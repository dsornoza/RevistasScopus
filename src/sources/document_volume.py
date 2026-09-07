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
from concurrent.futures import ThreadPoolExecutor

import requests

API_URL = "https://api.crossref.org/v1/works"
HEADERS = {"User-Agent": "RevistasScopusTool/1.0 (mailto:contacto@example.com)"}
TIMEOUT_SEGUNDOS = 8
REINTENTOS = 2


def _count_for_year(issn: str, year: int) -> int | None:
    params = {
        "filter": f"issn:{issn},from-pub-date:{year}-01-01,until-pub-date:{year}-12-31",
        "rows": 0,
    }
    for intento in range(REINTENTOS):
        try:
            resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=TIMEOUT_SEGUNDOS)
            if resp.status_code == 200 and resp.text.strip():
                return resp.json()["message"]["total-results"]
        except requests.RequestException:
            pass
        if intento < REINTENTOS - 1:
            time.sleep(0.5)
    return None


def documents_by_year(issn: str, anios_atras: int = 4) -> dict:
    anio_actual = datetime.date.today().year
    anios = list(range(anio_actual - anios_atras, anio_actual + 1))

    # Las 5 consultas (una por año) son independientes: las lanzamos en paralelo
    # en vez de secuenciales para no acumular latencia si Crossref responde lento.
    with ThreadPoolExecutor(max_workers=len(anios)) as executor:
        conteos = list(executor.map(lambda anio: _count_for_year(issn, anio), anios))

    historia = [{"anio": anio, "documentos": conteo} for anio, conteo in zip(anios, conteos)]

    if all(h["documentos"] is None for h in historia):
        return {"consultada": False, "motivo": "No se pudo consultar Crossref"}

    return {"consultada": True, "historia": historia, "anio_actual_parcial": anio_actual}
