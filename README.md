# Enlaces+

Enlaces+ extrae el audio de un vídeo públicamente accesible y devuelve una transcripción del habla para que puedas consultarla desde un cliente MCP.

## Estado del despliegue

El repositorio incluye un servidor MCP remoto, Dockerfile y Blueprint de Render. El despliegue **no se crea automáticamente al subir el código**: hay que autorizar la conexión GitHub-Render y confirmar la creación del servicio. El Blueprint elige el plan gratuito y el modelo Whisper `base` para evitar activar costes sin autorización.

## Características

- Herramienta MCP: `transcribe_video_audio(url, language="auto")`.
- Transporte remoto MCP Streamable HTTP en `/mcp`.
- Protección obligatoria mediante token Bearer de alta entropía.
- Endpoint público de salud: `/health`.
- Descarga de audio con yt-dlp y conversión mono a 16 kHz con FFmpeg.
- Transcripción local con faster-whisper (CPU/int8).
- Límite de descarga de 200 MB y una tarea simultánea.
- Limpieza de archivos temporales al terminar.

## Despliegue en Render desde el móvil

1. Abre el botón de despliegue del repositorio: https://render.com/deploy?repo=https://github.com/Maso10pasaca/Enlaces-
2. Inicia sesión o crea una cuenta en Render.
3. Autoriza el acceso al repositorio `Maso10pasaca/Enlaces-`.
4. Revisa el Blueprint. Debe mostrar el plan **Free**; no cambies a un plan de pago sin decidirlo.
5. Confirma la creación del servicio. Render generará automáticamente `ENLACES_API_TOKEN`.
6. Cuando termine, la URL pública tendrá el formato `https://enlaces-plus-maso10pasaca.onrender.com`; el endpoint MCP será `/mcp`.

Render asigna `RENDER_EXTERNAL_HOSTNAME`; el servidor lo usa para validar el encabezado Host. Si el nombre asignado es distinto, define `MCP_ALLOWED_HOSTS` con el hostname real (sin esquema, separado por comas).

## Ejecución local

Requiere Python 3.11+, FFmpeg y un secreto de al menos 32 caracteres:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ENLACES_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python server.py
```

Endpoint: `http://localhost:8000/mcp`. Health check: `http://localhost:8000/health`.

## Seguridad

- Se exige `Authorization: Bearer <ENLACES_API_TOKEN>` en todas las peticiones MCP.
- No se admiten URLs HTTP, credenciales embebidas, puertos no estándar, localhost, dominios locales ni direcciones IP no públicas.
- No se proporcionan cookies ni credenciales a yt-dlp.
- No se intenta eludir sesiones, vídeos privados, CAPTCHA, DRM, paywalls ni controles de acceso.
- La validación DNS bloquea direcciones no públicas antes de iniciar yt-dlp. Como yt-dlp sigue los redireccionamientos de los proveedores, esta validación inicial no sustituye a un cortafuegos de salida; el alojamiento debe mantener el aislamiento de red.
- No registres ni compartas el token. Si se filtra, rótalo desde las variables de entorno de Render.

## Limitaciones del plan gratuito

Render puede suspender un servicio gratuito tras inactividad y el primer uso puede tardar mientras Whisper descarga su modelo. El modelo `base` reduce el consumo de memoria, con una precisión inferior a `small`. Para un modelo `small` y un uso sin suspensión se necesitará un plan con más RAM y coste asociado.
