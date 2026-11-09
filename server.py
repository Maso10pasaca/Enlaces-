"""Enlaces+ remote MCP server.

Downloads audio from a single publicly reachable HTTPS video URL and transcribes
speech with faster-whisper. The HTTP endpoint is protected by a required Bearer
token. This service does not bypass logins, private-video controls, CAPTCHAs or DRM.
"""
from __future__ import annotations

import asyncio
import hmac
import ipaddress
import os
import shutil
import socket
import subprocess
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from faster_whisper import WhisperModel
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
import uvicorn

SERVICE_NAME = "Enlaces+"
MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")
MAX_FILE_BYTES = int(os.getenv("MAX_FILE_BYTES", str(200 * 1024 * 1024)))
MAX_CONCURRENT_JOBS = max(1, int(os.getenv("MAX_CONCURRENT_JOBS", "1")))
API_TOKEN = os.getenv("ENLACES_API_TOKEN", "")
PORT = int(os.getenv("PORT", "8000"))

mcp = FastMCP(SERVICE_NAME)
_model: WhisperModel | None = None
_model_lock = threading.Lock()
_job_limit = asyncio.Semaphore(MAX_CONCURRENT_JOBS)


def _allowed_hosts() -> list[str]:
    configured = os.getenv("MCP_ALLOWED_HOSTS", "").strip()
    if configured:
        return [entry.strip() for entry in configured.split(",") if entry.strip()]
    external = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if external:
        return [external, f"{external}:*"]
    # Safe defaults for local development and automated tests.
    return ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*", "[::1]", "[::1]:*"]


def _validate_url(url: str) -> str:
    """Validate a public HTTPS URL before passing it to yt-dlp."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Proporciona un enlace de vídeo válido.")
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("Solo se admiten enlaces HTTPS.")
    if parsed.username or parsed.password:
        raise ValueError("No se admiten URLs que incluyan credenciales.")
    if parsed.port not in (None, 443):
        raise ValueError("Solo se admite el puerto HTTPS estándar (443).")

    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("No se permiten dominios locales o internos.")

    try:
        literal_ip = ipaddress.ip_address(host)
        addresses = [literal_ip]
    except ValueError:
        try:
            resolved = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError("No se pudo resolver el dominio del enlace.") from exc
        addresses = [ipaddress.ip_address(item[4][0]) for item in resolved]

    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("El enlace resuelve a una dirección no pública y se ha bloqueado.")
    return url.strip()


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                # Quantized CPU model: designed to fit the free Render instance.
                _model = WhisperModel(
                    MODEL_SIZE,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=1,
                    num_workers=1,
                )
    return _model


def _download_audio(url: str, output_dir: Path) -> tuple[Path, str]:
    checked_url = _validate_url(url)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg no está instalado en el servidor.")

    template = str(output_dir / "source.%(ext)s")
    options = {
        "format": "bestaudio/best",
        "outtmpl": template,
        "noplaylist": True,
        "max_filesize": MAX_FILE_BYTES,
        "socket_timeout": 25,
        "retries": 2,
        "fragment_retries": 2,
        "quiet": True,
        "no_warnings": True,
        "overwrites": True,
        "nopart": False,
    }

    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(checked_url, download=True)
        if info.get("_type") == "playlist" or info.get("entries") is not None:
            raise ValueError("Enlaces+ procesa un vídeo cada vez, no listas de reproducción.")
        title = str(info.get("title") or "Vídeo")[:200]
        expected_path = Path(downloader.prepare_filename(info))

    candidates = [expected_path] if expected_path.exists() else []
    if not candidates:
        candidates = [
            path for path in output_dir.glob("source.*")
            if path.is_file() and path.suffix.lower() not in {".part", ".ytdl"}
        ]
    if not candidates:
        raise RuntimeError("La plataforma no proporcionó una pista de audio descargable.")

    source = candidates[0]
    if source.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("El audio supera el límite de 200 MB.")

    target = output_dir / "audio.mp3"
    command = [
        ffmpeg, "-nostdin", "-y", "-v", "error",
        "-i", str(source), "-vn", "-ac", "1", "-ar", "16000",
        "-b:a", "48k", "-threads", "1", str(target),
    ]
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("La conversión del audio excedió el tiempo permitido.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "")[-1000:]
        raise RuntimeError(f"FFmpeg no pudo convertir el audio: {detail}") from exc

    if not target.is_file() or target.stat().st_size == 0:
        raise RuntimeError("FFmpeg no generó un archivo de audio válido.")
    return target, title


def _transcribe(path: Path, language: str) -> tuple[str, str, float]:
    model = _get_model()
    requested_language = None if language.strip().lower() in {"", "auto", "automatico", "automático"} else language.strip()
    segments, info = model.transcribe(
        str(path),
        language=requested_language,
        vad_filter=True,
        beam_size=3,
    )
    transcript = " ".join(segment.text.strip() for segment in segments).strip()
    return transcript, str(info.language), float(info.language_probability)


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> Response:
    """Public liveness endpoint used by the hosting platform."""
    return JSONResponse({"status": "ok", "service": "enlaces-plus"})


@mcp.tool()
async def transcribe_video_audio(url: str, language: str = "auto") -> dict:
    """Extrae el audio de un vídeo público y devuelve su transcripción. Idioma: auto, es, en, etc."""
    async with _job_limit:
        temp_dir = Path(tempfile.mkdtemp(prefix="enlaces-plus-"))
        try:
            audio_path, title = await asyncio.to_thread(_download_audio, url, temp_dir)
            transcript, detected_language, probability = await asyncio.to_thread(
                _transcribe, audio_path, language
            )
            return {
                "title": title,
                "language": detected_language,
                "language_probability": round(probability, 4),
                "transcription": transcript,
                "speech_detected": bool(transcript),
            }
        except Exception as exc:
            # Keep the error useful without returning environment paths or credentials.
            return {
                "error": f"No se pudo procesar el vídeo: {type(exc).__name__}: {str(exc)[:1200]}"
            }
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class BearerTokenMiddleware:
    """Require a fixed, high-entropy Bearer token for every MCP HTTP request."""

    def __init__(self, app, token: str):
        self.app = app
        self.token = token.encode("utf-8")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not (
            scope.get("path") == "/mcp" or scope.get("path", "").startswith("/mcp/")
        ):
            await self.app(scope, receive, send)
            return

        if not self.token:
            response = JSONResponse(
                {"error": "server_misconfigured", "message": "ENLACES_API_TOKEN no está configurado."},
                status_code=503,
            )
            await response(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization", b"").decode("latin-1")
        scheme, separator, supplied = authorization.partition(" ")
        valid = (
            bool(separator)
            and scheme.lower() == "bearer"
            and bool(supplied)
            and hmac.compare_digest(supplied.encode("utf-8"), self.token)
        )
        if not valid:
            response = JSONResponse(
                {"error": "unauthorized", "message": "Se requiere un token Bearer válido."},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


security = TransportSecuritySettings(allowed_hosts=_allowed_hosts())
app = mcp.streamable_http_app(transport_security=security)
app.add_middleware(BearerTokenMiddleware, token=API_TOKEN)


if __name__ == "__main__":
    if not API_TOKEN or len(API_TOKEN) < 32:
        raise SystemExit(
            "Configuración incompleta: define ENLACES_API_TOKEN con al menos 32 caracteres."
        )
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
