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

            magnet["id"] = str(magnet_id)
            resultado.append(magnet)

        elif isinstance(elemento, (str, int)):
            magnet_id = str(elemento).strip()

            if magnet_id:
                resultado.append({
                    "id": magnet_id,
                    "filename": magnet_id
                })

    return resultado


def alldebrid(endpoint, datos=None):
    respuesta = session.post(
        AD + endpoint,
        data=datos or {},
        timeout=60
    )
    respuesta.raise_for_status()

    resultado = respuesta.json()

    if not isinstance(resultado, dict):
        raise Exception(f"Respuesta inesperada de AllDebrid: {resultado}")

    if resultado.get("status") != "success":
        raise Exception(f"Error AllDebrid: {resultado}")

    return resultado.get("data", {})


def obtener_magnets():
    data = alldebrid(
        "/v4.1/magnet/status",
        {"status": "ready"}
    )
    return normalizar_lista_magnets(data.get("magnets", []))


def recorrer_archivos(elementos, ruta=""):
    encontrados = []

    if not isinstance(elementos, list):
        return encontrados

    for elemento in elementos:
        if not isinstance(elemento, dict):
            continue

        nombre = elemento.get("n", "")
        if not nombre:
            continue

        ruta_actual = f"{ruta}/{nombre}".strip("/")
        hijos = elemento.get("e")

        if isinstance(hijos, list):
            encontrados.extend(recorrer_archivos(hijos, ruta_actual))
            continue

        if nombre.lower().endswith(VIDEO_EXTENSIONS):
            encontrados.append({
                "name": nombre,
                "path": ruta_actual,
                "size": elemento.get("s", 0),
                "url": elemento.get("l", "")
            })

    return encontrados


def obtener_archivos(magnet_id):
    data = alldebrid(
        "/v4/magnet/files",
        {"id[]": magnet_id}
    )

    magnets = normalizar_lista_magnets(data.get("magnets", []))

    for magnet in magnets:
        if str(magnet.get("id")) == str(magnet_id):
            return recorrer_archivos(magnet.get("files", []))

    print("No se encontraron archivos para el magnet:", magnet_id)
    return []


def fecha_incorporacion(magnet):
    valor = (
        magnet.get("uploadDate")
        or magnet.get("upload_date")
        or magnet.get("date")
    )

    if valor:
        try:
            if isinstance(valor, (int, float)):
                return datetime.fromtimestamp(
                    valor, timezone.utc
                ).isoformat()
            return str(valor)
        except Exception:
            pass

    return datetime.now(timezone.utc).isoformat()


# ==========================================================
# TITULOS: LIMPIEZA Y EXTRACCION DEL ANO
# ==========================================================

def clave_archivo(magnet_id, archivo):
    return str(magnet_id) + "|" + str(archivo["path"])


def normalizar(texto):
    texto = unicodedata.normalize("NFD", str(texto).lower())
    texto = "".join(
        c for c in texto
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]", "", texto)


def extraer_anio(*textos):
    for texto in textos:
        if not texto:
            continue

        coincidencias = re.findall(
            r"(?<!\d)((?:19|20)\d{2})(?!\d)",
            str(texto)
        )

        for valor in coincidencias:
            anio = int(valor)
            if 1900 <= anio <= 2035:
                return anio

    return None


