"""Regras compartilhadas pelas interfaces gráfica e de terminal."""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


APP_DIR = Path(__file__).resolve().parent
DEFAULT_DOWNLOAD_DIR = APP_DIR / "downloads"
SETTINGS_FILE = APP_DIR / "settings.json"
HISTORY_FILE = APP_DIR / "history.json"
AUDIO_FORMATS = ("mp3", "m4a", "wav", "flac")
VIDEO_FORMATS = ("mp4", "mkv", "webm")
DEFAULT_RESOLUTIONS = (
    "Melhor qualidade",
    "1080p",
    "720p",
    "480p",
    "360p",
    "Só o áudio",
)
DEFAULT_SETTINGS = {
    "output_dir": str(DEFAULT_DOWNLOAD_DIR),
    "resolution": DEFAULT_RESOLUTIONS[0],
    "format": VIDEO_FORMATS[0],
    "skip_existing": True,
    "theme": "dark",
}
MAX_HISTORY_ENTRIES = 200


class DownloadCancelled(Exception):
    """Interrompe o yt-dlp quando o usuário solicita cancelamento."""


def validate_url(value: str) -> str:
    """Valida uma URL HTTP(S) e devolve a versão sem espaços externos."""
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Informe uma URL completa começando com http:// ou https://.")
    return url


def sanitize_filename(value: str, fallback: str = "downloads") -> str:
    """Cria um nome de pasta compatível com Windows, macOS e Linux."""
    cleaned = re.sub(r'[\\/*?:"<>|\x00-\x1f]', "_", value).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:120] or fallback


def available_resolutions(info: dict) -> list[str]:
    """Extrai resoluções reais de um vídeo sem repetir alturas."""
    heights = {
        item.get("height")
        for item in info.get("formats") or []
        if item.get("vcodec") != "none" and item.get("height")
    }
    choices = [f"{height}p" for height in sorted(heights, reverse=True)]
    for fallback in ("Melhor qualidade", "Só o áudio"):
        if fallback not in choices:
            choices.append(fallback)
    return choices


def is_collection(info: dict) -> bool:
    return info.get("_type") in {"playlist", "channel", "multi_video"}


def collection_size(info: dict) -> int:
    entries = info.get("entries") or []
    try:
        return len(entries)
    except TypeError:
        return 0


def runtime_status() -> dict[str, str | None]:
    """Localiza dependências externas sem modificar o computador."""
    return {"ffmpeg": shutil.which("ffmpeg"), "node": shutil.which("node")}


def js_runtime_options(node_path: str | None = None) -> dict:
    path = node_path if node_path is not None else shutil.which("node")
    return {"js_runtimes": {"node": {"args": [path]}}} if path else {}


def _video_selector(resolution: str, output_format: str) -> str:
    height = ""
    if resolution != "Melhor qualidade":
        height = f"[height<={int(resolution.removesuffix('p'))}]"

    if output_format == "mp4":
        preferred = f"bestvideo{height}[ext=mp4]+bestaudio[ext=m4a]"
        progressive = f"best{height}[ext=mp4]"
    elif output_format == "webm":
        preferred = f"bestvideo{height}[ext=webm]+bestaudio[ext=webm]"
        progressive = f"best{height}[ext=webm]"
    else:
        return f"bestvideo{height}+bestaudio/best{height}"

    # O fallback genérico mantém o download funcional quando o site não oferece
    # contêineres específicos para a resolução escolhida.
    generic = f"bestvideo{height}+bestaudio/best{height}"
    return f"{preferred}/{progressive}/{generic}"


def build_ydl_options(
    resolution: str,
    output_format: str,
    output_template: str,
    *,
    progress_hook=None,
    archive_file: str | None = None,
    node_path: str | None = None,
    logger=None,
) -> dict:
    """Monta opções consistentes do yt-dlp para GUI e CLI."""
    if resolution == "Só o áudio":
        if output_format not in AUDIO_FORMATS:
            raise ValueError(f"Formato de áudio inválido: {output_format}")
    elif output_format not in VIDEO_FORMATS:
        raise ValueError(f"Formato de vídeo inválido: {output_format}")

    opts = {
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "windowsfilenames": os.name == "nt",
        "continuedl": True,
    }
    opts.update(js_runtime_options(node_path))
    if progress_hook:
        opts["progress_hooks"] = [progress_hook]
    if archive_file:
        opts["download_archive"] = archive_file
    if logger:
        opts["logger"] = logger

    if resolution == "Só o áudio":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": output_format,
            "preferredquality": "192",
        }]
    else:
        opts["format"] = _video_selector(resolution, output_format)
        opts["merge_output_format"] = output_format

    return opts


def readable_error(error: Exception | str) -> str:
    """Remove prefixos redundantes e evita caixas de erro gigantes."""
    message = str(error).strip()
    message = re.sub(r"^(ERROR:\s*)+", "", message, flags=re.IGNORECASE)
    return message[:900] or "Ocorreu um erro desconhecido."


def load_settings() -> dict:
    """Carrega preferências salvas, preenchendo o que faltar com o padrão."""
    settings = dict(DEFAULT_SETTINGS)
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            settings.update({key: value for key, value in saved.items() if key in DEFAULT_SETTINGS})
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return settings


def save_settings(**values) -> None:
    """Salva preferências do usuário para a próxima execução."""
    settings = load_settings()
    settings.update({key: value for key, value in values.items() if key in DEFAULT_SETTINGS})
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def load_history() -> list[dict]:
    """Carrega o histórico de downloads concluídos, mais recentes primeiro."""
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def add_history_entry(title: str, url: str, destination: str | Path) -> None:
    """Registra um download concluído no histórico local."""
    entries = load_history()
    entries.insert(
        0,
        {
            "title": title or "Sem título",
            "url": url,
            "destination": str(destination),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        },
    )
    del entries[MAX_HISTORY_ENTRIES:]
    try:
        HISTORY_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def clear_history() -> None:
    """Remove todo o histórico de downloads salvo."""
    try:
        HISTORY_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def split_urls(raw_text: str) -> list[str]:
    """Divide um bloco de texto em links únicos, ignorando linhas vazias/duplicadas."""
    seen: set[str] = set()
    urls: list[str] = []
    for line in raw_text.splitlines():
        candidate = line.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        urls.append(candidate)
    return urls
