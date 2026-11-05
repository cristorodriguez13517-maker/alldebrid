import os
import re
import json
import time
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

def guardar(nombre, datos):
    Path(nombre).write_text(
        json.dumps(datos, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def leer(nombre, defecto):
    try:
        return json.loads(
            Path(nombre).read_text(encoding="utf-8")
        )
    except Exception:
        return defecto


# ==========================================================
# API ALLDEBRID
# ==========================================================

def alldebrid(endpoint, datos=None):

    respuesta = session.post(
        AD + endpoint,
        data=datos or {},
        timeout=60
    )

    respuesta.raise_for_status()

    resultado = respuesta.json()

    if resultado.get("status") != "success":

        error = resultado.get("error", {})

        codigo = error.get("code", "ERROR")
        mensaje = error.get("message", "Error desconocido")

        raise Exception(
            f"AllDebrid {codigo}: {mensaje}"
        )

    return resultado.get("data", {})


# ==========================================================
# OBTENER MAGNETS
# ==========================================================

def obtener_magnets():

    data = alldebrid(
        "/v4.1/magnet/status",
        {"status": "ready"}
    )

    return data.get("magnets", [])


# ==========================================================
# OBTENER ARCHIVOS DE LOS MAGNETS
# ==========================================================

def recorrer_archivos(elementos, ruta=""):

    encontrados = []

    for elemento in elementos or []:

        nombre = elemento.get("n", "")

        ruta_actual = f"{ruta}/{nombre}".strip("/")

        hijos = elemento.get("e")

        if isinstance(hijos, list):

            encontrados.extend(
                recorrer_archivos(
                    hijos,
                    ruta_actual
                )
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

    for magnet in data.get("magnets", []):

        if int(magnet.get("id", 0)) == int(magnet_id):

            return recorrer_archivos(
                magnet.get("files", [])
            )

    return []


# ==========================================================
# DESBLOQUEAR ENLACES DIRECTOS
# ==========================================================

def esperar_enlace_retrasado(delayed_id):

    print("Esperando enlace de AllDebrid...")

    for intento in range(60):

        time.sleep(5)

        data = alldebrid(
            "/v4/link/delayed",
            {"id": delayed_id}
        )

        estado = data.get("status")

        if estado == 2:

            enlace = data.get("link", "")

            if enlace:

                print("Enlace directo conseguido.")

                return enlace

        elif estado == 3:

            raise Exception(
                "AllDebrid no pudo generar el enlace."
            )

        if intento % 6 == 0:

            print(
                "Esperando generación del enlace:",
                intento + 1
            )

    raise Exception(
        "Tiempo agotado esperando el enlace."
    )


def desbloquear_enlace(enlace):

    if not enlace:
        return ""

    # Si ya es un enlace directo, no hace falta desbloquearlo.

    if ".debrid.it/dl/" in enlace:

        return enlace

    print("Desbloqueando archivo en AllDebrid...")

    data = alldebrid(
        "/v4/link/unlock",
        {"link": enlace}
    )

    # Caso 1: enlace directo disponible inmediatamente.

    enlace_directo = data.get("link")

    if enlace_directo:

        print("Enlace directo obtenido correctamente.")

        return enlace_directo

    # Caso 2: el enlace necesita tiempo para generarse.

    delayed_id = data.get("delayed")

    if delayed_id:

        return esperar_enlace_retrasado(
            delayed_id
        )

    # Caso 3: AllDebrid ofrece varias calidades.

    streams = data.get("streams", [])

    if streams:

        generacion_id = data.get("id")

        if not generacion_id:

            raise Exception(
                "AllDebrid no ha devuelto el ID de generación."
            )

        stream_id = streams[0].get("id")

        if not stream_id:

            raise Exception(
                "No se ha encontrado un stream disponible."
            )

        resultado = alldebrid(
            "/v4/link/streaming",
            {
                "id": generacion_id,
                "stream": stream_id
            }
        )

        enlace_directo = resultado.get("link")

        if enlace_directo:

            return enlace_directo

        delayed_id = resultado.get("delayed")

        if delayed_id:

            return esperar_enlace_retrasado(
                delayed_id
            )

    raise Exception(
        "AllDebrid no ha devuelto un enlace directo."
    )


# ==========================================================
# LIMPIAR Y NORMALIZAR TÍTULOS
# ==========================================================

def limpiar_titulo(texto):

    texto = Path(texto).stem

    texto = re.sub(
        r"(?i)\b(2160p|1080p|720p|4k|uhd|bluray|brrip|webrip|web-dl|hdr|x264|x265|h264|h265)\b",
        " ",
        texto
    )

    texto = re.sub(
        r"\[.*?\]|\(.*?\)",
        " ",
        texto
    )

    texto = re.sub(
        r"[._]+",
        " ",
        texto
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip(" -_.")


def normalizar(texto):

    texto = unicodedata.normalize(
        "NFD",
        texto.lower()
    )

    return "".join(
        c for c in texto
        if unicodedata.category(c) != "Mn"
    )


# ==========================================================
# CALIDAD DE VÍDEO
# ==========================================================

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
# API TMDB
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


# ==========================================================
# BUSCAR PELÍCULAS Y SERIES
# ==========================================================

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


# ==========================================================
# IMÁGENES
# ==========================================================

def imagen(ruta, tamano="w780"):

    return (
        IMAGE + tamano + ruta
        if ruta
        else ""
    )


# ==========================================================
# EDADES
# ==========================================================

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

    except Exception as error:

        print("Error edad película:", error)

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

    except Exception as error:

        print("Error edad serie:", error)

    return ""


# ==========================================================
# LOGOS TMDB
# ==========================================================

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

    except Exception as error:

        print("Error buscando logo:", error)

    return ""


# ==========================================================
# DATOS DE PELÍCULAS
# ==========================================================

def datos_pelicula(archivo, magnet_id):

    titulo = limpiar_titulo(
        archivo["name"]
    )

    resultado = buscar_tmdb(
        titulo,
        "movie"
    )

    if not resultado:

        print(
            "Película sin coincidencia:",
            titulo
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
            titulo
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
            archivo["name"]
        ),

        "age_rating": edad_pelicula(
            tmdb_id
        ),

        "match_status": "encontrada"
    }


# ==========================================================
# DETECTAR EPISODIOS
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


# ==========================================================
# DATOS DE SERIES
# ==========================================================

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


# ==========================================================
# DATOS DE EPISODIOS
# ==========================================================

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

    except Exception as error:

        print("Error episodio TMDB:", error)

        return {

            "titulo": f"Episodio {episodio}",

            "sinopsis": "",

            "imagen": ""
        }


# ==========================================================
# ACTUALIZAR CATÁLOGOS
# ==========================================================

def main():

    peliculas = []

    series = {}

    episodios = {}

    peliculas_anteriores = leer(
        "peliculas.json",
        []
    )

    series_anteriores = leer(
        "series.json",
        []
    )

    episodios_anteriores = leer(
        "episodios.json",
        {}
    )

    print("--------------------------------")

    print("ACTUALIZANDO SHARKTV ALLDEBRID")

    print("--------------------------------")

    print("Consultando magnets de AllDebrid...")

    magnets = obtener_magnets()

    print(
        "Magnets terminados:",
        len(magnets)
    )

    for magnet in magnets:

        magnet_id = magnet.get("id")

        if not magnet_id:
            continue

        print("--------------------------------")

        print(
            "Examinando magnet:",
            magnet.get("filename")
        )

        try:

            archivos = obtener_archivos(
                magnet_id
            )

        except Exception as error:

            print(
                "Error leyendo magnet:",
                error
            )

            continue

        for archivo in archivos:

            if not archivo["url"]:
                continue

            nombre = archivo["name"]

            if re.search(
                r"(?i)sample|trailer|extras",
                nombre
            ):
                continue

            # Obtener enlace directo de AllDebrid.

            try:

                archivo["url"] = desbloquear_enlace(
                    archivo["url"]
                )

            except Exception as error:

                print(
                    "No se pudo desbloquear:",
                    nombre,
                    error
                )

                continue

            if not archivo["url"]:
                continue

            episodio = detectar_episodio(
                nombre
            )

            # --------------------------------------
            # SERIES
            # --------------------------------------

            if episodio:

                titulo_serie = episodio["serie"]

                clave = normalizar(
                    titulo_serie
                )

                if clave not in series:

                    info = datos_serie(
                        titulo_serie
                    )

                    if not info:
                        continue

                    series[clave] = info

                    episodios[str(info["id"])] = []

                info_serie = series[clave]

                tmdb_id = info_serie["id"]

                datos_tmdb = obtener_datos_episodio(
                    tmdb_id,
                    episodio["temporada"],
                    episodio["episodio"]
                )

                episodios[str(tmdb_id)].append({

                    "numero": episodio["episodio"],

                    "temporada": episodio["temporada"],

                    "titulo": datos_tmdb["titulo"],

                    "sinopsis": datos_tmdb["sinopsis"],

                    "imagen": datos_tmdb["imagen"],

                    "magnet_id": magnet_id,

                    "file_path": archivo["path"],

                    "url": archivo["url"],

                    "quality": calidad(nombre)

                })

            # --------------------------------------
            # PELÍCULAS
            # --------------------------------------

            else:

                pelicula = datos_pelicula(
                    archivo,
                    magnet_id
                )

                if pelicula:

                    peliculas.append(
                        pelicula
                    )

    # ======================================================
    # CONSERVAR PERSONALIZACIONES MANUALES
    # ======================================================

    for nueva in peliculas:

        for antigua in peliculas_anteriores:

            if (

                nueva["magnet_id"] == antigua.get("magnet_id")

                and nueva["file_path"] == antigua.get("file_path")

            ):

                for campo in antigua:

                    if campo.endswith("_manual"):

                        nueva[campo] = antigua[campo]

    for clave, nueva in series.items():

        for antigua in series_anteriores:

            if nueva["id"] == antigua.get("id"):

                for campo in antigua:

                    if campo.endswith("_manual"):

                        nueva[campo] = antigua[campo]

    # ======================================================
    # CONSERVAR PERSONALIZACIONES DE EPISODIOS
    # ======================================================

    for tmdb_id, lista in episodios.items():

        anteriores = episodios_anteriores.get(
            tmdb_id,
            []
        )

        for nuevo in lista:

            for antiguo in anteriores:

                if (

                    nuevo["magnet_id"] == antiguo.get("magnet_id")

                    and nuevo["file_path"] == antiguo.get("file_path")

                ):

                    for campo in antiguo:

                        if campo.endswith("_manual"):

                            nuevo[campo] = antiguo[campo]

    # ======================================================
    # ORDENAR EPISODIOS
    # ======================================================

    for tmdb_id in episodios:

        episodios[tmdb_id].sort(
            key=lambda x: (
                x["temporada"],
                x["numero"]
            )
        )

    # ======================================================
    # GUARDAR JSON
    # ======================================================

    guardar(
        "peliculas.json",
        peliculas
    )

    guardar(
        "series.json",
        list(series.values())
    )

    guardar(
        "episodios.json",
        episodios
    )

    # ======================================================
    # RESUMEN
    # ======================================================

    print("--------------------------------")

    print(
        "PELÍCULAS:",
        len(peliculas)
    )

    print(
        "SERIES:",
        len(series)
    )

    print(
        "EPISODIOS:",
        sum(
            len(x)
            for x in episodios.values()
        )
    )

    print("--------------------------------")

    print(
        "CATÁLOGOS SHARKTV ACTUALIZADOS"
    )

    print("--------------------------------")


# ==========================================================
# INICIO
# ==========================================================

if __name__ == "__main__":

    main()
