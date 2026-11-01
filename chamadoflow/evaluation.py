"""Avaliação reproduzível em exemplos sintéticos separados do treino."""
from collections import Counter
import json
from pathlib import Path

from sklearn.dummy import DummyClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

from .triage import CATEGORIES, Classifier, MARGIN_THRESHOLD, SCORE_THRESHOLD, SIMILARITY_THRESHOLD, normalize

ROOT = Path(__file__).resolve().parents[1]


def evaluate():
    train = json.loads((ROOT / "data/train.json").read_text("utf-8"))
    test = json.loads((ROOT / "data/test.json").read_text("utf-8"))
    train_text = {normalize(row["text"]).strip() for row in train}
    test_text = [normalize(row["text"]).strip() for row in test]
    if train_text.intersection(test_text) or len(set(test_text)) != len(test):
        raise ValueError("Textos repetidos no treino/teste.")
    model = Classifier(train)
    predictions = [model.predict(row["text"]) for row in test]
    expected = [row["category"] for row in test]
    routed = [row["category"] for row in predictions]
    labels = list(CATEGORIES)
    baseline = DummyClassifier(strategy="most_frequent").fit([[0]] * len(train), [r["category"] for r in train])
    baseline_predictions = baseline.predict([[0]] * len(test))
    accepted = [(truth, pred["category"]) for truth, pred in zip(expected, predictions) if not pred["needs_review"]]
    scope = [i for i, label in enumerate(expected) if label != "triagem"]
    unknown = [i for i, label in enumerate(expected) if label == "triagem"]
    return {
        "dataset": "Exemplos sintéticos em português, escritos para o projeto; conjunto de verificação de desenvolvimento.",
        "train_count": len(train), "test_count": len(test), "test_by_category": dict(Counter(expected)),
        "duplicate_text_overlap": 0,
        "thresholds": {"score": SCORE_THRESHOLD, "margin": MARGIN_THRESHOLD, "similarity": SIMILARITY_THRESHOLD},
        "routing_accuracy": round(accuracy_score(expected, routed), 4),
        "routing_macro_f1": round(f1_score(expected, routed, labels=labels, average="macro", zero_division=0), 4),
        "baseline_accuracy": round(accuracy_score(expected, baseline_predictions), 4),
        "baseline_macro_f1": round(f1_score(expected, baseline_predictions, labels=labels, average="macro", zero_division=0), 4),
        "in_scope_raw_accuracy": round(accuracy_score([expected[i] for i in scope], [predictions[i]["candidate"] for i in scope]), 4),
        "automatic_count": len(accepted),
        "automatic_accuracy": round(sum(a == b for a, b in accepted) / len(accepted), 4) if accepted else None,
        "manual_count": sum(p["needs_review"] for p in predictions),
        "out_of_scope_correctly_routed": sum(routed[i] == "triagem" for i in unknown),
        "out_of_scope_total": len(unknown),
        "classification_report": classification_report(expected, routed, labels=labels, output_dict=True, zero_division=0),
        "confusion_labels": labels,
        "confusion_matrix": confusion_matrix(expected, routed, labels=labels).tolist(),
        "cases": [{"text": row["text"], "expected": row["category"], **pred} for row, pred in zip(test, predictions)],
        "limitations": "Base pequena, sintética e relacionada ao desenvolvimento. As pontuações não são probabilidades calibradas. Não mede qualidade em atendimentos reais ou rascunhos de resposta.",
    }


def save_report(path):
    report = evaluate()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    return report