def limpiar_titulo(texto):
    texto = Path(str(texto)).stem

    # Eliminar direcciones web y dominios.
    texto = re.sub(
        r"(?i)www\.[^\s]+|https?://[^\s]+",
        " ",
        texto
    )
    texto = re.sub(
        r"(?i)\b[a-z0-9-]+\.(?:com|net|org|es|info)\b",
        " ",
        texto
    )

    # Eliminar etiquetas tecnicas entre corchetes.
    texto = re.sub(r"\[.*?\]|\{.*?\}", " ", texto)

    # Eliminar anos: nunca deben convertirse en candidatos de busqueda.
    texto = re.sub(
        r"(?<!\d)(?:19|20)\d{2}(?!\d)",
        " ",
        texto
    )

    patrones = [
        r"(?i)\b\d{3,4}p\b",
        r"(?i)\b4k\d*\b",
        r"(?i)\b2160\b",
        r"(?i)\buhd\b",
        r"(?i)\bfhd\b",
        r"(?i)\bhd\b",
        r"(?i)\bbluray\b",
        r"(?i)\bbrrip\b",
        r"(?i)\bwebrip\b",
        r"(?i)\bweb[- ]?dl\b",
        r"(?i)\bweb\b",
        r"(?i)\bhdr10?\+?\b",
        r"(?i)\bhdr\b",
        r"(?i)\bremux\b",
        r"(?i)\bx264\b|\bx265\b",
        r"(?i)\bh264\b|\bh265\b",
        r"(?i)\bhevc\b|\bav1\b",
        r"(?i)\bac3\b|\bdts(?:-hd)?\b",
        r"(?i)\btrue\s*hd\b",
        r"(?i)\batmos\b|\baac\b|\bflac\b",
        r"(?i)\b\d+(?:\.\d+)?\s*ch\b",
        r"(?i)\b\d\.\d\b",
        r"(?i)\bcastellano\b|\bespañol\b",
        r"(?i)\bingles\b|\benglish\b",
        r"(?i)\bsubs\b|\bsubtitulos\b",
        r"(?i)\bproper\b|\brepack\b",
        r"(?i)\bextended\b",
        r"(?i)\bdirectors cut\b",
        r"(?i)\bes-en\b|\ben-es\b",
    ]

    for patron in patrones:
        texto = re.sub(patron, " ", texto)

    texto = re.sub(r"[._]+", " ", texto)
    texto = re.sub(r"[-]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto)

    return texto.strip(" -_.")


def titulo_alias(texto):
    compacto = normalizar(Path(str(texto)).stem)

    for clave, titulo in ALIAS_TITULOS.items():
        if normalizar(clave) in compacto:
            return titulo

    return None


def obtener_titulos_candidatos(archivo, nombre_magnet=""):
    candidatos = []

    nombres = [
        archivo.get("name", ""),
        nombre_magnet
    ]

    # Alias conocidos.
    for nombre in nombres:
        if nombre:
            alias = titulo_alias(nombre)
            if alias:
                candidatos.append(alias)

    for nombre in nombres:
        if not nombre:
            continue

        base = Path(str(nombre)).stem

        # Quitar etiquetas tecnicas, pero conservar parentesis con titulos.
        base_sin_tags = re.sub(r"\[.*?\]|\{.*?\}", " ", base)

        # Un parentesis que solo contiene un ano NO es un titulo original.
        originales = re.findall(r"\(([^()]*)\)", base_sin_tags)

        for original in originales:
            if re.fullmatch(r"\s*(?:19|20)\d{2}\s*", original):
                continue

            limpio_original = limpiar_titulo(original)

            if limpio_original and len(normalizar(limpio_original)) >= 3:
                candidatos.append(limpio_original)

        # El titulo principal se busca antes que el titulo entre parentesis.
        principal = re.sub(r"\([^()]*\)", " ", base_sin_tags)
        limpio_principal = limpiar_titulo(principal)

        if limpio_principal and len(normalizar(limpio_principal)) >= 3:
            candidatos.append(limpio_principal)

    resultado = []
    vistos = set()

    for titulo in candidatos:
        clave = normalizar(titulo)

        # Evitar candidatos como "2026", "4K" o cadenas demasiado cortas.
        if len(clave) < 3 or clave.isdigit():
            continue

        if clave not in vistos:
            vistos.add(clave)
            resultado.append(titulo)

    return resultado


def calidad(texto):
    texto = str(texto).lower()

    if re.search(r"4k|2160p|uhd", texto):
        return "4K"
    if re.search(r"fhd|1080p|full hd", texto):
        return "FHD"
    if re.search(r"720p|\bhd\b", texto):
        return "HD"

    return ""


# ==========================================================
# TMDB: BUSQUEDA CON COMPROBACION DE TITULO Y ANO
# ==========================================================

def tmdb_get(endpoint, params=None):
    parametros = {
        "api_key": TMDB_API_KEY,
        "language": "es-ES"
    }

    if params:
        parametros.update(params)

    respuesta = requests.get(
        TMDB + endpoint,
        params=parametros,
        timeout=30
    )
    respuesta.raise_for_status()
    return respuesta.json()


def similitud_titulo(busqueda, nombre):
    a = normalizar(busqueda)
    b = normalizar(nombre)

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    ratio = SequenceMatcher(None, a, b).ratio()

    # Complementar la comparacion con palabras para titulos largos.
    palabras_a = set(re.findall(r"[a-z0-9]+", str(busqueda).lower()))
    palabras_b = set(re.findall(r"[a-z0-9]+", str(nombre).lower()))

    if palabras_a and palabras_b:
        interseccion = len(palabras_a & palabras_b)
        union = len(palabras_a | palabras_b)
        jaccard = interseccion / union if union else 0
        ratio = max(ratio, jaccard)

    return ratio


def fecha_resultado(item, tipo):
    if tipo == "movie":
        return item.get("release_date", "")
    return item.get("first_air_date", "")


def puntuar_resultado(titulo_busqueda, item, tipo, anio=None):
    if tipo == "movie":
        nombres = [
            item.get("title", ""),
            item.get("original_title", "")
        ]
    else:
        nombres = [
            item.get("name", ""),
            item.get("original_name", "")
        ]

    puntuacion = max(
        [similitud_titulo(titulo_busqueda, n) for n in nombres if n]
        or [0.0]
    )

    fecha = fecha_resultado(item, tipo)
    anio_resultado = None

    if fecha and len(fecha) >= 4 and fecha[:4].isdigit():
        anio_resultado = int(fecha[:4])

    # Si el archivo indica ano, se exige que TMDB no se aleje demasiado.
    if anio and anio_resultado:
        diferencia = abs(anio - anio_resultado)

        if diferencia > 1:
            return 0.0

        if diferencia == 1:
            puntuacion -= 0.08

    elif anio and not anio_resultado:
        puntuacion -= 0.05

    return puntuacion


def buscar_tmdb(titulo, tipo, anio=None):
    endpoint = "/search/movie" if tipo == "movie" else "/search/tv"

    consultas = []

    # Primera busqueda con ano cuando se conoce.
    if anio:
        if tipo == "movie":
            consultas.append({"year": anio})
        else:
            consultas.append({"first_air_date_year": anio})

    # Segunda busqueda sin ano para no perder titulos con fechas distintas.
    consultas.append({})

    todos = {}

    for extras in consultas:
        parametros = {
            "query": titulo,
            "include_adult": "false",
            **extras
        }

        try:
            resultados = tmdb_get(endpoint, parametros).get("results", [])
        except Exception as error:
            print("Error consultando TMDB:", error)
            continue

        for item in resultados:
            if isinstance(item, dict) and item.get("id"):
                todos[item["id"]] = item

    mejor = None
    mejor_puntuacion = 0.0

    for item in todos.values():
        puntuacion = puntuar_resultado(
            titulo,
            item,
            tipo,
            anio
        )

        if puntuacion > mejor_puntuacion:
            mejor = item
            mejor_puntuacion = puntuacion

    # Umbral alto: es preferible dejar una ficha pendiente a mostrar otra pelicula.
    if mejor is None or mejor_puntuacion < 0.72:
        print(
            "TMDB: coincidencia rechazada para",
            repr(titulo),
            "| puntuacion:",
            round(mejor_puntuacion, 3)
        )
        return None

    nombre = (
        mejor.get("title") or mejor.get("name") or ""
    )

    print(
        "TMDB: coincidencia aceptada:",
        nombre,
        "| puntuacion:",
        round(mejor_puntuacion, 3)
    )

    return mejor


def buscar_tmdb_candidatos(candidatos, tipo, anio=None):
    mejor = None
    mejor_puntuacion = 0.0

    for titulo in candidatos:
        if not titulo:
            continue

        print("Buscando en TMDB:", titulo, "| ano:", anio or "no indicado")

        resultado = buscar_tmdb(titulo, tipo, anio)

        if not resultado:
            continue

        puntuacion = puntuar_resultado(
            titulo,
            resultado,
            tipo,
            anio
        )

        if puntuacion > mejor_puntuacion:
            mejor = resultado
            mejor_puntuacion = puntuacion

    return mejor


def imagen(ruta, tamano="w780"):
    return IMAGE + tamano + ruta if ruta else ""


def edad_pelicula(tmdb_id):
    try:
        datos = tmdb_get(f"/movie/{tmdb_id}/release_dates")

        for pais in datos.get("results", []):
            if pais.get("iso_3166_1") == "ES":
                for fecha in pais.get("release_dates", []):
                    valor = fecha.get("certification")
                    if valor:
                        return valor + "+"

    except Exception:
        pass

    return ""


def edad_serie(tmdb_id):
    try:
        datos = tmdb_get(f"/tv/{tmdb_id}/content_ratings")

        for pais in datos.get("results", []):
            if pais.get("iso_3166_1") == "ES":
                valor = pais.get("rating", "")
                if valor:
                    return valor + "+"

    except Exception:
        pass

    return ""


def buscar_logo(tipo, tmdb_id):
    try:
        datos = tmdb_get(
            f"/{tipo}/{tmdb_id}/images",
            {"include_image_language": "es,en,null"}
        )

        logos = datos.get("logos", [])

        if logos:
            elegido = next(
                (x for x in logos if x.get("iso_639_1") == "es"),
                logos[0]
            )
            return imagen(elegido.get("file_path"), "w780")

    except Exception:
        pass

    return ""


# ==========================================================
# FICHA DE PELICULA
# ==========================================================

def construir_datos_tmdb_pelicula(resultado, titulo_fallback):
    tmdb_id = resultado["id"]
    detalles = tmdb_get(f"/movie/{tmdb_id}")

    return {
        "title": detalles.get("title") or titulo_fallback,
        "tmdb_id": tmdb_id,
        "poster": imagen(detalles.get("poster_path"), "w780"),
        "backdrop": imagen(detalles.get("backdrop_path"), "original"),
        "logo": buscar_logo("movie", tmdb_id),
        "overview": detalles.get("overview", ""),
        "release_date": detalles.get("release_date", ""),
        "runtime": detalles.get("runtime", 0),
        "genres": [
            x["name"] for x in detalles.get("genres", [])
        ],
        "age_rating": edad_pelicula(tmdb_id),
        "match_status": "encontrada"
    }


def datos_pelicula(archivo, magnet_id, nombre_magnet="", added_at=""):
    candidatos = obtener_titulos_candidatos(archivo, nombre_magnet)
    anio = extraer_anio(nombre_magnet, archivo.get("path"), archivo.get("name"))

    if not candidatos:
        print("No se pudo extraer el titulo:", archivo.get("name"))
        return None

    print("Titulos candidatos:", candidatos, "| ano:", anio or "no indicado")

    resultado = buscar_tmdb_candidatos(
        candidatos,
        "movie",
        anio
    )

    if not resultado:
        print("Pelicula sin coincidencia fiable:", candidatos)
        return None

    ficha = construir_datos_tmdb_pelicula(
        resultado,
        candidatos[0]
    )

    ficha.update({
        "magnet_id": str(magnet_id),
        "file_path": archivo["path"],
        "stream_url": archivo.get("url", ""),
        "quality": calidad(
            archivo.get("name", "") + " " + nombre_magnet
        ),
        "added_at": added_at,
        "source_name": nombre_magnet,
    })

    return ficha


# ==========================================================
# SERIES Y EPISODIOS
# ==========================================================

def detectar_episodio(nombre):
    nombre_original = Path(nombre).stem

    patron = re.search(
        r"(?i)(.*?)(?:S(\d{1,2})E(\d{1,3})|(\d{1,2})x(\d{1,3}))",
        nombre_original
    )

    if patron:
        serie = limpiar_titulo(patron.group(1))
        temporada = int(patron.group(2) or patron.group(4))
        episodio = int(patron.group(3) or patron.group(5))

        if serie:
            return {
                "serie": serie,
                "temporada": temporada,
                "episodio": episodio
            }

    patron = re.search(
        r"(?i)^(.*?)\s*\[?\s*(?:cap(?:itulo)?|episodio|ep)\.?\s*(\d{3,4})\s*\]?",
        nombre_original
    )

    if patron:
        serie = limpiar_titulo(patron.group(1))
        numero = patron.group(2)

        if serie:
            temporada = int(numero[:-2])
            episodio = int(numero[-2:])

            if temporada > 0 and episodio > 0:
                return {
                    "serie": serie,
                    "temporada": temporada,
                    "episodio": episodio
                }

    return None


def datos_serie(titulo, anio=None):
    resultado = buscar_tmdb_candidatos(
        [titulo],
        "tv",
        anio
    )

    if not resultado:
        print("Serie sin coincidencia fiable:", titulo)
        return None

    tmdb_id = resultado["id"]
    detalles = tmdb_get(f"/tv/{tmdb_id}")

    return {
        "id": tmdb_id,
        "tmdb_id": tmdb_id,
        "title": detalles.get("name", titulo),
        "poster": imagen(detalles.get("poster_path"), "w780"),
        "backdrop": imagen(detalles.get("backdrop_path"), "original"),
        "logo": buscar_logo("tv", tmdb_id),
        "overview": detalles.get("overview", ""),
        "first_air_date": detalles.get("first_air_date", ""),
        "genres": [
            x["name"] for x in detalles.get("genres", [])
        ],
        "age_rating": edad_serie(tmdb_id),
        "number_of_seasons": detalles.get("number_of_seasons", 0),
        "quality": ""
    }


def obtener_datos_episodio(tmdb_id, temporada, episodio):
    try:
        datos = tmdb_get(
            f"/tv/{tmdb_id}/season/{temporada}/episode/{episodio}"
        )

        return {
            "titulo": datos.get("name", f"Episodio {episodio}"),
            "sinopsis": datos.get("overview", ""),
            "imagen": imagen(datos.get("still_path"), "w500")
        }

    except Exception:
        return {
            "titulo": f"Episodio {episodio}",
            "sinopsis": "",
            "imagen": ""
        }


# ==========================================================
# REPARAR FICHAS ANTIGUAS SIN TOCAR LOS ENLACES
# ==========================================================

def reparar_peliculas_existentes(peliculas):
    reparadas = 0
    sin_coincidencia = 0

    for pelicula in peliculas:
        if not isinstance(pelicula, dict):
            continue

        fuente = pelicula.get("source_name") or pelicula.get("file_path", "")
        ruta = pelicula.get("file_path", "")
        nombre_archivo = Path(ruta).name if ruta else fuente

        archivo = {
            "name": nombre_archivo,
            "path": ruta,
            "url": pelicula.get("stream_url", "")
        }

        candidatos = obtener_titulos_candidatos(
            archivo,
            fuente
        )

        anio = extraer_anio(fuente, ruta)

        titulo_actual = str(pelicula.get("title", "")).strip()
        ficha_generica = (
            not titulo_actual
            or titulo_actual.isdigit()
            or normalizar(titulo_actual) in ("2026", "2025", "2024")
        )

        # Las fichas que tienen titulo correcto no se reescriben.
        # Las fichas genericas (por ejemplo, "2026") se vuelven a identificar.
        if not ficha_generica:
            continue

        if not candidatos:
            continue

        print(
            "Revisando ficha antigua:",
            fuente,
            "| candidatos:",
            candidatos
        )

        resultado = buscar_tmdb_candidatos(
            candidatos,
            "movie",
            anio
        )

        if resultado:
            nueva_ficha = construir_datos_tmdb_pelicula(
                resultado,
                candidatos[0]
            )

            # Conservar siempre los datos de AllDebrid y fecha.
            for campo in (
                "magnet_id", "file_path", "stream_url",
                "quality", "added_at", "source_name"
            ):
                if campo in pelicula:
                    nueva_ficha[campo] = pelicula[campo]

            # Si el usuario ha marcado expresamente una imagen como manual,
            # se conserva esa imagen.
            for campo in ("poster", "backdrop", "logo"):
                if pelicula.get("manual_" + campo):
                    nueva_ficha[campo] = pelicula.get(campo, "")

            pelicula.clear()
            pelicula.update(nueva_ficha)
            reparadas += 1

            print("Ficha antigua corregida:", pelicula.get("title"))

        else:
            # Si era una ficha generica equivocada, se elimina la metadata
            # incorrecta, pero se mantiene el enlace de reproduccion.
            titulo_limpio = candidatos[0]

            pelicula["title"] = titulo_limpio
            pelicula["tmdb_id"] = None
            pelicula["poster"] = ""
            pelicula["backdrop"] = ""
            pelicula["logo"] = ""
            pelicula["overview"] = ""
            pelicula["release_date"] = ""
            pelicula["runtime"] = 0
            pelicula["genres"] = []
            pelicula["age_rating"] = ""
            pelicula["match_status"] = "pendiente_tmdb"

            sin_coincidencia += 1

            print(
                "Ficha sin coincidencia fiable; se limpia la metadata:",
                titulo_limpio
            )

    print("Fichas antiguas reparadas:", reparadas)
    print("Fichas pendientes de TMDB:", sin_coincidencia)


# ==========================================================
# ACTUALIZACION
# ==========================================================

def main():
    print("--------------------------------")
    print("ACTUALIZANDO SHARKTV ALLDEBRID")
    print("--------------------------------")

    peliculas = leer("peliculas.json", [])
    series = leer("series.json", [])
    episodios = leer("episodios.json", {})

    if not isinstance(peliculas, list):
        raise Exception("peliculas.json no tiene formato valido")
    if not isinstance(series, list):
        raise Exception("series.json no tiene formato valido")
    if not isinstance(episodios, dict):
        raise Exception("episodios.json no tiene formato valido")

    # Reparar las fichas antiguas genericas sin borrar enlaces.
    reparar_peliculas_existentes(peliculas)

    peliculas_por_clave = {}

    for pelicula in peliculas:
        if not isinstance(pelicula, dict):
            continue

        if "magnet_id" in pelicula and "file_path" in pelicula:
            clave = (
                str(pelicula["magnet_id"])
                + "|"
                + str(pelicula["file_path"])
            )
            peliculas_por_clave[clave] = pelicula

    series_por_id = {}

    for serie in series:
        if isinstance(serie, dict) and serie.get("id") is not None:
            series_por_id[str(serie["id"])] = serie

    episodios_por_clave = {}

    for tmdb_id, lista in episodios.items():
        if not isinstance(lista, list):
            continue

        for episodio in lista:
            if not isinstance(episodio, dict):
                continue

            if "magnet_id" in episodio and "file_path" in episodio:
                clave = (
                    str(episodio["magnet_id"])
                    + "|"
                    + str(episodio["file_path"])
                )
                episodios_por_clave[clave] = episodio

    series_cache = {}
    nuevas_peliculas_lista = []
    nuevas_series_lista = []

    print("Peliculas existentes:", len(peliculas))
    print("Series existentes:", len(series))
    print("Consultando magnets de AllDebrid...")

    magnets = obtener_magnets()

    print("Magnets terminados:", len(magnets))

    if not magnets:
        raise Exception(
            "AllDebrid no ha devuelto magnets. "
            "Se conservan los catalogos anteriores."
        )

    nuevas_peliculas = 0
    nuevas_series = 0
    nuevos_episodios = 0
    archivos_examinados = 0

    for magnet in magnets:
        if not isinstance(magnet, dict):
            continue

        magnet_id = magnet.get("id")
        if not magnet_id:
            continue

        nombre_magnet = magnet.get("filename", magnet_id)
        added_at = fecha_incorporacion(magnet)

        print("--------------------------------")
        print("Examinando magnet:", nombre_magnet)

        try:
            archivos = obtener_archivos(magnet_id)
        except Exception as error:
            print("Error leyendo magnet:", magnet_id, error)
            continue

        print("Archivos de video encontrados:", len(archivos))

        for archivo in archivos:
            if not isinstance(archivo, dict):
                continue

            archivos_examinados += 1

            if not archivo.get("url"):
                print("Archivo sin enlace:", archivo.get("name"))
                continue

            nombre = archivo.get("name", "")
            if not nombre:
                continue

            if re.search(r"(?i)sample|trailer|extras", nombre):
                print("Archivo auxiliar ignorado:", nombre)
                continue

            clave = clave_archivo(magnet_id, archivo)

            # ------------------------------
            # SERIES Y EPISODIOS
            # ------------------------------
            episodio = detectar_episodio(nombre)

            if episodio:
                titulo_serie = episodio["serie"]
                clave_serie = normalizar(titulo_serie)

                if clave_serie not in series_cache:
                    anio_serie = extraer_anio(nombre_magnet, nombre)
                    info = datos_serie(titulo_serie, anio_serie)

                    if not info:
                        continue

                    tmdb_id = str(info["id"])

                    if tmdb_id in series_por_id:
                        serie_existente = series_por_id[tmdb_id]

                        if not serie_existente.get("added_at"):
                            serie_existente["added_at"] = added_at

                        series_cache[clave_serie] = serie_existente
                    else:
                        info["added_at"] = added_at
                        nuevas_series_lista.append(info)
                        series_por_id[tmdb_id] = info
                        series_cache[clave_serie] = info
                        nuevas_series += 1

                    episodios.setdefault(tmdb_id, [])

                info_serie = series_cache[clave_serie]
                tmdb_id = str(info_serie["id"])

                if clave in episodios_por_clave:
                    print("Episodio ya existente:", nombre)
                    continue

                datos_tmdb = obtener_datos_episodio(
                    tmdb_id,
                    episodio["temporada"],
                    episodio["episodio"]
                )

                nuevo = {
                    "numero": episodio["episodio"],
                    "temporada": episodio["temporada"],
                    "titulo": datos_tmdb["titulo"],
                    "sinopsis": datos_tmdb["sinopsis"],
                    "imagen": datos_tmdb["imagen"],
                    "magnet_id": str(magnet_id),
                    "file_path": archivo["path"],
                    "url": archivo["url"],
                    "quality": calidad(nombre + " " + nombre_magnet),
                    "added_at": added_at
                }

                episodios[tmdb_id].append(nuevo)
                episodios_por_clave[clave] = nuevo
                nuevos_episodios += 1

                print(
                    "Nuevo episodio:",
                    titulo_serie,
                    "T", episodio["temporada"],
                    "E", episodio["episodio"]
                )

            # ------------------------------
            # PELICULAS Y DOCUMENTALES
            # ------------------------------
            else:
                if clave in peliculas_por_clave:
                    print("Pelicula ya existente:", nombre)
                    continue

                try:
                    pelicula = datos_pelicula(
                        archivo,
                        magnet_id,
                        nombre_magnet,
                        added_at
                    )
                except Exception as error:
                    print(
                        "Error obteniendo datos de pelicula:",
                        nombre,
                        error
                    )
                    continue

                if pelicula:
                    nuevas_peliculas_lista.append(pelicula)
                    peliculas_por_clave[clave] = pelicula
                    nuevas_peliculas += 1
                    print("Nueva pelicula:", pelicula["title"])

    # Las nuevas incorporaciones aparecen al principio.
    peliculas = nuevas_peliculas_lista + peliculas
    series = nuevas_series_lista + series

    # Ordenar episodios por temporada y numero.
    for tmdb_id in episodios:
        if not isinstance(episodios[tmdb_id], list):
            continue

        episodios[tmdb_id].sort(
            key=lambda x: (
                x.get("temporada", 0),
                x.get("numero", 0)
            ) if isinstance(x, dict) else (0, 0)
        )

    guardar("peliculas.json", peliculas)
    guardar("series.json", series)
    guardar("episodios.json", episodios)

    print("--------------------------------")
    print("ACTUALIZACION COMPLETADA")
    print("--------------------------------")
    print("Magnets examinados:", len(magnets))
    print("Archivos de video examinados:", archivos_examinados)
    print("Peliculas totales:", len(peliculas))
    print("Peliculas nuevas:", nuevas_peliculas)
    print("Series totales:", len(series))
    print("Series nuevas:", nuevas_series)
    print("Episodios nuevos:", nuevos_episodios)
    print(
        "Episodios totales:",
        sum(
            len(x)
            for x in episodios.values()
            if isinstance(x, list)
        )
    )
    print("--------------------------------")
    print("Novedades colocadas al principio.")
    print("Enlaces de AllDebrid conservados.")
    print("--------------------------------")


if __name__ == "__main__":
    main()
