"""Classificação de relatos e avaliação reproduzível pela linha de comando."""
import argparse
from pathlib import Path

from .evaluation import save_report
from .triage import triage
import json


def main():
    """Oferece classificação local e geração do relatório de avaliação pelo terminal.

    triage valida tamanho e imprime a sugestão em JSON. evaluate grava o
    relatório no destino escolhido e imprime métricas resumidas. Erros de
    argumentos usam o código 2 do argparse; falhas de domínio/I/O são propagadas.
    """
    parser = argparse.ArgumentParser(description="TriaDesk: classificação local e avaliação")
    commands = parser.add_subparsers(dest="command", required=True)
    classify = commands.add_parser("triage")
    classify.add_argument("text")
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--output", type=Path, default=Path("reports/evaluation.json"))
    args = parser.parse_args()
    if args.command == "triage":
        if not 15 <= len(args.text.strip()) <= 4121:
            parser.error("O texto precisa ter de 15 a 4.121 caracteres.")
        print(json.dumps(triage(args.text), ensure_ascii=False, indent=2))
    else:
        report = save_report(args.output)
        print(json.dumps({k: report[k] for k in ["train_count", "test_count", "routing_accuracy", "routing_macro_f1", "baseline_macro_f1", "manual_count", "out_of_scope_correctly_routed"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
