import os
import re
import json
import requests
import unicodedata

from pathlib import Path
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
    """
    AllDebrid puede devolver los magnets como diccionarios
    o como identificadores de texto.

    Esta función convierte ambos formatos en diccionarios
    para evitar el error: 'str' object has no attribute 'get'.
    """

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

            if not magnet_id:
                continue

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

    magnets = data.get("magnets", [])

    return normalizar_lista_magnets(magnets)


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

            archivos = magnet.get("files", [])

            return recorrer_archivos(archivos)

    print(
        "No se encontraron archivos para el magnet:",
        magnet_id
    )

    return []


# ==========================================================
# IDENTIFICACIÓN DE ARCHIVOS
# ==========================================================

def clave_archivo(magnet_id, archivo):

    return (
        str(magnet_id)
        + "|"
        + str(archivo["path"])
    )


def limpiar_titulo(texto):

    texto = Path(texto).stem

    texto = re.sub(
        r"(?i)\b(2160p|1080p|720p|4k|uhd|bluray|brrip|webrip|web-dl|hdr|x264|x265|h264|h265)\b",
        " ",
        texto
    )

    texto = re.sub(r"\[.*?\]|\(.*?\)", " ", texto)
    texto = re.sub(r"[._]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto)

    return texto.strip(" -_.")


def normalizar(texto):

    texto = unicodedata.normalize(
        "NFD",
        str(texto).lower()
    )

    return "".join(
        c for c in texto
        if unicodedata.category(c) != "Mn"
    )


def calidad(texto):

    texto = texto.lower()

    if re.search(r"\b(4k|2160p|uhd)\b", texto):
        return "4K"

    if re.search(r"\b(fhd|1080p|full hd)\b", texto):
        return "FHD"

    if re.search(r"\b(hd|720p)\b", texto):
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

        puntuacion = SequenceMatcher(
            None,
            titulo_busqueda,
            normalizar(nombre)
        ).ratio()

        if puntuacion > mejor_puntuacion:

            mejor = item
            mejor_puntuacion = puntuacion

    if mejor_puntuacion < 0.45:
        return None

    return mejor


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
# NUEVAS PELÍCULAS
# ==========================================================

def datos_pelicula(archivo, magnet_id):

    titulo = limpiar_titulo(archivo["name"])

    resultado = buscar_tmdb(titulo, "movie")

    if not resultado:

        print("Película sin coincidencia:", titulo)

        return None

    tmdb_id = resultado["id"]

    detalles = tmdb_get(
        f"/movie/{tmdb_id}"
    )

    return {

        "magnet_id": magnet_id,
        "file_path": archivo["path"],
        "stream_url": archivo["url"],

        "title": detalles.get("title", titulo),

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

        "overview": detalles.get("overview", ""),

        "release_date": detalles.get("release_date", ""),

        "runtime": detalles.get("runtime", 0),

        "genres": [
            x["name"]
            for x in detalles.get("genres", [])
        ],

        "quality": calidad(archivo["name"]),

        "age_rating": edad_pelicula(tmdb_id),

        "match_status": "encontrada"
    }


# ==========================================================
# SERIES Y EPISODIOS
# ==========================================================

def detectar_episodio(nombre):

    patron = re.search(
        r"(?i)(.*?)(?:S(\d{1,2})E(\d{1,3})|(\d{1,2})x(\d{1,3}))",
        nombre
    )

    if not patron:
        return None

    serie = limpiar_titulo(
        patron.group(1)
    )

    temporada = int(
        patron.group(2) or patron.group(4)
    )

    episodio = int(
        patron.group(3) or patron.group(5)
    )

    if not serie:
        return None

    return {

        "serie": serie,

        "temporada": temporada,

        "episodio": episodio
    }


def datos_serie(titulo):

    resultado = buscar_tmdb(
        titulo,
        "tv"
    )

    if not resultado:

        print("Serie sin coincidencia:", titulo)

        return None

    tmdb_id = resultado["id"]

    detalles = tmdb_get(
        f"/tv/{tmdb_id}"
    )

    return {

        "id": tmdb_id,

        "tmdb_id": tmdb_id,

        "title": detalles.get("name", titulo),

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

        "overview": detalles.get("overview", ""),

        "first_air_date": detalles.get("first_air_date", ""),

        "genres": [
            x["name"]
            for x in detalles.get("genres", [])
        ],

        "age_rating": edad_serie(tmdb_id),

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

    # ======================================================
    # ÍNDICE DE PELÍCULAS EXISTENTES
    # ======================================================

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

    # ======================================================
    # ÍNDICE DE SERIES EXISTENTES
    # ======================================================

    series_por_id = {}

    for serie in series:

        if not isinstance(serie, dict):
            continue

        if serie.get("id") is not None:

            series_por_id[str(serie["id"])] = serie

    # ======================================================
    # ÍNDICE DE EPISODIOS EXISTENTES
    # ======================================================

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

    # Novedades separadas para colocarlas al principio.

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

    # ======================================================
    # RECORRER MAGNETS
    # ======================================================

    for magnet in magnets:

        # Protección adicional: comprobar el formato.

        if not isinstance(magnet, dict):

            print(
                "Magnet ignorado por formato incorrecto:",
                magnet
            )

            continue

        magnet_id = magnet.get("id")

        if not magnet_id:
            continue

        nombre_magnet = magnet.get(
            "filename",
            magnet_id
        )

        print(
            "Examinando magnet:",
            nombre_magnet
        )

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

            # ==================================================
            # EPISODIOS
            # ==================================================

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

                        series_cache[clave_serie] = (
                            series_por_id[tmdb_id]
                        )

                    else:

                        # Serie nueva: se guarda temporalmente.

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

                # No modificar episodios existentes.

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

                    "quality": calidad(nombre)
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

            # ==================================================
            # PELÍCULAS
            # ==================================================

            else:

                # Si existe, no modificar ningún dato manual.

                if clave in peliculas_por_clave:
                    continue

                try:

                    pelicula = datos_pelicula(
                        archivo,
                        magnet_id
                    )

                except Exception as error:

                    print(
                        "Error obteniendo datos de película:",
                        nombre,
                        error
                    )

                    continue

                if pelicula:

                    # Película nueva: se guarda temporalmente.

                    nuevas_peliculas_lista.append(
                        pelicula
                    )

                    peliculas_por_clave[clave] = pelicula

                    nuevas_peliculas += 1

                    print(
                        "Nueva película:",
                        pelicula["title"]
                    )

    # ======================================================
    # COLOCAR NOVEDADES AL PRINCIPIO
    # ======================================================

    peliculas = (
        nuevas_peliculas_lista
        + peliculas
    )

    series = (
        nuevas_series_lista
        + series
    )

    # ======================================================
    # ORDENAR EPISODIOS
    # ======================================================

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

    # ======================================================
    # GUARDAR CATÁLOGOS
    # ======================================================

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

    # ======================================================
    # RESULTADO
    # ======================================================

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

    print(
        "Las novedades se han colocado al principio."
    )

    print(
        "Los enlaces y correcciones existentes se han conservado."
    )

    print("--------------------------------")


if __name__ == "__main__":
    main()
