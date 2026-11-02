from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from streamlit.testing.v1 import AppTest

from triadesk.api import app
from triadesk.demo import seed_demo
from triadesk.evaluation import evaluate
from triadesk.store import ChangeTicket, ConflictError, NewTicket, Store, sla_state
from triadesk.triage import CATEGORIES, classifier, draft_reply, suggest_priority

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "tickets.sqlite3")


def new(store, now=NOW):
    return store.create(NewTicket(title="Entrega atrasada", description="Minha encomenda não chegou e o rastreio da transportadora não mudou."), now)


def change(ticket, **kwargs):
    return ChangeTicket(version=ticket["version"], status=ticket["status"], category=ticket["category"], priority=ticket["priority"], **kwargs)


def test_durable_creation_and_history(store):
    ticket = new(store)
    assert ticket["status"] == "Novo"
    assert ticket["id"] == 1 and ticket["version"] == 1
    assert datetime.fromisoformat(ticket["due_at"]) == NOW + timedelta(hours=24)
    assert Store(store.path).get(1)["title"] == "Entrega atrasada"
    assert len(store.events(1)) == 1
    assert store.events(1)[0]["kind"] == "criado"


def test_complete_lifecycle_and_reopen(store):
    ticket = new(store)
    ticket = store.update(1, change(ticket).model_copy(update={"status": "Em atendimento"}), NOW + timedelta(hours=1))
    ticket = store.update(1, change(ticket).model_copy(update={"status": "Resolvido", "note": "Orientação registrada."}), NOW + timedelta(hours=2))
    assert ticket["resolved_at"] == (NOW + timedelta(hours=2)).isoformat()
    assert sla_state(ticket, NOW + timedelta(days=100))["state"] == "Resolvido no prazo"
    ticket = store.update(1, change(ticket).model_copy(update={"status": "Em atendimento"}), NOW + timedelta(days=1))
    assert ticket["resolved_at"] is None
    assert ticket["version"] == 4
    assert len(store.events(1)) == 4


def test_invalid_transition_rolls_back(store):
    ticket = new(store)
    with pytest.raises(ValueError, match="Transição"):
        store.update(1, change(ticket).model_copy(update={"status": "Resolvido"}), NOW)
    assert store.get(1)["status"] == "Novo"
    assert len(store.events(1)) == 1


def test_version_conflict_preserves_latest_update(store):
    ticket = new(store)
    store.update(1, change(ticket).model_copy(update={"status": "Em atendimento"}), NOW)
    with pytest.raises(ConflictError):
        Store(store.path).update(1, change(ticket), NOW)
    assert store.get(1)["version"] == 2
    assert len(store.events(1)) == 2


def test_manual_category_team_priority_and_original_suggestion(store):
    ticket = new(store)
    updated = store.update(1, change(ticket).model_copy(update={"category": "pagamento", "priority": "Alta", "note": "Origem confirmada."}), NOW + timedelta(hours=2))
    assert updated["team"] == "Financeiro"
    assert updated["due_at"] == (NOW + timedelta(hours=4)).isoformat()
    assert updated["suggestion"] == ticket["suggestion"]
    assert store.events(1)[-1]["details"]["note"] == "Origem confirmada."


@pytest.mark.parametrize("offset,state", [(0, "No prazo"), (22, "Vence em breve"), (24, "Vence em breve"), (25, "Vencido")])
def test_sla_boundaries(store, offset, state):
    ticket = new(store)
    assert sla_state(ticket, NOW + timedelta(hours=offset))["state"] == state


def test_resolved_late_and_unchanged_resolution_timestamp(store):
    ticket = new(store)
    ticket = store.update(1, change(ticket).model_copy(update={"status": "Em atendimento"}), NOW)
    ticket = store.update(1, change(ticket).model_copy(update={"status": "Resolvido"}), NOW + timedelta(hours=30))
    assert sla_state(ticket)["state"] == "Resolvido após prazo"
    updated = store.update(1, change(ticket, note="Nota posterior."), NOW + timedelta(days=2))
    assert updated["resolved_at"] == ticket["resolved_at"]


def test_naive_and_pre_creation_dates_rejected(store):
    with pytest.raises(ValueError, match="fuso"):
        new(store, datetime(2026, 1, 1))
    ticket = new(store)
    with pytest.raises(ValueError, match="antes da criação"):
        store.update(1, change(ticket), NOW - timedelta(seconds=1))


@pytest.mark.parametrize("data", [{"title": "  ", "description": "Descrição suficientemente longa."}, {"title": "Ok!", "description": "curta"}, {"title": "x" * 121, "description": "Descrição suficientemente longa."}, {"title": "Título", "description": "x" * 4001}, {"title": "Título", "description": "Descrição suficientemente longa.", "channel": "SMS"}])
def test_invalid_ticket_fields(data):
    with pytest.raises(ValidationError):
        NewTicket(**data)


def test_sql_metacharacters_are_data(store):
    request = NewTicket(title="'; DROP TABLE tickets; --", description="Pagamento '; DELETE FROM events; -- com falha.")
    ticket = store.create(request, NOW)
    assert store.get(ticket["id"])["description"] == request.description
    assert len(store.list()) == 1
    assert len(store.events(ticket["id"])) == 1


def test_missing_ticket(store):
    with pytest.raises(KeyError):
        store.get(999)
    with pytest.raises(KeyError):
        store.events(999)
    with pytest.raises(KeyError):
        store.update(999, ChangeTicket(version=1, status="Novo", category="conta", priority="Normal"), NOW)


