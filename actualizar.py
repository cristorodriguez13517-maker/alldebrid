import os
import re
import json
import requests
import unicodedata

from pathlib import Path
from datetime import datetime, timezone
from difflib import SequenceMatcher


# ==========================================================
# CONFIGURACION
# ==========================================================

ALLDEBRID_API_KEY = os.environ["ALLDEBRID_API_KEY"]
TMDB_API_KEY = os.environ["TMDB_API_KEY"]

AD = "https://api.alldebrid.com"
TMDB = "https://api.themoviedb.org/3"
IMAGE = "https://image.tmdb.org/t/p/"

VIDEO_EXTENSIONS = (
    ".mkv", ".mp4", ".avi", ".mov", ".m4v",
    ".ts", ".webm", ".mpg", ".mpeg"
)

HEADERS = {"Authorization": f"Bearer {ALLDEBRID_API_KEY}"}

session = requests.Session()
session.headers.update(HEADERS)

# Alias manuales para nombres de archivo que no contienen el titulo real.
ALIAS_TITULOS = {
    "84114.V1N1": "Vinicius",
}


# ==========================================================
# JSON
# ==========================================================

def leer(nombre, defecto):
    ruta = Path(nombre)

    if not ruta.exists():
        return defecto

    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception as error:
        raise Exception(
            f"No se puede leer {nombre}. No se modificara ningun catalogo: {error}"
        )


def guardar(nombre, datos):
    ruta = Path(nombre)
    temporal = ruta.with_suffix(ruta.suffix + ".tmp")

    temporal.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    temporal.replace(ruta)


# ==========================================================
# ALLDEBRID
# ==========================================================

def normalizar_lista_magnets(elementos):
    if elementos is None:
        return []

    if isinstance(elementos, list):
        lista = elementos
    elif isinstance(elementos, dict):
        if "id" in elementos or "magnet_id" in elementos:
            lista = [elementos]
        else:
            lista = list(elementos.values())
    elif isinstance(elementos, (str, int)):
        lista = [elementos]
    else:
        return []

    resultado = []

    for elemento in lista:
        if isinstance(elemento, dict):
            magnet = dict(elemento)
            magnet_id = magnet.get("id") or magnet.get("magnet_id")

            if magnet_id is None:
                continue
