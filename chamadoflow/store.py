"""SQLite local com transações, histórico e controle de concorrência por versão."""
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .triage import CATEGORIES, SLA_HOURS, draft_reply, triage

STATUSES = ["Novo", "Em atendimento", "Resolvido"]
TRANSITIONS = {"Novo": {"Em atendimento"}, "Em atendimento": {"Novo", "Resolvido"}, "Resolvido": {"Em atendimento"}}


def utcnow():
    """Retorna o instante atual como datetime com fuso UTC."""
    return datetime.now(timezone.utc)


def iso(value):
    """Converte datetime com fuso em texto ISO 8601 normalizado para UTC.

    Raises:
        ValueError: A data recebida não tem informação válida de fuso horário.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Use data com fuso horário.")
    return value.astimezone(timezone.utc).isoformat()


# Entrada de cadastro: limita conteúdo, canal e campos extras antes de persistir.
class NewTicket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=15, max_length=4000)
    channel: Literal["Portal", "E-mail", "WhatsApp", "Telefone"] = "Portal"

    @field_validator("title", "description", mode="before")
    @classmethod
    def strip_text(cls, value):
        """Remove espaços externos dos campos textuais antes de validar seus limites."""
        return value.strip() if isinstance(value, str) else value


# Alteração com versão esperada; transições e existência do ID são conferidas no Store.
class ChangeTicket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    status: Literal["Novo", "Em atendimento", "Resolvido"]
    category: Literal["entrega", "pagamento", "conta", "produto", "cancelamento", "tecnico", "triagem"]
    priority: Literal["Alta", "Normal", "Baixa"]
    note: str = Field(default="", max_length=2000)


class ConflictError(ValueError):
    """A versão recebida está desatualizada em relação ao chamado persistido."""
    pass


def sla_state(ticket, now=None):
    """Calcula a situação do prazo usando a resolução ou o relógio informado.

    Args:
        ticket: Registro com status, due_at e resolved_at coerentes entre si.
        now: Instante com fuso para chamados abertos; None usa utcnow.

    Returns:
        Dicionário state/remaining_hours. Prazo aberto negativo é Vencido;
        de zero até duas horas é Vence em breve. Chamados resolvidos comparam
        o prazo com resolved_at, independentemente do momento da consulta.

    Raises:
        ValueError: A referência efetiva de tempo está sem fuso.

    Horas são corridas, sem expediente ou feriados. Exatamente no prazo
    ainda é considerado no prazo para resolução.
    """
    end = datetime.fromisoformat(ticket["resolved_at"]) if ticket["status"] == "Resolvido" else (now or utcnow())
    if end.tzinfo is None:
        raise ValueError("Use data com fuso horário.")
    remaining = (datetime.fromisoformat(ticket["due_at"]) - end).total_seconds() / 3600
    if ticket["status"] == "Resolvido":
        return {"state": "Resolvido no prazo" if remaining >= 0 else "Resolvido após prazo", "remaining_hours": round(remaining, 2)}
    return {"state": "Vencido" if remaining < 0 else "Vence em breve" if remaining <= 2 else "No prazo", "remaining_hours": round(remaining, 2)}


class Store:
    """Repositório SQLite local de chamados e eventos de atendimento.

    Cada operação abre e fecha sua conexão. Criação/alteração e seus eventos
    são gravados na mesma transação. Não implementa autenticação por operador.
    """
    def __init__(self, path):
        """Cria a pasta e as tabelas se necessário, preservando registros existentes.

        Args:
            path: Caminho de um arquivo SQLite local; a pasta pai é criada.

        Erros de permissão, arquivo inválido ou SQLite são propagados ao chamador.
        """
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT NOT NULL,
                channel TEXT NOT NULL, category TEXT NOT NULL, team TEXT NOT NULL,
                priority TEXT NOT NULL, status TEXT NOT NULL, suggestion TEXT NOT NULL,
                created_at TEXT NOT NULL, due_at TEXT NOT NULL, resolved_at TEXT,
                version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
                created_at TEXT NOT NULL, kind TEXT NOT NULL, details TEXT NOT NULL
            );
            """)

    @contextmanager
    def connect(self):
        """Fornece conexão transacional com chaves estrangeiras e espera de até dez segundos.

        Yields:
            Conexão SQLite com linhas acessíveis por nome de coluna.

        Confirma a transação ao sair normalmente; em exceção, desfaz alterações
        pendentes. Fecha a conexão em ambos os casos para liberar arquivo e locks.
        """
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def decode(row):
        """Converte uma linha SQLite em dicionário e desserializa a sugestão original do modelo."""
        ticket = dict(row)
        ticket["suggestion"] = json.loads(ticket["suggestion"])
        return ticket

    def list(self):
        """Retorna chamados do mais recente ao mais antigo, desempate por ID decrescente."""
        with self.connect() as db:
            rows = db.execute("SELECT * FROM tickets ORDER BY created_at DESC, id DESC").fetchall()
        return [self.decode(row) for row in rows]

    def get(self, ticket_id):
        """Lê um chamado por identificador com consulta parametrizada.

        Returns:
            Dicionário do registro com suggestion desserializada.

        Raises:
            KeyError: O chamado não existe no arquivo deste repositório.
        """
        with self.connect() as db:
            row = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if row is None:
            raise KeyError("Chamado não encontrado.")
        return self.decode(row)

    def events(self, ticket_id):
        """Retorna eventos do chamado em ordem crescente de inserção.

        O campo details de cada evento é desserializado. Gera KeyError se o
        chamado não existe, mesmo que a tabela de eventos não contenha registros.
        """
        self.get(ticket_id)
        with self.connect() as db:
            return [{**dict(row), "details": json.loads(row["details"])} for row in db.execute("SELECT * FROM events WHERE ticket_id=? ORDER BY id", (ticket_id,))]

    def create(self, request: NewTicket, now=None):
        """Classifica um novo chamado e persiste sua criação com o primeiro evento.

        Args:
            request: NewTicket validado, contendo assunto, descrição e canal declarado.
            now: Instante com fuso da criação; None usa o relógio UTC atual.

        Returns:
            Registro lido após gravar, inicialmente com status Novo e versão 1.

        Raises:
            ValueError: A referência de criação está sem fuso; falhas de triagem
                ou persistência também são propagadas.

        Assunto e descrição alimentam a triagem. A equipe deriva da categoria e
        o prazo soma horas corridas à criação. O canal é metadado, não integração.
        """
        now = now or utcnow()
        created = iso(now)
        suggestion = triage(request.title + "\n" + request.description)
        due = iso(now + timedelta(hours=SLA_HOURS[suggestion["priority"]]))
        with self.connect() as db:
            cursor = db.execute("""INSERT INTO tickets (title,description,channel,category,team,priority,status,suggestion,created_at,due_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""", (request.title, request.description, request.channel, suggestion["category"], suggestion["team"], suggestion["priority"], "Novo", json.dumps(suggestion, ensure_ascii=False), created, due))
            ticket_id = cursor.lastrowid
            db.execute("INSERT INTO events(ticket_id,created_at,kind,details) VALUES (?,?,?,?)", (ticket_id, created, "criado", json.dumps({"category": suggestion["category"], "priority": suggestion["priority"], "channel": request.channel}, ensure_ascii=False)))
        return self.get(ticket_id)

    def update(self, ticket_id, change: ChangeTicket, now=None):
        """Aplica uma alteração validada e registra os estados anterior e posterior.

        Args:
            ticket_id: Identificador do chamado neste arquivo SQLite.
            change: ChangeTicket com versão lida pelo operador e novos campos.
            now: Instante com fuso da operação; None usa utcnow.

        Returns:
            Registro lido após confirmar a transação, com versão incrementada.

        Raises:
            KeyError: O chamado não existe.
            ConflictError: A versão informada não coincide com a persistida.
            ValueError: Transição inválida, data sem fuso ou alteração anterior à criação.

        BEGIN IMMEDIATE bloqueia escritas concorrentes antes de conferir a versão.
        A equipe acompanha a categoria. A prioridade recalcula o prazo desde a
        criação; reabrir limpa resolved_at, sem reiniciar o relógio do prazo.
        A sugestão automática original é preservada. Registro e evento são atômicos.
        """
        now = now or utcnow()
        stamp = iso(now)
        with self.connect() as db:
            # Ler e comparar a versão sob o mesmo lock evita perder uma alteração concorrente.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
            if row is None:
                raise KeyError("Chamado não encontrado.")
            previous = self.decode(row)
            if previous["version"] != change.version:
                raise ConflictError("Este chamado mudou em outra sessão. Recarregue antes de salvar.")
            if change.status != previous["status"] and change.status not in TRANSITIONS[previous["status"]]:
                raise ValueError("Transição inválida. Inicie o atendimento antes de resolver o chamado.")
            if now < datetime.fromisoformat(previous["created_at"]):
                raise ValueError("A alteração não pode ocorrer antes da criação.")
            resolved = previous["resolved_at"] if previous["status"] == change.status == "Resolvido" else stamp if change.status == "Resolvido" else None
            # A criação continua como referência; prioridade e reabertura não reiniciam a contagem.
            due = iso(datetime.fromisoformat(previous["created_at"]) + timedelta(hours=SLA_HOURS[change.priority]))
            db.execute("""UPDATE tickets SET status=?,category=?,team=?,priority=?,due_at=?,resolved_at=?,version=version+1 WHERE id=?""", (change.status, change.category, CATEGORIES[change.category][1], change.priority, due, resolved, ticket_id))
            # O evento é gravado na mesma transação do chamado, preservando a rastreabilidade.
            details = {"before": {k: previous[k] for k in ["status", "category", "priority"]}, "after": change.model_dump(exclude={"version", "note"}), "note": change.note.strip()}
            db.execute("INSERT INTO events(ticket_id,created_at,kind,details) VALUES (?,?,?,?)", (ticket_id, stamp, "atualizado", json.dumps(details, ensure_ascii=False)))
        return self.get(ticket_id)

    def draft(self, ticket_id):
        """Lê a categoria atual e retorna o template local com sent=False.

        Não persiste resposta nem realiza envio. Chamado inexistente gera KeyError.
        """
        ticket = self.get(ticket_id)
        return {"ticket_id": ticket_id, "category": ticket["category"], "text": draft_reply(ticket["category"]), "sent": False, "method": "template_local"}
