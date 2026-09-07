#!/usr/bin/env python3
"""Refresca los datos fuente cacheados (Scopus Source List + dataset SCImago) y
publica cada archivo como asset de un GitHub Release, solo si cambió respecto
al último refresh registrado en data/latest.json.

Pensado para correr desde GitHub Actions una vez al mes — ver
.github/workflows/refresh-data.yml. También se puede correr a mano:

    ./.venv/bin/python scripts/refresh_cached_data.py
"""
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sources import scopus_list, scimago  # noqa: E402

BASE_DIR = Path(__file__).resolve().parents[1]
MANIFEST_PATH = BASE_DIR / "data" / "latest.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {}


def _gh_release_upload(tag: str, file_path: Path, asset_name: str) -> str:
    """Crea el release si no existe, sube el asset (reemplazando si ya estaba)
    y devuelve la URL de descarga pública del asset."""
    subprocess.run(
        ["gh", "release", "create", tag, "--title", tag, "--notes", "Refresh automático mensual de datos fuente."],
        cwd=BASE_DIR, check=False,  # no falla si el release ya existe
    )
    subprocess.run(
        ["gh", "release", "upload", tag, f"{file_path}#{asset_name}", "--clobber"],
        cwd=BASE_DIR, check=True,
    )
    repo = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        cwd=BASE_DIR, check=True, capture_output=True, text=True,
    ).stdout.strip()
    return f"https://github.com/{repo}/releases/download/{tag}/{asset_name}"


def refrescar_fuente(nombre: str, ruta_local: Path, manifest: dict) -> dict:
    hash_actual = _sha256(ruta_local)
    entrada_anterior = manifest.get(nombre, {})

    if entrada_anterior.get("sha256") == hash_actual:
        print(f"[{nombre}] sin cambios desde el último refresh ({entrada_anterior.get('actualizado')}).")
        return entrada_anterior

    tag = f"data-{datetime.date.today().strftime('%Y-%m')}"
    url = _gh_release_upload(tag, ruta_local, ruta_local.name)
    entrada = {
        "sha256": hash_actual,
        "actualizado": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "release_tag": tag,
        "url": url,
        "tamano_bytes": ruta_local.stat().st_size,
    }
    print(f"[{nombre}] actualizado -> {url}")
    return entrada


def main():
    manifest = _load_manifest()

    ruta_scopus = scopus_list.download_source_list(force=True)
    manifest["scopus_source_list"] = refrescar_fuente("scopus_source_list", ruta_scopus, manifest)

    ruta_scimago = scimago.download_dataset(force=True)
    manifest["scimago_indicators"] = refrescar_fuente("scimago_indicators", ruta_scimago, manifest)

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nManifiesto actualizado en {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
