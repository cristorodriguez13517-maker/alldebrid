# SHARKTV ALLDEBRID APK — proyecto inicial

## Qué hace
- Lee `peliculas.json` y `episodios.json` del repositorio `cristorodriguez13517-maker/alldebrid`.
- Busca enlaces pendientes en `pending_url` o enlaces antiguos `/f/` guardados en `stream_url` / `url`.
- Desbloquea cada enlace mediante la API oficial de AllDebrid desde el propio Android.
- Guarda el enlace directo `/dl/` en el campo correspondiente.
- No sustituye un enlace que ya sea directo.
- `series.json` se consulta, pero no se modifica porque no contiene enlaces de reproducción.

## Preparar el repositorio
1. Descarga y descomprime este ZIP.
2. Sube el contenido de la carpeta `SHARKTV_ALLDEBRID_APK` a la raíz de un repositorio GitHub nuevo o a la raíz del repositorio `alldebrid`.
3. Conserva las carpetas tal como están, especialmente `.github/workflows/`.
4. En GitHub abre **Actions** y ejecuta **Construir APK SHARKTV ALLDEBRID**.
5. Al terminar, abre la ejecución y descarga el artefacto `SHARKTV-ALLDEBRID-APK`. Dentro estará `app-debug.apk`.

## Credenciales dentro de la aplicación
- Clave API de AllDebrid.
- Token de GitHub con acceso al repositorio y permiso **Contents: Read and write**.

No compartas esas credenciales ni las pegues en conversaciones. Si creas un token solo para esta aplicación, limita su acceso al repositorio `alldebrid`.

## Uso
1. Instala la APK en tu Android.
2. Introduce las dos credenciales y guárdalas.
3. Pulsa **COMPLETAR ENLACES PENDIENTES**.
4. Espera a que termine y revisa el registro de actividad.

La primera versión se ejecuta al pulsar el botón; no trabaja en segundo plano ni se ejecuta automáticamente.

## Importante
La API puede rechazar enlaces concretos por límites, indisponibilidad del servidor, enlaces caídos o errores de AllDebrid. Esos enlaces quedan sin modificar para volver a intentarlo más adelante.
