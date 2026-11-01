"""Classificação supervisionada local; prioridade e rascunhos por regras explícitas."""
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {
    "entrega": ("Entrega e rastreio", "Logística"),
    "pagamento": ("Pagamentos", "Financeiro"),
    "conta": ("Conta e acesso", "Suporte de acesso"),
    "produto": ("Produto e qualidade", "Pós-venda"),
    "cancelamento": ("Cancelamento e devolução", "Relacionamento"),
    "tecnico": ("Problema técnico", "Engenharia de suporte"),
    "triagem": ("Triagem manual", "Triagem"),
}
SLA_HOURS = {"Alta": 4, "Normal": 24, "Baixa": 72}
SCORE_THRESHOLD = 0.40
MARGIN_THRESHOLD = 0.08
SIMILARITY_THRESHOLD = 0.08


def normalize(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))


class Classifier:
    def __init__(self, rows):
        if not rows or any(row["category"] not in CATEGORIES or row["category"] == "triagem" for row in rows):
            raise ValueError("Base de treino inválida.")
        normalized = [normalize(row["text"]).strip() for row in rows]
        if len(set(normalized)) != len(rows):
            raise ValueError("O treino contém textos duplicados.")
        self.model = Pipeline([
            ("features", FeatureUnion([
                ("words", TfidfVectorizer(strip_accents="unicode", ngram_range=(1, 2), sublinear_tf=True)),
                ("chars", TfidfVectorizer(analyzer="char_wb", strip_accents="unicode", ngram_range=(3, 5), sublinear_tf=True)),
            ], transformer_weights={"words": 0.7, "chars": 0.3})),
            ("classifier", LogisticRegression(C=8, max_iter=1000, random_state=42)),
        ])
        self.model.fit([r["text"] for r in rows], [r["category"] for r in rows])
        self.train_vectors = self.model.named_steps["features"].transform([r["text"] for r in rows])

    def predict(self, text):
        probabilities = self.model.predict_proba([text])[0]
        order = np.argsort(probabilities)[::-1]
        score = float(probabilities[order[0]])
        margin = float(score - probabilities[order[1]])
        vector = self.model.named_steps["features"].transform([text])
        similarity = float(cosine_similarity(vector, self.train_vectors).max())
        candidate = str(self.model.classes_[order[0]])
        accepted = score >= SCORE_THRESHOLD and margin >= MARGIN_THRESHOLD and similarity >= SIMILARITY_THRESHOLD
        return {"category": candidate if accepted else "triagem", "candidate": candidate,
                "score": round(score, 4), "margin": round(margin, 4), "similarity": round(similarity, 4),
                "needs_review": not accepted,
                "reason": "Sugestão do classificador local." if accepted else "Pontuação, separação ou similaridade insuficiente; classificação manual necessária."}


@lru_cache(maxsize=1)
def classifier():
    rows = json.loads((ROOT / "data/train.json").read_text("utf-8"))
    return Classifier(rows)


def suggest_priority(text):
    plain = normalize(text)
    critical = ["sistema fora do ar", "sistema indisponivel", "todos os usuarios", "vazamento de dados", "suspeita de invasao", "conta invadida"]
    matched = next((term for term in critical if term in plain), None)
    if matched:
        return "Alta", f"Expressão encontrada: {matched}. Regra demonstrativa; confirme a prioridade."
    if re.search(r"\b(sugestao|sugestão|elogio|melhoria futura)\b", plain):
        return "Baixa", "Sugestão, elogio ou melhoria futura identificada por regra."
    return "Normal", "Prioridade padrão; não foi encontrada expressão crítica configurada."


def triage(text):
    result = classifier().predict(text)
    priority, reason = suggest_priority(text)
    return {**result, "team": CATEGORIES[result["category"]][1], "priority": priority, "priority_reason": reason}


def draft_reply(category):
    drafts = {
        "entrega": "Recebemos sua solicitação sobre a entrega. A equipe de logística verificará o rastreio e as informações disponíveis. Ainda não há uma nova data confirmada. Não envie dados pessoais por este canal demonstrativo.",
        "pagamento": "Recebemos sua dúvida sobre o pagamento. A equipe financeira verificará a situação nos canais autenticados. Não envie número de cartão, senha ou comprovantes com dados pessoais nesta demonstração.",
        "conta": "Recebemos sua solicitação de acesso. Utilize o fluxo oficial de recuperação de conta. A equipe de suporte pode orientar os próximos passos pelo canal autenticado; nunca compartilhe sua senha ou código de verificação.",
        "produto": "Recebemos o relato sobre o produto. A equipe de pós-venda verificará o problema e as alternativas previstas na política aplicável. A análise ainda não representa aprovação de troca, garantia ou reembolso.",
        "cancelamento": "Recebemos sua solicitação de cancelamento ou devolução. A equipe responsável verificará o pedido e a política aplicável. O cancelamento ou reembolso ainda não está confirmado.",
        "tecnico": "Recebemos o relato de falha técnica. A equipe de suporte verificará o comportamento informado. Se possível, descreva os passos para reproduzir o problema sem incluir senhas, tokens ou dados pessoais.",
        "triagem": "Recebemos sua solicitação. Precisamos identificar o assunto para direcioná-la à equipe adequada. Descreva o problema e o resultado esperado, sem incluir senhas ou dados pessoais.",
    }
    return drafts[category]
