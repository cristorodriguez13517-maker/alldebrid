import os
import re
import json
import requests
import unicodedata

from pathlib import Path
from datetime import datetime, timezone
from difflib import SequenceMatcher


# ==========================================================
# CONFIGURACIÓN
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

HEADERS = {
    "Authorization": f"Bearer {ALLDEBRID_API_KEY}"
}

session = requests.Session()
session.headers.update(HEADERS)


# ==========================================================
# ALIAS MANUALES
# ==========================================================
# Aquí podemos asociar nombres raros de archivos con títulos
# reales. Se pueden añadir más casos cuando sea necesario.

ALIAS_TITULOS = {
    "84114.v1n1": "Vinicius",
}


# ==========================================================
# ARCHIVOS JSON
# ==========================================================

def leer(nombre, defecto):
    ruta = Path(nombre)

    if not ruta.exists():
        return defecto

    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception as error:
        raise Exception(
            f"No se puede leer {nombre}. "
            f"No se modificará ningún catálogo: {error}"
        )


def guardar(nombre, datos):
    ruta = Path(nombre)

    contenido = json.dumps(
        datos,
        ensure_ascii=False,
        indent=2
    )

    temporal = ruta.with_suffix(ruta.suffix + ".tmp")
    temporal.write_text(contenido, encoding="utf-8")
    temporal.replace(ruta)


# ==========================================================
# NORMALIZAR RESPUESTAS DE ALLDEBRID
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

            magnet_id = (
                magnet.get("id")
                or magnet.get("magnet_id")
            )

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


# ==========================================================
# ALLDEBRID
# ==========================================================

def alldebrid(endpoint, datos=None):

    respuesta = session.post(
        AD + endpoint,
        data=datos or {},
        timeout=60
    )

    respuesta.raise_for_status()

    resultado = respuesta.json()

    if not isinstance(resultado, dict):
        raise Exception(
            f"Respuesta inesperada de AllDebrid: {resultado}"
        )

    if resultado.get("status") != "success":
        raise Exception(f"Error AllDebrid: {resultado}")

    return resultado.get("data", {})


def obtener_magnets():

    data = alldebrid(
        "/v4.1/magnet/status",
        {"status": "ready"}
    )

    return normalizar_lista_magnets(
        data.get("magnets", [])
    )


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

            encontrados.extend(
                recorrer_archivos(hijos, ruta_actual)
            )

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

    magnets = normalizar_lista_magnets(
        data.get("magnets", [])
    )

    for magnet in magnets:

        if str(magnet.get("id")) == str(magnet_id):

            return recorrer_archivos(
                magnet.get("files", [])
            )

    print(
        "No se encontraron archivos para el magnet:",
        magnet_id
    )

    return []


# ==========================================================
# FECHAS DE INCORPORACIÓN
# ==========================================================

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
                    valor,
                    timezone.utc
                ).isoformat()

            return str(valor)

        except Exception:
            pass

    return datetime.now(timezone.utc).isoformat()


# ==========================================================
# IDENTIFICACIÓN DE ARCHIVOS
# ==========================================================

def clave_archivo(magnet_id, archivo):

    return (
        str(magnet_id)
        + "|"
        + str(archivo["path"])
    )


def normalizar(texto):

    texto = unicodedata.normalize(
        "NFD",
        str(texto).lower()
    )

    return "".join(
        c for c in texto
        if unicodedata.category(c) != "Mn"
    )


