#!/usr/bin/env python3
"""Corre el chequeo de riesgo sobre todas las revistas de watchlist.json,
compara contra la corrida anterior y genera un reporte en reports/YYYY-MM.md.

Uso:
    python src/monitor_watchlist.py
"""
import datetime
from pathlib import Path

from core import evaluate_journal, save_snapshot, last_snapshot, load_watchlist

BASE_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE_DIR / "reports"

NIVELES = ["Bajo", "Medio", "Medio-alto", "Alto"]


def _detecta_alerta(anterior: dict | None, actual: dict) -> str | None:
    if anterior is None:
        return None
    if NIVELES.index(actual["score"]) > NIVELES.index(anterior["score"]):
        return f"Riesgo subió de {anterior['score']} a {actual['score']}."
    return None


def main():
    revistas = load_watchlist()
    if not revistas:
        print("watchlist.json no tiene revistas reales todavía. Edítalo y vuelve a correr.")
        return

    alertas = []
    filas = []
    detalles = []

    for r in revistas:
        issn = r["issn"]
        anterior = last_snapshot(issn)
        resultado = evaluate_journal(issn, r.get("nombre", ""))
        save_snapshot(resultado)

        alerta = _detecta_alerta(anterior, resultado)
        if alerta:
            alertas.append(f"**{resultado['nombre']}** (ISSN {issn}): {alerta}")

        filas.append((resultado["nombre"], issn, resultado["score"]))
        detalles.append(resultado)

    mes = datetime.date.today().strftime("%Y-%m")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{mes}.md"

    lineas = [f"# Reporte de riesgo Scopus — {mes}\n"]

    if alertas:
        lineas.append("## ALERTAS\n")
        for a in alertas:
            lineas.append(f"- {a}")
        lineas.append("")

    lineas.append("## Resumen\n")
    lineas.append("| Revista | ISSN | Riesgo |")
    lineas.append("|---|---|---|")
    for nombre, issn, score in filas:
        lineas.append(f"| {nombre} | {issn} | {score} |")
    lineas.append("")

    lineas.append("## Detalle\n")
    for resultado in detalles:
        lineas.append(f"### {resultado['nombre']} (ISSN {resultado['issn']}) — {resultado['score']}\n")
        for razon in resultado["razones"]:
            lineas.append(f"- {razon}")
        lineas.append("")

    report_path.write_text("\n".join(lineas), encoding="utf-8")
    print(f"Reporte generado en {report_path}")
    if alertas:
        print("\n⚠ ALERTAS detectadas:")
        for a in alertas:
            print(f"  - {a}")


if __name__ == "__main__":
    main()