def test_draft_has_no_external_delivery(store):
    ticket = new(store)
    draft = store.draft(ticket["id"])
    assert draft["sent"] is False
    assert draft["method"] == "template_local"
    assert "confirmada" in draft["text"]


@pytest.mark.parametrize("category", list(CATEGORIES))
def test_each_category_has_safe_nonempty_draft(category):
    assert len(draft_reply(category)) > 80


@pytest.mark.parametrize("text,expected", [("O sistema fora do ar afeta a operação", "Alta"), ("Falha para todos os usuários", "Alta"), ("Sugestão de melhoria futura na tela", "Baixa"), ("Preciso consultar meu pagamento", "Normal")])
def test_priority_rules(text, expected):
    assert suggest_priority(text)[0] == expected


def test_model_known_and_out_of_scope():
    model = classifier()
    assert model.predict("Meu pedido está atrasado e ainda não chegou à minha casa")["category"] == "entrega"
    assert model.predict("Quero aprender a tocar violão e estudar música.")["category"] == "triagem"
    assert model.predict("zzzz qqqq yyyyy")["needs_review"]


def test_evaluation_is_reproducible_and_no_identical_text_overlap():
    report = evaluate()
    assert report["train_count"] == 96
    assert report["test_count"] == 44
    assert report["duplicate_text_overlap"] == 0
    assert report["routing_macro_f1"] > report["baseline_macro_f1"]
    assert report["out_of_scope_correctly_routed"] == 8
    assert len(report["cases"]) == 44


def test_demo_independent_and_seeded_once(store, tmp_path):
    seed_demo(store, NOW)
    seed_demo(store, NOW)
    assert len(store.list()) == 12
    assert {s: sum(t["status"] == s for t in store.list()) for s in ["Novo", "Em atendimento", "Resolvido"]} == {"Novo": 4, "Em atendimento": 4, "Resolvido": 4}
    assert Store(tmp_path / "real.sqlite3").list() == []


def test_api_end_to_end_and_conflict(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIADESK_DB", str(tmp_path / "api.sqlite3"))
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        response = client.post("/tickets", json={"title": "Falha na entrega", "description": "A transportadora não entregou meu pacote no endereço correto."})
        assert response.status_code == 201
        ticket = response.json()
        update = {"version": ticket["version"], "status": "Em atendimento", "category": "entrega", "priority": "Normal", "note": "Verificação iniciada."}
        assert client.patch(f"/tickets/{ticket['id']}", json=update).status_code == 200
        assert client.patch(f"/tickets/{ticket['id']}", json=update).status_code == 409
        details = client.get(f"/tickets/{ticket['id']}").json()
        assert len(details["events"]) == 2
        assert details["draft"]["sent"] is False
        assert len(client.get("/tickets").json()) == 1


def test_api_validation_and_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIADESK_DB", str(tmp_path / "api.sqlite3"))
    with TestClient(app) as client:
        assert client.post("/tickets", json={"title": "a", "description": "b"}).status_code == 422
        assert client.get("/tickets/999").status_code == 404
        assert client.post("/triage", json={"text": " " * 20}).status_code == 422
        response = client.post("/triage", json={"text": "O site apresenta erro 500 quando abro a página"})
        assert response.status_code == 200
        assert response.json()["candidate"] == "tecnico"


def test_ui_board_create_update_and_filter(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIADESK_HOME", str(tmp_path / "ui"))
    ui = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not ui.exception
    assert len([b for b in ui.button if b.label == "Abrir chamado ↗"]) == 12
    next(s for s in ui.selectbox if s.label == "Ambiente").set_value("Meus chamados").run()
    assert not ui.exception
    assert not [b for b in ui.button if b.label == "Abrir chamado ↗"]
    next(r for r in ui.radio if r.label == "Navegação").set_value("Novo chamado").run()
    next(t for t in ui.text_input if t.label == "Assunto").set_value("Pagamento não confirmado")
    next(t for t in ui.text_area if t.label == "Descrição").set_value("Paguei o boleto e a compra continua aguardando pagamento.")
    next(b for b in ui.button if b.label == "Criar chamado e sugerir triagem").click().run()
    assert not ui.exception
    assert ui.success
    next(b for b in ui.button if b.label == "Abrir TD-0001").click().run()
    assert not ui.exception
    assert any("Pagamento não confirmado" in t.value for t in ui.title)
    next(s for s in ui.selectbox if s.label == "Situação").set_value("Em atendimento")
    next(t for t in ui.text_area if t.label == "Nota interna").set_value("Consulta interna registrada.")
    next(b for b in ui.button if b.label == "Salvar atendimento").click().run()
    assert not ui.exception
    assert next(s for s in ui.selectbox if s.label == "Situação").value == "Em atendimento"
    next(b for b in ui.button if b.label == "← Voltar ao quadro").click().run()
    next(t for t in ui.text_input if t.label == "Buscar chamado").set_value("não existe aqui").run()
    assert not ui.exception
    assert not [b for b in ui.button if b.label == "Abrir chamado ↗"]


def test_ui_evaluation_view(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIADESK_HOME", str(tmp_path / "evaluation_ui"))
    ui = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    next(r for r in ui.radio if r.label == "Navegação").set_value("Avaliação").run()
    assert not ui.exception
    assert any("Como a triagem foi medida" in t.value for t in ui.title)
    assert len(ui.dataframe) >= 2