def limpiar_titulo(texto):

    texto = Path(str(texto)).stem

    # Eliminar páginas web y dominios.
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

    # Eliminar información técnica de las releases.
    patrones = [
        r"(?i)\b2160p?\b",
        r"(?i)\b1080p?\b",
        r"(?i)\b720p?\b",
        r"(?i)\b4k\b",
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
        r"(?i)\bx264\b",
        r"(?i)\bx265\b",
        r"(?i)\bh264\b",
        r"(?i)\bh265\b",
        r"(?i)\bhevc\b",
        r"(?i)\bav1\b",
        r"(?i)\bac3\b",
        r"(?i)\bdts\b",
        r"(?i)\bdts-hd\b",
        r"(?i)\btruehd\b",
        r"(?i)\batmos\b",
        r"(?i)\baac\b",
        r"(?i)\bflac\b",
        r"(?i)\b\d(?:\.\d)?\s*ch\b",
        r"(?i)\b\d\.\d\b",
        r"(?i)\bcastellano\b",
        r"(?i)\bespañol\b",
        r"(?i)\bingles\b",
        r"(?i)\benglish\b",
        r"(?i)\bsubs\b",
        r"(?i)\bsubtitulos\b",
        r"(?i)\bes-en\b",
        r"(?i)\ben-es\b",
        r"(?i)\bproper\b",
        r"(?i)\brepack\b",
        r"(?i)\bextended\b",
        r"(?i)\bdirectors cut\b",
    ]

    for patron in patrones:
        texto = re.sub(patron, " ", texto)

    # Quitar grupos de etiquetas entre corchetes.
    texto = re.sub(r"\[.*?\]", " ", texto)
    texto = re.sub(r"\{.*?\}", " ", texto)

    # Quitar puntos y guiones usados como separadores.
    texto = re.sub(r"[._]+", " ", texto)
    texto = re.sub(r"[-]+", " ", texto)

    # Quitar restos de corchetes sueltos.
    texto = texto.replace("[", " ")
    texto = texto.replace("]", " ")

    texto = re.sub(r"\s+", " ", texto)

    return texto.strip(" -_.")


def titulo_alias(texto):

    texto_normalizado = normalizar(
        limpiar_titulo(texto)
    )

    for clave, titulo in ALIAS_TITULOS.items():

        clave_normalizada = normalizar(clave)

        if (
            texto_normalizado == clave_normalizada
            or texto_normalizado.startswith(
                clave_normalizada + " "
            )
        ):
            return titulo

    return None


def obtener_titulos_candidatos(archivo, nombre_magnet=""):

    candidatos = []

    # Primero comprobamos si existe un alias manual.
    alias_archivo = titulo_alias(
        archivo.get("name", "")
    )

    alias_magnet = titulo_alias(
        nombre_magnet
    )

    if alias_archivo:
        candidatos.append(alias_archivo)

    if alias_magnet:
        candidatos.append(alias_magnet)

    # Después utilizamos los nombres limpios.
    titulo_archivo = limpiar_titulo(
        archivo.get("name", "")
    )

    titulo_magnet = limpiar_titulo(
        nombre_magnet
    )

    if titulo_archivo:
        candidatos.append(titulo_archivo)

    if titulo_magnet:
        candidatos.append(titulo_magnet)

    # Eliminar duplicados conservando el orden.
    resultado = []
    vistos = set()

    for titulo in candidatos:

        clave = normalizar(titulo)

        if clave and clave not in vistos:
            vistos.add(clave)
            resultado.append(titulo)

    # Los nombres más específicos se prueban primero.
    resultado.sort(
        key=lambda x: len(x),
        reverse=True
    )

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
# TMDB
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


def buscar_tmdb(titulo, tipo):

    endpoint = (
        "/search/movie"
        if tipo == "movie"
        else "/search/tv"
    )

    resultados = tmdb_get(
        endpoint,
        {
            "query": titulo,
            "include_adult": "false"
        }
    ).get("results", [])

    if not resultados:
        return None

    titulo_busqueda = normalizar(titulo)

    mejor = None
    mejor_puntuacion = 0

    for item in resultados:

        nombre = item.get(
            "title" if tipo == "movie" else "name",
            ""
        )

        nombre_original = item.get(
            "original_title"
            if tipo == "movie"
            else "original_name",
            ""
        )

        puntuacion = max(
            SequenceMatcher(
                None,
                titulo_busqueda,
                normalizar(nombre)
            ).ratio(),

            SequenceMatcher(
                None,
                titulo_busqueda,
                normalizar(nombre_original)
            ).ratio()
        )

        if puntuacion > mejor_puntuacion:

            mejor = item
            mejor_puntuacion = puntuacion

    if mejor_puntuacion < 0.40:
        return None

    return mejor


def buscar_tmdb_candidatos(candidatos, tipo):

    for titulo in candidatos:

        if not titulo:
            continue

        print(
            "Buscando en TMDB:",
            titulo
        )

        resultado = buscar_tmdb(
            titulo,
            tipo
        )

        if resultado:
            return resultado

    return None


