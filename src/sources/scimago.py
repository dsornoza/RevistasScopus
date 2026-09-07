"""Histórico de SJR/cuartil/h-index/citas promedio por revista.

NOTA IMPORTANTE: scimagojr.com está detrás de Cloudflare y bloquea con 403
cualquier request programático (probado con requests y curl con distintos
User-Agent), incluso su export CSV (`journalrank.php?out=xls`). Por eso esta
herramienta NO scrapea el sitio en vivo. En su lugar usa el dataset comunitario
de Michael E. Rose (github.com/Michael-E-Rose/SCImagoJournalRankIndicators),
que republica los mismos indicadores de SCImago como CSV plano, actualizado
periódicamente (no en tiempo real). Columnas disponibles: Title, field, year,
SJR, h-index, avg_citations, Issn, Sourceid. No incluye cuartil ni volumen de
documentos/año ni % de autocitación de forma directa.

El cuartil ("SJR Best Quartile") SÍ se puede reconstruir: para cada año,
rankeamos el SJR de cada revista contra las demás de su misma categoría ASJC
("field") y la dividimos en 4 franjas iguales — el mismo método que usa
SCImago. Una revista puede estar en varias categorías; tomamos el mejor
cuartil (el número más bajo) entre todas, igual que hace SCImago.
"""
import datetime
from pathlib import Path

import requests
import pandas as pd

CSV_URL = "https://raw.githubusercontent.com/Michael-E-Rose/SCImagoJournalRankIndicators/master/all.csv"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"

_cache = {}


def download_dataset(force: bool = False) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    month_tag = datetime.date.today().strftime("%Y-%m")
    dest = RAW_DIR / f"scimago_indicators_{month_tag}.csv"
    if dest.exists() and not force:
        return dest
    resp = requests.get(CSV_URL, timeout=180)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


AÑOS_DE_HISTORIA = 6  # suficiente para las señales de riesgo y para el gráfico


def _load_dataframe() -> pd.DataFrame:
    if "df" in _cache:
        return _cache["df"]
    path = download_dataset()
    anio_minimo = datetime.date.today().year - AÑOS_DE_HISTORIA

    # El CSV completo tiene ~1M de filas (1999-hoy) y con los dtypes por defecto
    # de pandas el pico de memoria durante el parseo se acerca a los 512MB del
    # plan free de Render. Leemos por chunks, descartamos años que no usamos y
    # bajamos los dtypes ANTES de concatenar, para no tener nunca el dataset
    # completo sin optimizar en memoria a la vez.
    columnas = ["Title", "field", "year", "SJR", "h-index", "avg_citations", "Issn"]
    dtypes_compactos = {
        "field": "category",
        "year": "int16",
        "SJR": "float32",
        "h-index": "float32",
        "avg_citations": "float32",
    }
    partes = []
    for chunk in pd.read_csv(path, usecols=columnas, dtype={"Issn": str}, chunksize=150_000):
        chunk = chunk[chunk["year"] >= anio_minimo]
        if chunk.empty:
            continue
        for col, dtype in dtypes_compactos.items():
            chunk[col] = chunk[col].astype(dtype)
        partes.append(chunk)

    df = pd.concat(partes, ignore_index=True)
    partes.clear()
    df["Title"] = df["Title"].astype("category")
    df["Issn"] = df["Issn"].str.strip()

    # Cuartil reconstruido: rank percentil del SJR dentro de cada (field, year).
    rank_pct = df.groupby(["field", "year"], observed=True)["SJR"].rank(pct=True, ascending=False)
    df["quartile"] = pd.cut(
        rank_pct, bins=[0, 0.25, 0.5, 0.75, 1.0], labels=[1, 2, 3, 4], include_lowest=True
    ).astype("Int8")

    # Índice ISSN normalizado -> posiciones de fila, construido una sola vez.
    # Evita repetir un .apply() sobre las ~700k filas en cada chequeo de revista.
    indice = {}
    for pos, celda in enumerate(df["Issn"].fillna("")):
        for parte in celda.split(","):
            norm = _normalize_issn(parte)
            if norm:
                indice.setdefault(norm, []).append(pos)

    _cache["df"] = df
    _cache["indice_issn"] = indice
    return df


def _normalize_issn(issn: str) -> str:
    return "".join(ch for ch in (issn or "") if ch.isalnum()).upper()


def lookup_history(issn: str) -> dict:
    """Devuelve la serie histórica de SJR/h-index/avg_citations para un ISSN."""
    df = _load_dataframe()
    target = _normalize_issn(issn)
    if not target:
        return {"encontrada": False, "motivo": "ISSN vacío o inválido"}

    posiciones = _cache["indice_issn"].get(target, [])
    subset_todas_categorias = df.iloc[posiciones]
    if subset_todas_categorias.empty:
        return {
            "encontrada": False,
            "motivo": "ISSN no está en el dataset comunitario de SCImago "
            "(puede ser una revista nueva, o revisar manualmente en scimagojr.com)",
        }

    # Mejor cuartil por año entre todas las categorías ASJC de la revista.
    mejor_cuartil_por_anio = (
        subset_todas_categorias.groupby("year")["quartile"].min().to_dict()
    )

    subset = subset_todas_categorias.drop_duplicates(subset=["year"]).sort_values("year")
    historia = [
        {
            "anio": int(row["year"]),
            "sjr": None if pd.isna(row["SJR"]) else float(row["SJR"]),
            "cuartil": None
            if pd.isna(mejor_cuartil_por_anio.get(row["year"]))
            else int(mejor_cuartil_por_anio[row["year"]]),
            "h_index": None if pd.isna(row["h-index"]) else int(row["h-index"]),
            "avg_citations": None if pd.isna(row["avg_citations"]) else float(row["avg_citations"]),
        }
        for _, row in subset.iterrows()
    ]
    titulo = subset.iloc[-1]["Title"]
    return {
        "encontrada": True,
        "titulo": titulo,
        "marcado_discontinued": "discontinued" in titulo.lower(),
        "historia": historia,
    }
