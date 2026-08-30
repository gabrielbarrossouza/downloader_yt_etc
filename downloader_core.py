"""Regras compartilhadas pelas interfaces gráfica e de terminal."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


APP_DIR = Path(__file__).resolve().parent
DEFAULT_DOWNLOAD_DIR = APP_DIR / "downloads"
SETTINGS_FILE = APP_DIR / "settings.json"
HISTORY_FILE = APP_DIR / "history.json"
LOG_FILE = APP_DIR / "downloader.log"
AUDIO_FORMATS = ("mp3", "m4a", "wav", "flac")
VIDEO_FORMATS = ("mp4", "mkv", "webm")
AUDIO_QUALITIES = ("Melhor", "320 kbps", "256 kbps", "192 kbps", "128 kbps")
COOKIE_BROWSERS = ("Nenhum", "Firefox", "Chrome", "Edge", "Brave", "Opera", "Vivaldi")
SUBTITLE_LANGS = ("pt-BR", "pt", "en", "es")
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
    "audio_quality": "192 kbps",
    "embed_metadata": True,
    "embed_thumbnail": True,
    "download_subtitles": False,
    "subtitle_langs": "pt-BR, en",
    "embed_subtitles": True,
    "cookies_browser": "Nenhum",
    "include_id": True,
    "restrict_filenames": False,
    "speed_limit_mbps": "",
}
MAX_HISTORY_ENTRIES = 200

# Frases exibidas durante o pós-processamento do FFmpeg.
POSTPROCESSOR_PHASES = {
    "Merger": "Unindo vídeo e áudio…",
    "FFmpegMerger": "Unindo vídeo e áudio…",
    "FFmpegExtractAudio": "Extraindo o áudio…",
    "ExtractAudio": "Extraindo o áudio…",
    "FFmpegVideoConvertor": "Convertendo o vídeo…",
    "FFmpegVideoRemuxer": "Ajustando o contêiner…",
    "EmbedThumbnail": "Inserindo a capa…",
    "FFmpegEmbedThumbnail": "Inserindo a capa…",
    "FFmpegMetadata": "Gravando os metadados…",
    "FFmpegEmbedSubtitle": "Embutindo as legendas…",
}

# Padrões de erro comuns → dica em português.
_ERROR_HINTS = (
    (r"age.?restrict|age.?gate|confirm your age|inappropriate for some users",
     "Conteúdo com restrição de idade. Selecione o navegador onde você está logado em “Cookies”."),
    (r"sign in to confirm you.?re not a bot|login required|requires authentication|private (video|content)|members-only|this video is available to",
     "O site exige uma conta conectada. Escolha um navegador em “Cookies” nas opções."),
    (r"geo.?restrict|not available in your country|blocked it in your country|content is not available in your",
     "Este conteúdo está bloqueado na sua região."),
    (r"http error 429|too many requests|rate.?limit|temporarily blocked",
     "O site limitou as requisições. Aguarde alguns minutos antes de tentar de novo."),
    (r"video unavailable|content isn.?t available|removed by the uploader|this video has been removed|deleted",
     "O conteúdo não está mais disponível na origem."),
    (r"ffmpeg|ffprobe|postprocessing",
     "Falha no FFmpeg. Confirme se ele está instalado e disponível no PATH."),
    (r"unsupported url|no suitable extractor|unable to extract",
     "O yt-dlp não sabe baixar deste site ou o link mudou de formato."),
    (r"winerror 5|permission denied|access is denied|read-only file system",
     "Sem permissão para gravar na pasta escolhida. Selecione outra pasta de destino."),
    (r"no space left|not enough space|disco",
     "Espaço em disco insuficiente para concluir o download."),
)


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


def engine_version() -> str:
    """Versão instalada do yt-dlp (motor de download)."""
    try:
        import yt_dlp

        return yt_dlp.version.__version__
    except Exception:
        return "desconhecida"


def update_engine(timeout: int = 240) -> tuple[bool, str]:
    """Atualiza o yt-dlp via pip. Retorna (sucesso, mensagem)."""
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--disable-pip-version-check",
                "yt-dlp",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as error:
        return False, readable_error(error)
    if result.returncode == 0:
        if "already satisfied" in (result.stdout or "").lower():
            return True, f"O yt-dlp já está atualizado ({engine_version()})."
        return True, "yt-dlp atualizado. Reinicie o aplicativo para carregar a nova versão."
    return False, readable_error(result.stderr or result.stdout or "Falha ao atualizar o yt-dlp.")


def _speed_limit_bytes(value: str | float | None) -> float | None:
    """Converte um limite em MB/s (texto ou número) para bytes por segundo."""
    if value in (None, ""):
        return None
    try:
        mbps = float(str(value).replace(",", "."))
    except ValueError:
        return None
    return mbps * 1024 * 1024 if mbps > 0 else None


def build_output_template(base_dir: str | Path, *, collection: bool, include_id: bool = True) -> str:
    """Modelo de nome de arquivo do yt-dlp, igual para GUI e CLI."""
    tag = " [%(id)s]" if include_id else ""
    base = Path(base_dir)
    if collection:
        return str(base / f"%(playlist_index)03d - %(title)s{tag}.%(ext)s")
    return str(base / f"%(title)s{tag}.%(ext)s")


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


def _preferred_audio_quality(label: str) -> str:
    return {
        "Melhor": "0",
        "320 kbps": "320",
        "256 kbps": "256",
        "192 kbps": "192",
        "128 kbps": "128",
    }.get(label, "192")


def parse_subtitle_langs(raw: str) -> list[str]:
    """Normaliza uma lista de idiomas separada por vírgula ou espaço."""
    parts = re.split(r"[\s,;]+", (raw or "").strip())
    seen: set[str] = set()
    langs: list[str] = []
    for part in parts:
        code = part.strip()
        if code and code.lower() not in seen:
            seen.add(code.lower())
            langs.append(code)
    return langs


def build_ydl_options(
    resolution: str,
    output_format: str,
    output_template: str,
    *,
    progress_hook=None,
    postprocessor_hook=None,
    archive_file: str | None = None,
    node_path: str | None = None,
    logger=None,
    audio_quality: str = "192 kbps",
    embed_metadata: bool = True,
    embed_thumbnail: bool = True,
    subtitle_langs: list[str] | None = None,
    embed_subtitles: bool = True,
    cookies_from_browser: str | None = None,
    playlist_items: str | None = None,
    speed_limit_mbps: str | float | None = None,
    restrict_filenames: bool = False,
    tolerate_errors: bool = False,
) -> dict:
    """Monta opções consistentes do yt-dlp para GUI e CLI."""
    audio_only = resolution == "Só o áudio"
    if audio_only:
        if output_format not in AUDIO_FORMATS:
            raise ValueError(f"Formato de áudio inválido: {output_format}")
    elif output_format not in VIDEO_FORMATS:
        raise ValueError(f"Formato de vídeo inválido: {output_format}")

    opts: dict = {
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "windowsfilenames": os.name == "nt",
        "restrictfilenames": bool(restrict_filenames),
        "trim_file_name": 120,
        "continuedl": True,
        "noplaylist": False,
        # Robustez de rede: tentativas generosas e pausa entre requisições.
        "concurrent_fragment_downloads": 5,
        "retries": 10,
        "fragment_retries": 10,
        "file_access_retries": 5,
        "extractor_retries": 3,
        "retry_sleep_functions": {
            "http": lambda n: min(4 * n, 30),
            "fragment": lambda n: min(2 * n, 20),
        },
        "sleep_interval_requests": 0.25,
    }
    opts.update(js_runtime_options(node_path))

    if tolerate_errors:
        opts["ignoreerrors"] = "only_download"

    limit = _speed_limit_bytes(speed_limit_mbps)
    if limit:
        opts["ratelimit"] = limit

    if cookies_from_browser and cookies_from_browser != "Nenhum":
        opts["cookiesfrombrowser"] = (cookies_from_browser.lower(),)

    if playlist_items:
        opts["playlist_items"] = str(playlist_items).strip()

    if progress_hook:
        opts["progress_hooks"] = [progress_hook]
    if postprocessor_hook:
        opts["postprocessor_hooks"] = [postprocessor_hook]
    if archive_file:
        opts["download_archive"] = archive_file
    if logger:
        opts["logger"] = logger

    postprocessors: list[dict] = []

    if audio_only:
        opts["format"] = "bestaudio/best"
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": output_format,
                "preferredquality": _preferred_audio_quality(audio_quality),
            }
        )
        thumb_ok = embed_thumbnail and output_format in {"mp3", "m4a", "flac"}
    else:
        opts["format"] = _video_selector(resolution, output_format)
        opts["merge_output_format"] = output_format
        # Só o MKV aceita capa embutida via FFmpeg sem depender do AtomicParsley.
        thumb_ok = embed_thumbnail and output_format == "mkv"

        if subtitle_langs:
            opts["writesubtitles"] = True
            opts["writeautomaticsub"] = True
            opts["subtitleslangs"] = list(subtitle_langs)
            if embed_subtitles and output_format in {"mp4", "mkv"}:
                postprocessors.append({"key": "FFmpegEmbedSubtitle"})

    if embed_metadata:
        postprocessors.append(
            {"key": "FFmpegMetadata", "add_metadata": True, "add_chapters": True}
        )
    if thumb_ok:
        opts["writethumbnail"] = True
        postprocessors.append({"key": "EmbedThumbnail"})

    if postprocessors:
        opts["postprocessors"] = postprocessors

    return opts


def readable_error(error: Exception | str) -> str:
    """Remove prefixos redundantes e evita caixas de erro gigantes."""
    message = str(error).strip()
    message = re.sub(r"^(ERROR:\s*)+", "", message, flags=re.IGNORECASE)
    return message[:900] or "Ocorreu um erro desconhecido."


def explain_error(error: Exception | str) -> str:
    """Mensagem amigável para os erros mais comuns, com o detalhe técnico ao fim."""
    message = readable_error(error)
    lowered = message.lower()
    for pattern, hint in _ERROR_HINTS:
        if re.search(pattern, lowered):
            return f"{hint}\n\nDetalhe técnico: {message[:300]}"
    return message


def postprocessor_phase(name: str | None) -> str | None:
    """Traduz o nome de um pós-processador do yt-dlp para uma frase de status."""
    if not name:
        return None
    return POSTPROCESSOR_PHASES.get(name)


def append_log(message: str) -> None:
    """Registra uma linha em downloader.log para diagnóstico posterior."""
    try:
        stamp = datetime.now().isoformat(timespec="seconds")
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp}  {message}\n")
    except OSError:
        pass


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


def add_history_entry(
    title: str,
    url: str,
    destination: str | Path,
    *,
    filepath: str | Path | None = None,
) -> None:
    """Registra um download concluído no histórico local."""
    entries = load_history()
    entries.insert(
        0,
        {
            "title": title or "Sem título",
            "url": url,
            "destination": str(destination),
            "filepath": str(filepath) if filepath else "",
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


def _write_history(entries: list[dict]) -> None:
    try:
        HISTORY_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def delete_history_entry(index: int) -> None:
    """Remove um único item do histórico pela posição (0 = mais recente)."""
    entries = load_history()
    if 0 <= index < len(entries):
        del entries[index]
        _write_history(entries)


def remove_history_entry(url: str, timestamp: str) -> None:
    """Remove o item que casa com (url, timestamp), independente da ordenação exibida."""
    entries = [
        entry
        for entry in load_history()
        if not (entry.get("url") == url and entry.get("timestamp") == timestamp)
    ]
    _write_history(entries)


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
