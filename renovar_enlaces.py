import os
import json
import time
import requests

from pathlib import Path
from urllib.parse import urlparse


# ==========================================================
# CONFIGURACION
# ==========================================================

API_KEY = os.environ.get("ALLDEBRID_API_KEY", "").strip()

if not API_KEY:
    raise SystemExit("ERROR: falta el secreto ALLDEBRID_API_KEY")

AD = "https://api.alldebrid.com"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}"
}

session = requests.Session()
session.headers.update(HEADERS)


# ==========================================================
# JSON: LECTURA Y GUARDADO SEGURO
# ==========================================================

def leer_json(nombre, defecto):
    ruta = Path(nombre)

    if not ruta.exists():
        print(f"AVISO: no existe {nombre}")
        return defecto

    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception as error:
        raise SystemExit(
            f"ERROR leyendo {nombre}: {error}. "
            "No se modificara ningun catalogo."
        )


def guardar_json(nombre, datos):
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

def alldebrid(endpoint, datos=None):
    respuesta = session.post(
        AD + endpoint,
        data=datos or {},
        timeout=60
    )

    respuesta.raise_for_status()

    resultado = respuesta.json()

    if not isinstance(resultado, dict):
        raise Exception("Respuesta inesperada de AllDebrid")

    if resultado.get("status") != "success":
        error = resultado.get("error", {})
        raise Exception(f"AllDebrid: {error or resultado}")

    return resultado.get("data", {})


def enlace_directo_valido(url):
    if not isinstance(url, str) or not url.strip():
        return False

    try:
        partes = urlparse(url.strip())
        host = (partes.hostname or "").lower()

        dominio_valido = (
            host.endswith(".debrid.it")
            or host.endswith(".alldeb.ovh")
        )

        return (
            partes.scheme == "https"
            and dominio_valido
            and partes.path.startswith("/dl/")
        )

    except Exception:
        return False


def desbloquear_enlace(url):
    if not isinstance(url, str) or not url.strip():
        return ""

    url = url.strip()

    if enlace_directo_valido(url):
        return url

    try:
        print("  Solicitando nuevo enlace a AllDebrid...")

        data = alldebrid(
            "/v4/link/unlock",
            {"link": url}
        )

        enlace = data.get("link", "")

        if enlace_directo_valido(enlace):
            return enlace

        delayed_id = data.get("delayed")

        if not delayed_id:
            print("  AllDebrid no devolvio enlace directo.")
            return ""

        print("  Enlace pendiente. Esperando...")

        for intento in range(24):
            time.sleep(5)

            resultado = alldebrid(
                "/v4/link/delayed",
                {"id": delayed_id}
            )

            estado = resultado.get("status")

            if estado == 2:
                enlace = resultado.get("link", "")

                if enlace_directo_valido(enlace):
                    return enlace

                print("  El enlace recibido no es un enlace /dl/.")
                return ""

            if estado == 3:
                print("  AllDebrid no pudo generar el enlace.")
                return ""

            print(f"  Esperando: {intento + 1}/24")

        print("  Tiempo de espera agotado.")
        return ""

    except Exception as error:
        mensaje = str(error)

        if "NO_SERVER" in mensaje:
            print(
                "  ERROR NO_SERVER: AllDebrid no permite "
                "desbloquear desde este servidor."
            )
        else:
            print(f"  ERROR: {mensaje}")

        return ""


# ==========================================================
# RENOVACION DE PELICULAS
# ==========================================================

def renovar_peliculas(peliculas):
    renovados = 0
    protegidos = 0
    fallidos = 0

    if not isinstance(peliculas, list):
        raise SystemExit("ERROR: peliculas.json no contiene una lista.")

    for pelicula in peliculas:
        if not isinstance(pelicula, dict):
            continue

        titulo = pelicula.get("title", "Sin titulo")

        # No tocar enlaces marcados como manuales.
        if pelicula.get("manual_link") is True:
            protegidos += 1
            print(f"[PROTEGIDO] Pelicula: {titulo}")
            continue

        origen = pelicula.get("pending_url", "").strip()

        if not origen:
            continue

        print(f"[PELICULA] {titulo}")

        nuevo = desbloquear_enlace(origen)

        if nuevo:
            pelicula["stream_url"] = nuevo
            renovados += 1
            print("  Enlace renovado correctamente.")
        else:
            fallidos += 1
            print("  No se pudo renovar.")

        time.sleep(2)

    return renovados, protegidos, fallidos


# ==========================================================
# RENOVACION DE EPISODIOS
# ==========================================================

def renovar_episodios(episodios):
    renovados = 0
    protegidos = 0
    fallidos = 0

    if not isinstance(episodios, dict):
        raise SystemExit("ERROR: episodios.json no contiene un objeto.")

    for serie_id, lista in episodios.items():

        if not isinstance(lista, list):
            continue

        for episodio in lista:
            if not isinstance(episodio, dict):
                continue

            titulo = episodio.get("titulo", "Episodio")
            temporada = episodio.get("temporada", "")
            numero = episodio.get("numero", "")

            # No tocar enlaces marcados como manuales.
            if episodio.get("manual_link") is True:
                protegidos += 1
                print(
                    f"[PROTEGIDO] Serie {serie_id} "
                    f"T{temporada} E{numero}"
                )
                continue

            origen = episodio.get("pending_url", "").strip()

            if not origen:
                continue

            print(
                f"[EPISODIO] Serie {serie_id} "
                f"T{temporada} E{numero} - {titulo}"
            )

            nuevo = desbloquear_enlace(origen)

            if nuevo:
                episodio["url"] = nuevo
                renovados += 1
                print("  Enlace renovado correctamente.")
            else:
                fallidos += 1
                print("  No se pudo renovar.")

            time.sleep(2)

    return renovados, protegidos, fallidos


# ==========================================================
# PROGRAMA PRINCIPAL
# ==========================================================

def main():
    print("----------------------------------------")
    print("SHARKTV - RENOVADOR DE ENLACES ALLDEBRID")
    print("----------------------------------------")

    peliculas = leer_json("peliculas.json", [])
    episodios = leer_json("episodios.json", {})

    print("\nRenovando peliculas...")

    p_ok, p_protegidos, p_error = renovar_peliculas(peliculas)

    print("\nRenovando episodios...")

    e_ok, e_protegidos, e_error = renovar_episodios(episodios)

    # Solo guardar los dos catalogos que contienen enlaces.
    guardar_json("peliculas.json", peliculas)
    guardar_json("episodios.json", episodios)

    print("\n----------------------------------------")
    print("RESUMEN")
    print("----------------------------------------")
    print(f"Peliculas renovadas: {p_ok}")
    print(f"Episodios renovados: {e_ok}")
    print(f"Enlaces protegidos: {p_protegidos + e_protegidos}")
    print(f"Enlaces que no se pudieron renovar: {p_error + e_error}")
    print("----------------------------------------")
    print("Proceso terminado.")


if __name__ == "__main__":
    main()
