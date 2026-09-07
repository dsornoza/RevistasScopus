"""Lógica compartida entre check_journal.py y monitor_watchlist.py."""
import datetime
import json
from pathlib import Path

from sources import scopus_list, scimago, retractions, document_volume
from risk_score import compute_score, NIVELES

BASE_DIR = Path(__file__).resolve().parent.parent
HISTORY_DIR = BASE_DIR / "data" / "history"
WATCHLIST_PATH = BASE_DIR / "watchlist.json"


def evaluate_journal(issn: str, nombre: str = "") -> dict:
    scopus_info = scopus_list.lookup_by_issn(issn)
    scimago_info = scimago.lookup_history(issn)
    retractions_info = retractions.recent_retractions(issn)
    volumen_info = document_volume.documents_by_year(issn)
    score = compute_score(scopus_info, scimago_info, retractions_info, volumen_info)

    nivel = score["nivel"]
    razones = list(score["razones"])

    # Cambio de editorial respecto al último chequeo: señal barata (ya la teníamos
    # guardada) de que la revista pudo haber cambiado de manos, otro patrón descrito
    # en revistas bajo revisión CSAB.
    anterior = last_snapshot(issn)
    if anterior:
        editorial_anterior = (
            anterior.get("detalle", {}).get("scopus", {}).get("editorial") or ""
        ).strip()
        editorial_actual = (scopus_info.get("editorial") or "").strip()
        if editorial_anterior and editorial_actual and editorial_anterior != editorial_actual:
            if NIVELES.index("Medio-alto") > NIVELES.index(nivel):
                nivel = "Medio-alto"
            razones.append(
                f"La editorial cambió de '{editorial_anterior}' a '{editorial_actual}' "
                "desde el último chequeo."
            )

    return {
        "issn": issn,
        "nombre": nombre or scopus_info.get("titulo") or scimago_info.get("titulo") or issn,
        "fecha_chequeo": datetime.datetime.now().isoformat(timespec="seconds"),
        "score": nivel,
        "razones": razones,
        "detalle": {
            "scopus": scopus_info,
            "scimago": scimago_info,
            "retractions": retractions_info,
            "volumen": volumen_info,
        },
    }


def save_snapshot(resultado: dict) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = HISTORY_DIR / f"{resultado['issn']}.jsonl"
    entry = {
        "fecha_chequeo": resultado["fecha_chequeo"],
        "score": resultado["score"],
        "razones": resultado["razones"],
        "detalle": resultado.get("detalle", {}),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def last_snapshot(issn: str) -> dict | None:
    path = HISTORY_DIR / f"{issn}.jsonl"
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return None
    return json.loads(lines[-1])


def _normalize_issn(issn: str) -> str:
    return "".join(ch for ch in (issn or "") if ch.isalnum()).upper()


def load_watchlist() -> list:
    if not WATCHLIST_PATH.exists():
        return []
    data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
    revistas = data.get("revistas", [])
    # Ignora la entrada de ejemplo que trae el proyecto por defecto.
    return [r for r in revistas if _normalize_issn(r.get("issn")) != "00000000"]


def save_watchlist(revistas: list) -> None:
    WATCHLIST_PATH.write_text(
        json.dumps({"revistas": revistas}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add_journal(issn: str, nombre: str = "", editorial: str = "", notas: str = "") -> dict:
    issn = issn.strip()
    target = _normalize_issn(issn)
    revistas = load_watchlist()
    for r in revistas:
        if _normalize_issn(r.get("issn")) == target:
            return r  # ya estaba en la watchlist
    entry = {
        "nombre": nombre.strip(),
        "issn": issn,
        "editorial": editorial.strip(),
        "fecha_publicacion_propia": "",
        "notas": notas.strip(),
    }
    revistas.append(entry)
    save_watchlist(revistas)
    return entry


def update_journal_nombre(issn: str, nombre: str) -> None:
    target = _normalize_issn(issn)
    revistas = load_watchlist()
    for r in revistas:
        if _normalize_issn(r.get("issn")) == target and not r.get("nombre"):
            r["nombre"] = nombre
    save_watchlist(revistas)


def remove_journal(issn: str) -> None:
    target = _normalize_issn(issn)
    revistas = [r for r in load_watchlist() if _normalize_issn(r.get("issn")) != target]
    save_watchlist(revistas)