def imagen(ruta, tamano="w780"):

    return IMAGE + tamano + ruta if ruta else ""


def edad_pelicula(tmdb_id):

    try:

        datos = tmdb_get(
            f"/movie/{tmdb_id}/release_dates"
        )

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

        datos = tmdb_get(
            f"/tv/{tmdb_id}/content_ratings"
        )

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
            {
                "include_image_language": "es,en,null"
            }
        )

        logos = datos.get("logos", [])

        if logos:

            elegido = next(
                (
                    x for x in logos
                    if x.get("iso_639_1") == "es"
                ),
                logos[0]
            )

            return imagen(
                elegido.get("file_path"),
                "w500"
            )

    except Exception:
        pass

    return ""


# ==========================================================
# NUEVAS PELÍCULAS Y DOCUMENTALES
# ==========================================================

def datos_pelicula(
    archivo,
    magnet_id,
    nombre_magnet="",
    added_at=""
):

    candidatos = obtener_titulos_candidatos(
        archivo,
        nombre_magnet
    )

    if not candidatos:

        print(
            "No se pudo extraer el título:",
            archivo.get("name")
        )

        return None

    resultado = buscar_tmdb_candidatos(
        candidatos,
        "movie"
    )

    if not resultado:

        print(
            "Película sin coincidencia:",
            candidatos
        )

        return None

    tmdb_id = resultado["id"]

    detalles = tmdb_get(
        f"/movie/{tmdb_id}"
    )

    return {

        "magnet_id": magnet_id,

        "file_path": archivo["path"],

        "stream_url": archivo["url"],

        "title": detalles.get(
            "title",
            candidatos[0]
        ),

        "tmdb_id": tmdb_id,

        "poster": imagen(
            detalles.get("poster_path")
        ),

        "backdrop": imagen(
            detalles.get("backdrop_path"),
            "original"
        ),

        "logo": buscar_logo(
            "movie",
            tmdb_id
        ),

        "overview": detalles.get(
            "overview",
            ""
        ),

        "release_date": detalles.get(
            "release_date",
            ""
        ),

        "runtime": detalles.get(
            "runtime",
            0
        ),

        "genres": [
            x["name"]
            for x in detalles.get("genres", [])
        ],

        "quality": calidad(
            archivo["name"] + " " + nombre_magnet
        ),

        "age_rating": edad_pelicula(
            tmdb_id
        ),

        "added_at": added_at,

        "source_name": nombre_magnet,

        "match_status": "encontrada"
    }


# ==========================================================
# SERIES Y EPISODIOS
# ==========================================================

def detectar_episodio(nombre):

    nombre_original = Path(nombre).stem

    # FORMATO S01E01 O 1x01

    patron = re.search(
        r"(?i)(.*?)(?:S(\d{1,2})E(\d{1,3})|(\d{1,2})x(\d{1,3}))",
        nombre_original
    )

    if patron:

        serie = limpiar_titulo(
            patron.group(1)
        )

        temporada = int(
            patron.group(2) or patron.group(4)
        )

        episodio = int(
            patron.group(3) or patron.group(5)
        )

        if serie:

            return {
                "serie": serie,
                "temporada": temporada,
                "episodio": episodio
            }

    # FORMATO Cap.101 / Cap 101 / Capítulo 101

    patron = re.search(
        r"(?i)^(.*?)\s*\[?\s*(?:cap(?:itulo)?|episodio|ep)\.?\s*(\d{3,4})\s*\]?",
        nombre_original
    )

    if patron:

        serie = limpiar_titulo(
            patron.group(1)
        )

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


