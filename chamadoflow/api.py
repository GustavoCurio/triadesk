"""API local para cadastro, fluxo, histórico e classificação; sem envio externo."""
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .store import ChangeTicket, ConflictError, NewTicket, Store, sla_state
from .triage import triage

app = FastAPI(title="ChamadoFlow", version="1.0.0")


def get_store():
    home = Path(os.environ.get("CHAMADOFLOW_HOME", str(Path(__file__).resolve().parents[1] / "storage")))
    return Store(os.environ.get("CHAMADOFLOW_DB", str(home / "chamados.sqlite3")))


@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


class ClassifyRequest(BaseModel):
    text: str = Field(min_length=15, max_length=4121)


@app.post("/triage")
def classify(request: ClassifyRequest):
    if len(request.text.strip()) < 15:
        raise HTTPException(422, "Descreva o assunto em pelo menos 15 caracteres.")
    return triage(request.text)


@app.get("/tickets")
def tickets():
    return [{**t, "sla": sla_state(t)} for t in get_store().list()]


@app.post("/tickets", status_code=201)
def create(request: NewTicket):
    return get_store().create(request)


@app.get("/tickets/{ticket_id}")
def read(ticket_id: int):
    try:
        store = get_store()
        ticket = store.get(ticket_id)
        return {**ticket, "events": store.events(ticket_id), "draft": store.draft(ticket_id), "sla": sla_state(ticket)}
    except KeyError as error:
        raise HTTPException(404, "Chamado não encontrado.") from error


@app.patch("/tickets/{ticket_id}")
def update(ticket_id: int, change: ChangeTicket):
    try:
        return get_store().update(ticket_id, change)
    except KeyError as error:
        raise HTTPException(404, "Chamado não encontrado.") from error
    except ConflictError as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
