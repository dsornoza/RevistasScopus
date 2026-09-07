"""Descarga y consulta el Scopus Source List oficial (Elsevier).

El listado se publica sin login en elsevier.com/products/scopus/content como un
.xlsx cuyo nombre de archivo cambia cada mes (ej. ext_list_Jul_2026.xlsx), así
que primero resolvemos la URL actual parseando esa página.
"""
import re
import datetime
from pathlib import Path

import requests
import pandas as pd

CONTENT_PAGE_URL = "https://www.elsevier.com/products/scopus/content"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
XLSX_LINK_RE = re.compile(r"(https?:)?//downloads\.ctfassets\.net/[^\"'\s]+\.xlsx", re.IGNORECASE)

_cache = {}


def _resolve_current_xlsx_url() -> str:
    resp = requests.get(CONTENT_PAGE_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    match = XLSX_LINK_RE.search(resp.text)
    if not match:
        raise RuntimeError(
            "No se pudo encontrar el enlace de descarga del Scopus Source List "
            f"en {CONTENT_PAGE_URL}. La página pudo haber cambiado de estructura."
        )
    url = match.group(0)
    if url.startswith("//"):
        url = "https:" + url
    return url


def download_source_list(force: bool = False) -> Path:
    """Descarga (o reutiliza si ya existe) el xlsx del mes actual."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    month_tag = datetime.date.today().strftime("%Y-%m")
    dest = RAW_DIR / f"scopus_source_list_{month_tag}.xlsx"
    if dest.exists() and not force:
        return dest

    url = _resolve_current_xlsx_url()
    resp = requests.get(url, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def _load_dataframe() -> pd.DataFrame:
    if "df" in _cache:
        return _cache["df"]
    path = download_source_list()
    # El archivo trae varias hojas (Sources, Accepted Titles, Discontinued Titles,
    # Conference Proceedings, etc). La que necesitamos es la que tiene la columna
    # "Active or Inactive"; no asumimos que sea la de más filas (esa suele ser la
    # de conference proceedings).
    sheets = pd.read_excel(path, sheet_name=None, dtype=str)
    df = None
    for sheet_df in sheets.values():
        cols_lower = [str(c).strip().lower() for c in sheet_df.columns]
        if any("active" in c and "inactive" in c for c in cols_lower):
            df = sheet_df
            break
    if df is None:
        raise RuntimeError(
            "No se encontró la hoja principal de 'Scopus Sources' (con columna "
            "'Active or Inactive') en el xlsx descargado. Revisar estructura del archivo."
        )
    df.columns = [str(c).strip() for c in df.columns]
    _cache["df"] = df
    return df


def _find_column(df: pd.DataFrame, *keywords: str):
    for col in df.columns:
        low = col.lower()
        if all(k in low for k in keywords):
            return col
    return None


def _normalize_issn(issn: str) -> str:
    return re.sub(r"[^0-9Xx]", "", issn or "").upper()


def lookup_by_issn(issn: str) -> dict:
    """Busca una revista por ISSN (impreso o electrónico) en el Scopus Source List."""
    df = _load_dataframe()
    target = _normalize_issn(issn)
    if not target:
        return {"encontrada": False, "motivo": "ISSN vacío o inválido"}

    issn_cols = [c for c in df.columns if "issn" in c.lower()]
    title_col = _find_column(df, "source", "title") or _find_column(df, "title")
    status_col = _find_column(df, "active") or _find_column(df, "status") or _find_column(df, "inactive")
    coverage_col = _find_column(df, "coverage")
    publisher_col = _find_column(df, "publisher")
    sourcerecord_col = _find_column(df, "sourcerecord")

    for _, row in df.iterrows():
        for col in issn_cols:
            val = _normalize_issn(str(row.get(col, "")))
            if val and val == target:
                return {
                    "encontrada": True,
                    "titulo": row.get(title_col) if title_col else None,
                    "estado": row.get(status_col) if status_col else None,
                    "cobertura": row.get(coverage_col) if coverage_col else None,
                    "editorial": row.get(publisher_col) if publisher_col else None,
                    "sourcerecord_id": row.get(sourcerecord_col) if sourcerecord_col else None,
                    "fuente_fecha": download_source_list().stat().st_mtime,
                }
    return {"encontrada": False, "motivo": "ISSN no aparece en el Scopus Source List actual"}
