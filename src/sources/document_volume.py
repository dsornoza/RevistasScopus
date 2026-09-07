"""Volumen de artículos publicados por año, vía la API de Crossref.

Señal descrita en investigaciones sobre revistas bajo revisión CSAB de Scopus
(ej. "5 Predatory Scopus Journals Already Under Exclusion", Futurity
Publishing, 2026): un salto brusco en el número de artículos/issues por año
es uno de los indicadores más fuertes de que una revista está bajando su
control de calidad — típicamente porque está "vendiendo" cupos mientras
todavía puede, a la espera de una decisión de exclusión.
"""
import datetime
import time

import requests

API_URL = "https://api.crossref.org/v1/works"
HEADERS = {"User-Agent": "RevistasScopusTool/1.0 (mailto:contacto@example.com)"}


def _count_for_year(issn: str, year: int) -> int | None:
    params = {
        "filter": f"issn:{issn},from-pub-date:{year}-01-01,until-pub-date:{year}-12-31",
        "rows": 0,
    }
    for intento in range(3):
        try:
            resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
            if resp.status_code == 200 and resp.text.strip():
                return resp.json()["message"]["total-results"]
        except requests.RequestException:
            pass
        time.sleep(1)
    return None


def documents_by_year(issn: str, anios_atras: int = 4) -> dict:
    anio_actual = datetime.date.today().year
    anios = list(range(anio_actual - anios_atras, anio_actual + 1))

    historia = []
    for anio in anios:
        conteo = _count_for_year(issn, anio)
        historia.append({"anio": anio, "documentos": conteo})
        time.sleep(0.3)  # ser buen ciudadano con la API pública de Crossref

    if all(h["documentos"] is None for h in historia):
        return {"consultada": False, "motivo": "No se pudo consultar Crossref"}

    return {"consultada": True, "historia": historia, "anio_actual_parcial": anio_actual}
