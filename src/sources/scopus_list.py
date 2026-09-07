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


def _find_column(columnas, *keywords: str):
    for col in columnas:
        low = str(col).strip().lower()
        if all(k in low for k in keywords):
            return col
    return None


def _load_dataframe() -> pd.DataFrame:
    if "df" in _cache:
        return _cache["df"]
    path = download_source_list()
    # El archivo trae varias hojas (Sources, Accepted Titles, Discontinued Titles,
    # Conference Proceedings —esta última con ~180k filas que no usamos—, etc) y
    # la hoja de Sources sola trae 52 columnas, de las que solo usamos 7 (el resto
    # son flags de categoría ASJC). En un hosting con poca RAM (Render free,
    # 512MB) cargar todo eso de más casi agota la memoria, así que:
    #  1. leemos cada hoja SOLO con nrows=0 para ver sus columnas (barato) hasta
    #     encontrar la que tiene "Active or Inactive",
    #  2. recién ahí releemos esa hoja completa pero con usecols limitado a las
    #     columnas que realmente necesitamos.
    df = None
    with pd.ExcelFile(path, engine="openpyxl", engine_kwargs={"read_only": True}) as libro:
        for nombre_hoja in libro.sheet_names:
            header = pd.read_excel(libro, sheet_name=nombre_hoja, nrows=0)
            cols_lower = [str(c).strip().lower() for c in header.columns]
            if not any("active" in c and "inactive" in c for c in cols_lower):
                continue

            necesarias = [
                c
                for c in [
                    _find_column(header.columns, "sourcerecord"),
                    _find_column(header.columns, "source", "title") or _find_column(header.columns, "title"),
                    _find_column(header.columns, "active"),
                    _find_column(header.columns, "coverage"),
                    _find_column(header.columns, "publisher"),
                ]
                if c
            ] + [c for c in header.columns if "issn" in str(c).lower()]

            df = pd.read_excel(libro, sheet_name=nombre_hoja, dtype=str, usecols=necesarias)
            break
    if df is None:
        raise RuntimeError(
            "No se encontró la hoja principal de 'Scopus Sources' (con columna "
            "'Active or Inactive') en el xlsx descargado. Revisar estructura del archivo."
        )
    df.columns = [str(c).strip() for c in df.columns]

    # Índice ISSN normalizado -> posición de fila, construido una sola vez
    # (evita un df.iterrows() sobre las ~49k filas en cada chequeo de revista).
    issn_cols = [c for c in df.columns if "issn" in c.lower()]
    indice = {}
    for pos in range(len(df)):
        for col in issn_cols:
            norm = _normalize_issn(str(df.iat[pos, df.columns.get_loc(col)]))
            if norm:
                indice.setdefault(norm, pos)

    _cache["df"] = df
    _cache["indice_issn"] = indice
    return df


def _normalize_issn(issn: str) -> str:
    return re.sub(r"[^0-9Xx]", "", issn or "").upper()


def lookup_by_issn(issn: str) -> dict:
    """Busca una revista por ISSN (impreso o electrónico) en el Scopus Source List."""
    df = _load_dataframe()
    target = _normalize_issn(issn)
    if not target:
        return {"encontrada": False, "motivo": "ISSN vacío o inválido"}

    pos = _cache["indice_issn"].get(target)
    if pos is None:
        return {"encontrada": False, "motivo": "ISSN no aparece en el Scopus Source List actual"}

    row = df.iloc[pos]
    title_col = _find_column(df.columns, "source", "title") or _find_column(df.columns, "title")
    status_col = _find_column(df.columns, "active")
    coverage_col = _find_column(df.columns, "coverage")
    publisher_col = _find_column(df.columns, "publisher")
    sourcerecord_col = _find_column(df.columns, "sourcerecord")

    return {
        "encontrada": True,
        "titulo": row.get(title_col) if title_col else None,
        "estado": row.get(status_col) if status_col else None,
        "cobertura": row.get(coverage_col) if coverage_col else None,
        "editorial": row.get(publisher_col) if publisher_col else None,
        "sourcerecord_id": row.get(sourcerecord_col) if sourcerecord_col else None,
        "fuente_fecha": download_source_list().stat().st_mtime,
    }
