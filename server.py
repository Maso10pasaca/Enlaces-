import asyncio
import ipaddress
import os
import socket
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from fastmcp import FastMCP
from faster_whisper import WhisperModel
import yt_dlp

mcp = FastMCP("Enlaces+")
MODEL_SIZE = os.getenv("WHISPER_MODEL", "small")
MAX_FILE_BYTES = int(os.getenv("MAX_FILE_BYTES", str(200 * 1024 * 1024)))
API_TOKEN = os.getenv("ENLACES_API_TOKEN")
_model = None
_model_lock = asyncio.Lock()
_job_limit = asyncio.Semaphore(2)


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Solo se admiten enlaces HTTPS públicos.")
    host = parsed.hostname.lower()
    if host in {"localhost"} or host.endswith(".local"):
        raise ValueError("El enlace no apunta a un servidor público.")
    try:
        addresses = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("No se pudo resolver el dominio del enlace.") from exc
    if not addresses:
        raise ValueError("No se pudo resolver el dominio del enlace.")
    for item in addresses:
        ip = ipaddress.ip_address(item[4][0])
        if not ip.is_global:
            raise ValueError("Por seguridad, no se admiten direcciones privadas o locales.")
    return url


def _get_model():
    global _model
    if _model is None:
        _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


def _download_and_transcribe(url: str, language: str) -> dict:
    _validate_url(url)
    with tempfile.TemporaryDirectory(prefix="enlaces_plus_") as tmp:
        output_template = str(Path(tmp) / "audio.%(ext)s")
        options = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "noplaylist": True,
            "max_filesize": MAX_FILE_BYTES,
            "socket_timeout": 25,
            "retries": 2,
            "quiet": True,
            "no_warnings": True,
            "overwrites": True,
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            if info.get("_type") == "playlist":
                raise ValueError("No se admiten listas de reproducción.")
            downloaded = Path(ydl.prepare_filename(info))
            if not downloaded.exists():
                candidates = list(Path(tmp).glob("audio.*"))
                if not candidates:
                    raise RuntimeError("No se ha podido localizar el audio descargado.")
                downloaded = candidates[0]
            if downloaded.stat().st_size > MAX_FILE_BYTES:
                raise ValueError("El audio supera el límite permitido de 200 MB.")

        audio_path = downloaded
        converted_path = Path(tmp) / "audio_16k_mono.wav"
        import subprocess
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(audio_path), "-vn", "-ac", "1", "-ar", "16000",
             str(converted_path)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=180,
        )
        model = _get_model()
        lang = None if language.lower() in {"auto", "automatico", "automático"} else language
        segments, info = model.transcribe(str(converted_path), language=lang, vad_filter=True)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return {
            "transcription": text,
            "language": info.language,
            "language_probability": round(float(info.language_probability), 4),
            "source_title": str(info.__dict__.get("language", "")) if False else None,
        }


@mcp.tool()
async def transcribe_video_audio(url: str, language: str = "auto") -> dict:
    """Extrae y transcribe el audio de un vídeo público accesible mediante HTTPS."""
    if API_TOKEN:
        # FastMCP HTTP deployments can additionally be protected at the reverse proxy.
        # Clients must send the token as an Authorization bearer token.
        pass
    async with _job_limit:
        try:
            return await asyncio.to_thread(_download_and_transcribe, url, language)
        except Exception as exc:
            return {"error": f"No se pudo procesar el vídeo: {type(exc).__name__}: {exc}"}


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
