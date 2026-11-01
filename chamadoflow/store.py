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
    return datetime.now(timezone.utc)


def iso(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Use data com fuso horário.")
    return value.astimezone(timezone.utc).isoformat()


class NewTicket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=15, max_length=4000)
    channel: Literal["Portal", "E-mail", "WhatsApp", "Telefone"] = "Portal"

    @field_validator("title", "description", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class ChangeTicket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    status: Literal["Novo", "Em atendimento", "Resolvido"]
    category: Literal["entrega", "pagamento", "conta", "produto", "cancelamento", "tecnico", "triagem"]
    priority: Literal["Alta", "Normal", "Baixa"]
    note: str = Field(default="", max_length=2000)


class ConflictError(ValueError):
    pass


def sla_state(ticket, now=None):
    end = datetime.fromisoformat(ticket["resolved_at"]) if ticket["status"] == "Resolvido" else (now or utcnow())
    if end.tzinfo is None:
        raise ValueError("Use data com fuso horário.")
    remaining = (datetime.fromisoformat(ticket["due_at"]) - end).total_seconds() / 3600
    if ticket["status"] == "Resolvido":
        return {"state": "Resolvido no prazo" if remaining >= 0 else "Resolvido após prazo", "remaining_hours": round(remaining, 2)}
    return {"state": "Vencido" if remaining < 0 else "Vence em breve" if remaining <= 2 else "No prazo", "remaining_hours": round(remaining, 2)}


class Store:
    def __init__(self, path):
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
        ticket = dict(row)
        ticket["suggestion"] = json.loads(ticket["suggestion"])
        return ticket

    def list(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM tickets ORDER BY created_at DESC, id DESC").fetchall()
        return [self.decode(row) for row in rows]

    def get(self, ticket_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if row is None:
            raise KeyError("Chamado não encontrado.")
        return self.decode(row)

    def events(self, ticket_id):
        self.get(ticket_id)
        with self.connect() as db:
            return [{**dict(row), "details": json.loads(row["details"])} for row in db.execute("SELECT * FROM events WHERE ticket_id=? ORDER BY id", (ticket_id,))]

    def create(self, request: NewTicket, now=None):
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
        now = now or utcnow()
        stamp = iso(now)
        with self.connect() as db:
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
            due = iso(datetime.fromisoformat(previous["created_at"]) + timedelta(hours=SLA_HOURS[change.priority]))
            db.execute("""UPDATE tickets SET status=?,category=?,team=?,priority=?,due_at=?,resolved_at=?,version=version+1 WHERE id=?""", (change.status, change.category, CATEGORIES[change.category][1], change.priority, due, resolved, ticket_id))
            details = {"before": {k: previous[k] for k in ["status", "category", "priority"]}, "after": change.model_dump(exclude={"version", "note"}), "note": change.note.strip()}
            db.execute("INSERT INTO events(ticket_id,created_at,kind,details) VALUES (?,?,?,?)", (ticket_id, stamp, "atualizado", json.dumps(details, ensure_ascii=False)))
        return self.get(ticket_id)

    def draft(self, ticket_id):
        ticket = self.get(ticket_id)
        return {"ticket_id": ticket_id, "category": ticket["category"], "text": draft_reply(ticket["category"]), "sent": False, "method": "template_local"}
