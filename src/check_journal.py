#!/usr/bin/env python3
"""Chequeo puntual de riesgo de discontinuación de una revista en Scopus.

Uso:
    python src/check_journal.py --issn 1234-5678 [--nombre "Nombre de la revista"]
"""
import argparse

from core import evaluate_journal, save_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issn", required=True, help="ISSN de la revista (con o sin guion)")
    parser.add_argument("--nombre", default="", help="Nombre de la revista (opcional, solo para el reporte)")
    parser.add_argument("--no-guardar", action="store_true", help="No guardar snapshot en el historial")
    args = parser.parse_args()

    resultado = evaluate_journal(args.issn, args.nombre)

    print(f"\nRevista: {resultado['nombre']} (ISSN {resultado['issn']})")
    print(f"Riesgo: {resultado['score']}")
    print("Razones:")
    for r in resultado["razones"]:
        print(f"  - {r}")

    if not args.no_guardar:
        save_snapshot(resultado)
        print("\n(snapshot guardado en data/history/)")


if __name__ == "__main__":
    main()
