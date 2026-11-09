# Enlaces+

Enlaces+ extrae el audio de un vídeo público y devuelve su transcripción para que puedas consultar qué se dice en él.

## Requisitos
- Python 3.11+
- FFmpeg
- Dependencias de `requirements.txt`

## Ejecución local
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

El servidor MCP utiliza Streamable HTTP en `/mcp` (puerto 8000 por defecto). La primera ejecución descarga el modelo Whisper configurado.

## Despliegue
El repositorio incluye un `Dockerfile` y un manifiesto `render.yaml` para facilitar el despliegue en un servicio compatible con contenedores. Configura un secreto `ENLACES_API_TOKEN` y exige autenticación Bearer en el proxy o gateway que exponga el servicio.

## Herramienta
`transcribe_video_audio(url, language="auto")`

- Acepta una URL HTTPS pública.
- No procesa listas de reproducción.
- Límite de descarga: 200 MB.
- Detecta automáticamente el idioma si se usa `auto`.
- El audio temporal se elimina al terminar.

## Seguridad y límites
No intenta acceder a vídeos privados, iniciar sesión, resolver CAPTCHA ni eludir DRM o controles de acceso. El servicio debe desplegarse detrás de una capa de autenticación que valide el token antes de permitir llamadas. La comprobación DNS inicial no sustituye a un aislamiento de red; despliega el servicio en un entorno restringido y bloquea rangos privados/metadata a nivel de red.
