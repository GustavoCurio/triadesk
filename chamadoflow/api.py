"""API local para cadastro, fluxo, histórico e classificação; sem envio externo."""
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .store import ChangeTicket, ConflictError, NewTicket, Store, sla_state
from .triage import triage

app = FastAPI(title="ChamadoFlow", version="1.0.0")


def get_store():
    """Abre o repositório da API, criando sua estrutura quando necessário.

    CHAMADOFLOW_DB tem precedência sobre CHAMADOFLOW_HOME/chamados.sqlite3.
    Sem variáveis, usa storage/chamados.sqlite3 na raiz do projeto.
    """
    home = Path(os.environ.get("CHAMADOFLOW_HOME", str(Path(__file__).resolve().parents[1] / "storage")))
    return Store(os.environ.get("CHAMADOFLOW_DB", str(home / "chamados.sqlite3")))


@app.get("/health")
def health():
    """Retorna disponibilidade e versão sem abrir a base de chamados."""
    return {"status": "ok", "version": "1.0.0"}


# Contrato de texto para triagem sem persistência; o endpoint também rejeita espaços vazios.
class ClassifyRequest(BaseModel):
    text: str = Field(min_length=15, max_length=4121)


@app.post("/triage")
def classify(request: ClassifyRequest):
    """Sugere triagem para o texto validado, sem criar um chamado.

    Retorna categoria, sinais do modelo, equipe e prioridade. Texto composto
    por espaços é recusado com HTTP 422, além dos limites do contrato de entrada.
    """
    if len(request.text.strip()) < 15:
        raise HTTPException(422, "Descreva o assunto em pelo menos 15 caracteres.")
    return triage(request.text)


@app.get("/tickets")
def tickets():
    """Lista os chamados persistidos e acrescenta a situação atual dos seus prazos."""
    return [{**t, "sla": sla_state(t)} for t in get_store().list()]


@app.post("/tickets", status_code=201)
def create(request: NewTicket):
    """Recebe NewTicket validado, persiste a triagem e retorna o chamado com HTTP 201."""
    return get_store().create(request)


@app.get("/tickets/{ticket_id}")
def read(ticket_id: int):
    """Retorna chamado, eventos, rascunho local e situação do prazo.

    Args:
        ticket_id: Identificador inteiro do registro solicitado.

    Raises:
        HTTPException: 404 quando o chamado não existe nesta base.
    """
    try:
        store = get_store()
        ticket = store.get(ticket_id)
        return {**ticket, "events": store.events(ticket_id), "draft": store.draft(ticket_id), "sla": sla_state(ticket)}
    except KeyError as error:
        raise HTTPException(404, "Chamado não encontrado.") from error


@app.patch("/tickets/{ticket_id}")
def update(ticket_id: int, change: ChangeTicket):
    """Altera um chamado usando a versão fornecida e as regras de transição.

    Args:
        ticket_id: Identificador do registro a alterar.
        change: Novos campos e versão esperada, validados pelo ChangeTicket.

    Returns:
        Estado persistido após a alteração.

    Raises:
        HTTPException: 404 para chamado ausente; 409 para versão desatualizada;
            422 para transição ou data inválida no domínio.
    """
    try:
        return get_store().update(ticket_id, change)
    except KeyError as error:
        raise HTTPException(404, "Chamado não encontrado.") from error
    except ConflictError as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
