"""ChamadoFlow: quadro operacional e histórico local de atendimento."""
import csv
from datetime import datetime
from html import escape
import io
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from pydantic import ValidationError
import streamlit as st

from chamadoflow.demo import seed_demo
from chamadoflow.store import ChangeTicket, ConflictError, NewTicket, STATUSES, Store, TRANSITIONS, sla_state, utcnow
from chamadoflow.triage import CATEGORIES, SLA_HOURS

ROOT = Path(__file__).resolve().parent
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
st.set_page_config(page_title="ChamadoFlow · Mesa de atendimento", page_icon="↗", layout="wide")
st.markdown("""<style>
.stApp{background:#eef1f6;color:#283346}.block-container{max-width:1550px;padding-top:3.6rem}
h1,h2,h3{letter-spacing:-.035em}h1{font-size:1.9rem!important;padding:.25rem 0!important}
.block-container [data-testid="stVerticalBlock"]{gap:.65rem}.block-container hr{margin:.3rem 0}
div[class*="st-key-cf_card_"]{background:white;border-radius:12px}
.cf-brand{font-weight:800;font-size:23px;color:#2c3854}.cf-brand b{color:#e3634c}
.cf-brand span{font-size:11px;letter-spacing:2px;color:#8590a2;margin-left:20px;font-weight:600}
.column-head{border-top:3px solid;padding:14px 4px;font-size:13px;letter-spacing:1.4px;font-weight:800}
.column-head span{float:right;border-radius:5px;background:#dce2ec;padding:1px 8px;color:#34425c}
.ticket{margin-bottom:3px}.ticket .meta{font:11px monospace;color:#8590a2;margin-bottom:12px}
.ticket h4{font-size:17px;margin:8px 0;color:#26334b;line-height:1.35}
.ticket p{font-size:13px;line-height:1.55;color:#667389;margin:10px 0}
.ticket .tag{display:inline-block;padding:3px 8px;border-radius:4px;background:#f1f3f8;font-size:11px;color:#59647b}
.ticket .due{font-size:12px;color:#71809a;margin-top:14px}.ticket .late{color:#c44234}.ticket .soon{color:#a77313}
.queue-note{background:#fff5ed;border-left:3px solid #df8a48;padding:12px 16px;color:#8b582e;font-size:13px;margin:8px 0 12px}
[data-testid="stVerticalBlockBorderWrapper"]{border-radius:12px}
@media(max-width:700px){.cf-brand span{display:block;margin:6px 0}.ticket h4{font-size:16px}}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def workspace(path, demo):
    store = Store(path)
    if demo:
        seed_demo(store)
    return store


def open_ticket(ticket_id):
    st.session_state["cf_page"] = "Quadro"
    st.session_state["cf_ticket"] = ticket_id


def switch_space():
    st.session_state.pop("cf_ticket", None)
    st.session_state.pop("cf_created", None)


def when(value):
    return datetime.fromisoformat(value).astimezone(LOCAL_TZ).strftime("%d/%m · %H:%M")


def safe_csv(tickets):
    buffer = io.StringIO(newline="")
    fields = ["id", "title", "category", "team", "priority", "status", "created_at", "due_at", "resolved_at"]
    writer = csv.writer(buffer)
    writer.writerow(fields)
    for ticket in tickets:
        values = [str(ticket[field] or "") for field in fields]
        writer.writerow(["'" + value if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")) else value for value in values])
    return buffer.getvalue().encode("utf-8-sig")


st.markdown('<div class="cf-brand"><b>↗</b> ChamadoFlow<span>MESA DE ATENDIMENTO</span></div>', unsafe_allow_html=True)
brand, spaces = st.columns([2.2, 1])
with brand:
    page = st.radio("Navegação", ["Quadro", "Novo chamado", "Avaliação"], horizontal=True, key="cf_page", label_visibility="collapsed")
with spaces:
    space = st.selectbox("Ambiente", ["Demonstração", "Meus chamados"], on_change=switch_space, key="cf_space", label_visibility="collapsed")
home = Path(os.environ.get("CHAMADOFLOW_HOME", str(ROOT / "storage")))
path = home / ("demo.sqlite3" if space == "Demonstração" else "chamados.sqlite3")
store = workspace(str(path), space == "Demonstração")
st.caption("Demonstração com chamados fictícios." if space == "Demonstração" else "Seus chamados são salvos neste computador. A API usa a base Meus chamados por padrão.")
st.divider()

if page == "Novo chamado":
    st.title("Qual problema precisa de atenção?")
    form_col, explanation = st.columns([1.8, 1], gap="large")
    with form_col:
        with st.form("new_ticket"):
            title = st.text_input("Assunto", max_chars=120, placeholder="Ex.: Pagamento não confirmado")
            description = st.text_area("Descrição", max_chars=4000, height=190, placeholder="Descreva o que aconteceu e o resultado esperado. Não inclua senhas ou dados pessoais.")
            channel = st.selectbox("Canal de origem", ["Portal", "E-mail", "WhatsApp", "Telefone"])
            submitted = st.form_submit_button("Criar chamado e sugerir triagem", type="primary")
        if submitted:
            try:
                ticket = store.create(NewTicket(title=title, description=description, channel=channel))
                st.session_state["cf_created"] = ticket["id"]
                st.success(f"CF-{ticket['id']:04d} criado. Equipe sugerida: {ticket['team']}.")
            except ValidationError:
                st.error("Preencha um assunto de 3 a 120 caracteres e uma descrição de 15 a 4.000 caracteres.")
        if st.session_state.get("cf_created"):
            created_id = st.session_state["cf_created"]
            st.button(f"Abrir CF-{created_id:04d}", on_click=open_ticket, args=(created_id,))
    with explanation:
        st.subheader("Do relato ao responsável")
        st.write("**1. Classificar**\n\nO modelo local sugere o assunto e a equipe. Quando o sinal é insuficiente, o chamado segue para triagem manual.")
        st.write("**2. Priorizar**\n\nRegras explícitas sugerem prioridade. Você pode alterar a classificação e a prioridade no atendimento.")
        st.write("**3. Acompanhar**\n\nO prazo começa na criação e segue horas corridas: alta 4 h, normal 24 h e baixa 72 h.")
        st.caption("Os canais indicam apenas a origem informada. Não há conexão com e-mail, WhatsApp ou sistemas externos.")

elif page == "Avaliação":
    st.title("Como a triagem foi medida")
    report_path = ROOT / "reports/evaluation.json"
    if not report_path.exists():
        st.info("Execute python -m chamadoflow evaluate para gerar o relatório.")
    else:
        report = json.loads(report_path.read_text("utf-8"))
        st.write(f"**{report['train_count']} exemplos de treino · {report['test_count']} exemplos de verificação · textos sintéticos em português.**")
        st.info(report["limitations"])
        rows = [
            ("F1 macro de encaminhamento", f"{report['routing_macro_f1']:.3f}"),
            ("F1 macro da classe majoritária", f"{report['baseline_macro_f1']:.3f}"),
            ("Acerto de encaminhamento", f"{100*report['routing_accuracy']:.1f}%"),
            ("Encaminhamentos automáticos", str(report["automatic_count"])),
            ("Casos para triagem manual", str(report["manual_count"])),
            ("Fora do escopo enviados à triagem", f"{report['out_of_scope_correctly_routed']} / {report['out_of_scope_total']}"),
        ]
        a, b = st.columns([1, 1.5], gap="large")
        with a:
            st.dataframe(pd.DataFrame(rows, columns=["Critério", "Resultado"]), hide_index=True, width="stretch")
            st.caption("No acerto e F1 de encaminhamento, a abstenção em um assunto conhecido conta como erro. A classe Triagem é esperada para perguntas fora do escopo.")
        with b:
            st.subheader("Matriz de confusão")
            labels = [CATEGORIES[c][0] for c in report["confusion_labels"]]
            st.dataframe(pd.DataFrame(report["confusion_matrix"], index=labels, columns=labels), width="stretch")
            st.caption("Linhas: assunto esperado. Colunas: encaminhamento realizado.")
        with st.expander("Ver casos e pontuações"):
            st.dataframe(pd.DataFrame(report["cases"]), hide_index=True, width="stretch")
        st.download_button("Baixar avaliação · JSON", report_path.read_bytes(), "chamadoflow-avaliacao.json", "application/json")
    with st.expander("Modelo, regras e limites"):
        st.write("TF-IDF de palavras e caracteres + regressão logística. O treino usa somente data/train.json; a avaliação usa data/test.json, sem textos idênticos normalizados entre as bases. Os limiares são 0,40 de pontuação, 0,08 de margem entre classes e 0,08 de similaridade com o treino.")
        st.write("A prioridade é uma heurística separada do modelo: expressões como sistema fora do ar ou todos os usuários recebem prioridade alta. Sugestões e melhorias futuras recebem baixa; os demais relatos recebem normal. Os prazos são demonstrativos em horas corridas, sem calendário de feriados.")
        st.write("Rascunhos de resposta são modelos de texto locais por categoria. Nenhum LLM externo é usado e nenhuma mensagem é enviada.")

else:
    selected_id = st.session_state.get("cf_ticket")
    if selected_id:
        if st.button("← Voltar ao quadro"):
            st.session_state.pop("cf_ticket", None)
            st.rerun()
        try:
            ticket = store.get(selected_id)
        except KeyError:
            st.session_state.pop("cf_ticket", None)
            st.rerun()
        st.caption(f"CF-{ticket['id']:04d} · {ticket['channel']} · criado em {when(ticket['created_at'])}")
        st.title(ticket["title"])
        content, actions = st.columns([1.65, 1], gap="large")
        with content:
            with st.container(border=True):
                st.subheader("Relato recebido")
                st.write(ticket["description"])
                st.caption(f"Prazo: {when(ticket['due_at'])} · {sla_state(ticket)['state']} · prioridade {ticket['priority']}")
            st.subheader("Resposta sugerida")
            st.caption("Rascunho local por categoria. Confira a adequação antes de usar em um atendimento real.")
            st.code(store.draft(selected_id)["text"], language=None, wrap_lines=True)
            st.caption("Nenhuma mensagem é enviada pelo ChamadoFlow.")
            with st.expander("Histórico do chamado", expanded=True):
                for event in reversed(store.events(selected_id)):
                    st.caption(f"{when(event['created_at'])} · {event['kind']}")
                    details = event["details"]
                    if event["kind"] == "criado":
                        st.write(f"Chamado recebido · {CATEGORIES[details['category']][0]} · prioridade {details['priority']}.")
                    else:
                        before, after = details["before"], details["after"]
                        st.write(f"{before['status']} → {after['status']} · {CATEGORIES[after['category']][0]} · {after['priority']}")
                        if details["note"]:
                            st.write(details["note"])
        with actions:
            with st.container(border=True):
                st.subheader("Conduzir atendimento")
                with st.form(f"edit_{selected_id}_{ticket['version']}"):
                    allowed = [s for s in STATUSES if s == ticket["status"] or s in TRANSITIONS[ticket["status"]]]
                    status = st.selectbox("Situação", allowed, index=allowed.index(ticket["status"]))
                    category = st.selectbox("Assunto confirmado", list(CATEGORIES), index=list(CATEGORIES).index(ticket["category"]), format_func=lambda c: CATEGORIES[c][0])
                    priority = st.selectbox("Prioridade", list(SLA_HOURS), index=list(SLA_HOURS).index(ticket["priority"]))
                    st.caption("A equipe acompanha o assunto escolhido. Mudar a prioridade recalcula o prazo a partir da criação.")
                    note = st.text_area("Nota interna", max_chars=2000, placeholder="Registre o que foi verificado ou realizado.")
                    save = st.form_submit_button("Salvar atendimento", type="primary")
                if save:
                    try:
                        store.update(selected_id, ChangeTicket(version=ticket["version"], status=status, category=category, priority=priority, note=note))
                        st.rerun()
                    except (ValueError, ConflictError) as error:
                        st.error(str(error))
                st.caption(f"Equipe: {ticket['team']}")
            with st.expander("Por que esta sugestão?"):
                suggestion = ticket["suggestion"]
                st.write(suggestion["reason"])
                st.write(f"Assunto candidato: {CATEGORIES[suggestion['candidate']][0]}")
                st.caption(f"Pontuação: {suggestion['score']:.3f} · margem: {suggestion['margin']:.3f} · similaridade: {suggestion['similarity']:.3f}. Estes valores não são probabilidades calibradas.")
                st.write(suggestion["priority_reason"])
                st.caption("A sugestão original é preservada mesmo após alterações manuais.")
        export = {**ticket, "events": store.events(selected_id), "draft": store.draft(selected_id)}
        st.download_button("Baixar chamado e histórico · JSON", json.dumps(export, ensure_ascii=False, indent=2), f"chamado-{selected_id}.json", "application/json")
    else:
        heading, refresh = st.columns([4, 1])
        heading.title("Organize a próxima ação.")
        refresh.button("Atualizar quadro")
        now = utcnow()
        tickets = store.list()
        late = sum(t["status"] != "Resolvido" and sla_state(t, now)["state"] == "Vencido" for t in tickets)
        manual = sum(t["category"] == "triagem" and t["status"] != "Resolvido" for t in tickets)
        st.markdown(f'<div class="queue-note">{len(tickets)} chamados neste ambiente &nbsp; / &nbsp; {late} com prazo vencido &nbsp; / &nbsp; {manual} aguardando classificação manual</div>', unsafe_allow_html=True)
        search_col, team_col, priority_col, due_col = st.columns([1.6, 1.2, 1, 1])
        search = search_col.text_input("Buscar chamado", placeholder="Assunto, descrição ou CF-0001")
        team = team_col.selectbox("Equipe", ["Todas"] + sorted({v[1] for v in CATEGORIES.values()}))
        priority_filter = priority_col.selectbox("Prioridade", ["Todas"] + list(SLA_HOURS))
        only_late = due_col.checkbox("Só vencidos")
        filtered = [t for t in tickets if (not search or search.casefold() in (t["title"] + " " + t["description"] + f" CF-{t['id']:04d}").casefold()) and (team == "Todas" or t["team"] == team) and (priority_filter == "Todas" or t["priority"] == priority_filter) and (not only_late or (t["status"] != "Resolvido" and sla_state(t, now)["state"] == "Vencido"))]
        st.caption(f"{len(filtered)} chamados no recorte · prazos em horas corridas · atualize o quadro para renovar a situação dos prazos")
        cols = st.columns(3, gap="medium")
        for column, status, label, color in zip(cols, STATUSES, ["NOVOS", "EM ATENDIMENTO", "RESOLVIDOS"], ["#738aaf", "#d79a40", "#63a68e"]):
            with column:
                grouped = [t for t in filtered if t["status"] == status]
                grouped.sort(key=lambda t: (datetime.fromisoformat(t["due_at"]), t["id"]))
                st.markdown(f'<div class="column-head" style="border-color:{color}">{label}<span>{len(grouped)}</span></div>', unsafe_allow_html=True)
                if not grouped:
                    st.caption("Nenhum chamado nesta coluna.")
                for ticket in grouped:
                    sla = sla_state(ticket, now)
                    tone = "late" if sla["state"] in {"Vencido", "Resolvido após prazo"} else "soon" if sla["state"] == "Vence em breve" else ""
                    with st.container(border=True, key=f"cf_card_{ticket['id']}"):
                        st.markdown(f'''<div class="ticket"><div class="meta">CF-{ticket['id']:04d} · {escape(ticket['channel'])} · {escape(ticket['priority'])}</div><span class="tag">{escape(CATEGORIES[ticket['category']][0])}</span><h4>{escape(ticket['title'])}</h4><p>{escape(ticket['description'][:115])}{'…' if len(ticket['description']) > 115 else ''}</p><div class="due {tone}">{escape(sla['state'])} · {when(ticket['due_at'])}</div></div>''', unsafe_allow_html=True)
                        st.caption(ticket["team"])
                        st.button("Abrir chamado ↗", key=f"open_{ticket['id']}", on_click=open_ticket, args=(ticket["id"],), width="stretch")
        st.divider()
        st.download_button("Exportar recorte · CSV", safe_csv(filtered), "chamadoflow-quadro.csv", "text/csv")
        st.caption("As alterações ficam salvas no SQLite local. A demonstração usa uma base separada de Meus chamados.")