def datos_serie(titulo):

    resultado = buscar_tmdb(
        titulo,
        "tv"
    )

    if not resultado:

        print(
            "Serie sin coincidencia:",
            titulo
        )

        return None

    tmdb_id = resultado["id"]

    detalles = tmdb_get(
        f"/tv/{tmdb_id}"
    )

    return {

        "id": tmdb_id,

        "tmdb_id": tmdb_id,

        "title": detalles.get(
            "name",
            titulo
        ),

        "poster": imagen(
            detalles.get("poster_path")
        ),

        "backdrop": imagen(
            detalles.get("backdrop_path"),
            "original"
        ),

        "logo": buscar_logo(
            "tv",
            tmdb_id
        ),

        "overview": detalles.get(
            "overview",
            ""
        ),

        "first_air_date": detalles.get(
            "first_air_date",
            ""
        ),

        "genres": [
            x["name"]
            for x in detalles.get("genres", [])
        ],

        "age_rating": edad_serie(
            tmdb_id
        ),

        "number_of_seasons": detalles.get(
            "number_of_seasons",
            0
        ),

        "quality": ""
    }


def obtener_datos_episodio(
    tmdb_id,
    temporada,
    episodio
):

    try:

        datos = tmdb_get(
            f"/tv/{tmdb_id}/season/{temporada}/episode/{episodio}"
        )

        return {

            "titulo": datos.get(
                "name",
                f"Episodio {episodio}"
            ),

            "sinopsis": datos.get(
                "overview",
                ""
            ),

            "imagen": imagen(
                datos.get("still_path"),
                "w500"
            )
        }

    except Exception:

        return {

            "titulo": f"Episodio {episodio}",

            "sinopsis": "",

            "imagen": ""
        }


# ==========================================================
# ACTUALIZACIÓN SEGURA
# ==========================================================

