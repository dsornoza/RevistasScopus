"""Consulta retractaciones recientes de una revista vía la API de Crossref.

Desde 2023 Crossref integró la base de Retraction Watch; se puede filtrar
directamente por ISSN y update-type:retraction sin necesidad de scraping
ni API key.
"""
import datetime

import requests

API_URL = "https://api.crossref.org/v1/works"


def recent_retractions(issn: str, months: int = 24) -> dict:
    params = {
        "filter": f"issn:{issn},update-type:retraction",
        "rows": 100,
    }
    try:
        resp = requests.get(API_URL, params=params, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        return {"consultada": False, "motivo": str(exc)}

    items = resp.json().get("message", {}).get("items", [])
    cutoff = datetime.date.today() - datetime.timedelta(days=30 * months)

    recientes = []
    for item in items:
        parts = item.get("issued", {}).get("date-parts", [[None]])[0]
        if not parts or parts[0] is None:
            continue
        year = parts[0]
        month = parts[1] if len(parts) > 1 else 1
        day = parts[2] if len(parts) > 2 else 1
        try:
            fecha = datetime.date(year, month, day)
        except ValueError:
            continue
        if fecha >= cutoff:
            recientes.append({"titulo": item.get("title", [None])[0], "fecha": fecha.isoformat()})

    return {"consultada": True, "total_historico": len(items), "recientes": recientes}