def main():

    print("--------------------------------")
    print("ACTUALIZANDO SHARKTV ALLDEBRID")
    print("--------------------------------")

    peliculas = leer(
        "peliculas.json",
        []
    )

    series = leer(
        "series.json",
        []
    )

    episodios = leer(
        "episodios.json",
        {}
    )

    if not isinstance(peliculas, list):
        raise Exception(
            "peliculas.json no tiene formato válido"
        )

    if not isinstance(series, list):
        raise Exception(
            "series.json no tiene formato válido"
        )

    if not isinstance(episodios, dict):
        raise Exception(
            "episodios.json no tiene formato válido"
        )

    # ÍNDICE DE PELÍCULAS

    peliculas_por_clave = {}

    for pelicula in peliculas:

        if not isinstance(pelicula, dict):
            continue

        if (
            "magnet_id" in pelicula
            and "file_path" in pelicula
        ):

            clave = (
                str(pelicula["magnet_id"])
                + "|"
                + str(pelicula["file_path"])
            )

            peliculas_por_clave[clave] = pelicula

    # ÍNDICE DE SERIES

    series_por_id = {}

    for serie in series:

        if not isinstance(serie, dict):
            continue

        if serie.get("id") is not None:

            series_por_id[str(serie["id"])] = serie

    # ÍNDICE DE EPISODIOS

    episodios_por_clave = {}

    for tmdb_id, lista in episodios.items():

        if not isinstance(lista, list):
            continue

        for episodio in lista:

            if not isinstance(episodio, dict):
                continue

            if (
                "magnet_id" in episodio
                and "file_path" in episodio
            ):

                clave = (
                    str(episodio["magnet_id"])
                    + "|"
                    + str(episodio["file_path"])
                )

                episodios_por_clave[clave] = episodio

    series_cache = {}

    nuevas_peliculas_lista = []
    nuevas_series_lista = []

    print(
        "Películas existentes:",
        len(peliculas)
    )

    print(
        "Series existentes:",
        len(series)
    )

    print("Consultando magnets de AllDebrid...")

    magnets = obtener_magnets()

    print(
        "Magnets terminados:",
        len(magnets)
    )

    if not magnets:

        raise Exception(
            "AllDebrid no ha devuelto magnets. "
            "Se conservan los catálogos anteriores."
        )

    nuevas_peliculas = 0
    nuevas_series = 0
    nuevos_episodios = 0

    # RECORRER MAGNETS

    for magnet in magnets:

        if not isinstance(magnet, dict):
            continue

        magnet_id = magnet.get("id")

        if not magnet_id:
            continue

        nombre_magnet = magnet.get(
            "filename",
            magnet_id
        )

        added_at = fecha_incorporacion(magnet)

        print("--------------------------------")
        print("Examinando magnet:", nombre_magnet)

        try:

            archivos = obtener_archivos(
                magnet_id
            )

        except Exception as error:

            print(
                "Error leyendo magnet:",
                magnet_id,
                error
            )

            continue

        for archivo in archivos:

            if not isinstance(archivo, dict):
                continue

            if not archivo.get("url"):
                continue

            nombre = archivo.get("name", "")

            if not nombre:
                continue

            if re.search(
                r"(?i)sample|trailer|extras",
                nombre
            ):
                continue

            clave = clave_archivo(
                magnet_id,
                archivo
            )

            # ==============================================
            # DETECTAR EPISODIOS
            # ==============================================

            episodio = detectar_episodio(nombre)

            if episodio:

                titulo_serie = episodio["serie"]

                clave_serie = normalizar(
                    titulo_serie
                )

                if clave_serie not in series_cache:

                    info = datos_serie(
                        titulo_serie
                    )

                    if not info:
                        continue

                    tmdb_id = str(
                        info["id"]
                    )

                    if tmdb_id in series_por_id:

                        serie_existente = series_por_id[tmdb_id]

                        # No sobrescribir correcciones manuales.
                        if not serie_existente.get("added_at"):
                            serie_existente["added_at"] = added_at

                        series_cache[clave_serie] = serie_existente

                    else:

                        info["added_at"] = added_at

                        nuevas_series_lista.append(info)

                        series_por_id[tmdb_id] = info

                        series_cache[clave_serie] = info

                        nuevas_series += 1

                    episodios.setdefault(
                        tmdb_id,
                        []
                    )

                info_serie = series_cache[
                    clave_serie
                ]

                tmdb_id = str(
                    info_serie["id"]
                )

                if clave in episodios_por_clave:
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

                    "magnet_id": magnet_id,

                    "file_path": archivo["path"],

                    "url": archivo["url"],

                    "quality": calidad(
                        nombre + " " + nombre_magnet
                    ),

                    "added_at": added_at
                }

                episodios[tmdb_id].append(nuevo)

                episodios_por_clave[clave] = nuevo

                nuevos_episodios += 1

                print(
                    "Nuevo episodio:",
                    titulo_serie,
                    "T",
                    episodio["temporada"],
                    "E",
                    episodio["episodio"]
                )

            # ==============================================
            # PELÍCULAS Y DOCUMENTALES
            # ==============================================

            else:

                if clave in peliculas_por_clave:
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
                        "Error obteniendo datos de película:",
                        nombre,
                        error
                    )

                    continue

                if pelicula:

                    nuevas_peliculas_lista.append(
                        pelicula
                    )

                    peliculas_por_clave[clave] = pelicula

                    nuevas_peliculas += 1

                    print(
                        "Nueva película:",
                        pelicula["title"]
                    )

    # ==============================================
    # NOVEDADES AL PRINCIPIO
    # ==============================================

    peliculas = (
        nuevas_peliculas_lista
        + peliculas
    )

    series = (
        nuevas_series_lista
        + series
    )

    # ==============================================
    # ORDENAR EPISODIOS
    # ==============================================

    for tmdb_id in episodios:

        if not isinstance(episodios[tmdb_id], list):
            continue

        episodios[tmdb_id].sort(
            key=lambda x: (
                x.get("temporada", 0),
                x.get("numero", 0)
            )
            if isinstance(x, dict)
            else (0, 0)
        )

    # ==============================================
    # GUARDAR CATÁLOGOS
    # ==============================================

    guardar(
        "peliculas.json",
        peliculas
    )

    guardar(
        "series.json",
        series
    )

    guardar(
        "episodios.json",
        episodios
    )

    # ==============================================
    # RESULTADO
    # ==============================================

    print("--------------------------------")
    print("ACTUALIZACIÓN COMPLETADA")
    print("--------------------------------")

    print(
        "Películas totales:",
        len(peliculas)
    )

    print(
        "Películas nuevas:",
        nuevas_peliculas
    )

    print(
        "Series totales:",
        len(series)
    )

    print(
        "Series nuevas:",
        nuevas_series
    )

    print(
        "Episodios nuevos:",
        nuevos_episodios
    )

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
    print("Correcciones manuales conservadas.")
    print("Fechas de incorporación guardadas.")
    print("--------------------------------")


if __name__ == "__main__":
    main()
