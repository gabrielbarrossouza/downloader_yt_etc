from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import questionary
import yt_dlp
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.prompt import Confirm, Prompt
from rich.table import Table

from downloader_core import (
    AUDIO_FORMATS,
    AUDIO_QUALITIES,
    COOKIE_BROWSERS,
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_RESOLUTIONS,
    VIDEO_FORMATS,
    add_history_entry,
    available_resolutions,
    build_output_template,
    build_ydl_options,
    collection_size,
    engine_version,
    explain_error,
    is_collection,
    js_runtime_options,
    load_history,
    load_settings,
    parse_subtitle_langs,
    postprocessor_phase,
    runtime_status,
    sanitize_filename,
    save_settings,
    update_engine,
    validate_url,
)


console = Console()


class MyLogger:
    def debug(self, _message):
        pass

    def info(self, _message):
        pass

    def warning(self, message):
        console.print(f"[yellow]Aviso: {message}[/yellow]")

    def error(self, message):
        console.print(f"[red]Erro: {message}[/red]")


class RichDownloader:
    def __init__(self, output_dir: Path = DEFAULT_DOWNLOAD_DIR, settings: dict | None = None):
        self.output_dir = output_dir.expanduser().resolve()
        self.settings = settings or load_settings()
        self.runtimes = runtime_status()
        self.tasks: dict[str, int] = {}
        self.completed_ids: set[str] = set()
        self.video_index = 0
        self.total_videos = 0
        self.last_filepath: str | None = None
        self.forced_items: str | None = None
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.fields[filename]}", justify="right"),
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>3.1f}%",
            "•",
            DownloadColumn(),
            "•",
            TransferSpeedColumn(),
            "•",
            TimeRemainingColumn(),
            console=console,
        )

    def show_runtime_status(self):
        ffmpeg = "[green]pronto[/green]" if self.runtimes["ffmpeg"] else "[red]não encontrado[/red]"
        node = "[green]pronto[/green]" if self.runtimes["node"] else "[yellow]opcional, não encontrado[/yellow]"
        console.print(
            f"[dim]FFmpeg:[/dim] {ffmpeg}  [dim]Node.js:[/dim] {node}  "
            f"[dim]yt-dlp:[/dim] {engine_version()}"
        )

    def get_info(self, url: str) -> dict | None:
        with console.status("[bold green]Analisando o link...[/bold green]"):
            options = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": "in_playlist",
            }
            options.update(js_runtime_options(self.runtimes["node"]))
            cookies = self.settings.get("cookies_browser")
            if cookies and cookies != "Nenhum":
                options["cookiesfrombrowser"] = (cookies.lower(),)
            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    return ydl.extract_info(url, download=False)
            except Exception as error:
                console.print(f"[red]Não foi possível analisar o link: {explain_error(error)}[/red]")
                return None

    @staticmethod
    def select_resolution(choices: list[str]) -> str | None:
        return questionary.select("Selecione a qualidade:", choices=choices).ask()

    @staticmethod
    def select_format(resolution: str) -> str | None:
        audio_only = resolution == "Só o áudio"
        kind = "áudio" if audio_only else "vídeo"
        choices = list(AUDIO_FORMATS if audio_only else VIDEO_FORMATS)
        return questionary.select(f"Selecione o formato de {kind}:", choices=choices).ask()

    def _require_ffmpeg(self) -> bool:
        if self.runtimes["ffmpeg"]:
            return True
        console.print(
            "[red]O FFmpeg é necessário para converter áudio e unir vídeo com áudio. "
            "Instale-o e adicione-o ao PATH antes de continuar.[/red]"
        )
        return False

    def _choose_options(self, choices: list[str]) -> dict | None:
        resolution = self.select_resolution(choices)
        if not resolution:
            return None
        output_format = self.select_format(resolution)
        if not output_format:
            return None

        chosen: dict = {"resolution": resolution, "output_format": output_format}

        if resolution == "Só o áudio":
            default_q = self.settings.get("audio_quality", "192 kbps")
            chosen["audio_quality"] = questionary.select(
                "Qualidade do áudio:",
                choices=list(AUDIO_QUALITIES),
                default=default_q if default_q in AUDIO_QUALITIES else "192 kbps",
            ).ask() or "192 kbps"
        else:
            if Confirm.ask("Baixar legendas?", default=bool(self.settings.get("download_subtitles"))):
                raw = Prompt.ask(
                    "Idiomas das legendas (separados por vírgula)",
                    default=self.settings.get("subtitle_langs", "pt-BR, en"),
                )
                chosen["subtitle_langs"] = parse_subtitle_langs(raw)
                chosen["embed_subtitles"] = Confirm.ask(
                    "Embutir as legendas no vídeo?", default=True
                )

        return chosen

    def download_collection(self, url: str, info: dict) -> bool:
        title = info.get("title") or "Coleção"
        self.total_videos = collection_size(info)
        table = Table(box=None, show_header=False, padding=(0, 1))
        table.add_row("[bold cyan]Nome[/bold cyan]", title)
        count = str(self.total_videos) if self.total_videos else "será calculado durante o download"
        table.add_row("[bold cyan]Itens[/bold cyan]", count)
        console.print(Panel(table, title="[bold]Playlist / canal[/bold]", border_style="cyan"))

        chosen = self._choose_options(list(DEFAULT_RESOLUTIONS))
        if not chosen or not self._require_ffmpeg():
            return False

        if self.forced_items is not None:
            items = self.forced_items
        else:
            items = Prompt.ask(
                "Quais itens baixar? (ex.: 1-10, 3,5,9 — vazio = todos)", default=""
            ).strip()
        chosen["playlist_items"] = items or None

        destination = self.output_dir / sanitize_filename(title)
        destination.mkdir(parents=True, exist_ok=True)
        skip_existing = Confirm.ask("Ignorar itens já baixados anteriormente?", default=True)
        archive = str(destination / ".download_archive.txt") if skip_existing else None
        template = build_output_template(
            destination, collection=True, include_id=bool(self.settings.get("include_id", True))
        )
        return self._run_download(url, chosen, template, archive, destination, title, tolerate_errors=True)

    def download_single(self, url: str, info: dict) -> bool:
        title = info.get("title") or "Vídeo"
        console.print(f"[green]Encontrado:[/green] {title}")
        chosen = self._choose_options(available_resolutions(info))
        if not chosen or not self._require_ffmpeg():
            return False

        self.total_videos = 1
        self.output_dir.mkdir(parents=True, exist_ok=True)
        template = build_output_template(
            self.output_dir, collection=False, include_id=bool(self.settings.get("include_id", True))
        )
        return self._run_download(url, chosen, template, None, self.output_dir, title)

    def _run_download(
        self,
        url: str,
        chosen: dict,
        template: str,
        archive: str | None,
        destination: Path,
        title: str,
        *,
        tolerate_errors: bool = False,
    ) -> bool:
        self.video_index = 0
        self.tasks.clear()
        self.completed_ids.clear()
        self.last_filepath = None
        options = build_ydl_options(
            chosen["resolution"],
            chosen["output_format"],
            template,
            progress_hook=self.progress_hook,
            postprocessor_hook=self.postprocessor_hook,
            archive_file=archive,
            node_path=self.runtimes["node"],
            logger=MyLogger(),
            audio_quality=chosen.get("audio_quality", self.settings.get("audio_quality", "192 kbps")),
            embed_metadata=bool(self.settings.get("embed_metadata", True)),
            embed_thumbnail=bool(self.settings.get("embed_thumbnail", True)),
            subtitle_langs=chosen.get("subtitle_langs"),
            embed_subtitles=chosen.get("embed_subtitles", True),
            cookies_from_browser=self.settings.get("cookies_browser"),
            playlist_items=chosen.get("playlist_items"),
            speed_limit_mbps=self.settings.get("speed_limit_mbps"),
            restrict_filenames=bool(self.settings.get("restrict_filenames", False)),
            tolerate_errors=tolerate_errors,
        )
        console.print(f"\n[bold green]Baixando para:[/bold green] [white]{destination}[/white]\n")
        try:
            with self.progress:
                with yt_dlp.YoutubeDL(options) as ydl:
                    result = ydl.download([url])
            if result and not tolerate_errors:
                console.print("[red]O yt-dlp encerrou com falha.[/red]")
                return False
        except KeyboardInterrupt:
            console.print("\n[yellow]Download interrompido. Ele poderá ser retomado depois.[/yellow]")
            return False
        except Exception as error:
            console.print(f"\n[red]Falha no download: {explain_error(error)}[/red]")
            return False

        console.print(f"\n[bold green]✓ Concluído:[/bold green] [white]{destination}[/white]")
        add_history_entry(title, url, destination, filepath=self.last_filepath)
        return True

    def download(self, raw_url: str) -> bool:
        try:
            url = validate_url(raw_url)
        except ValueError as error:
            console.print(f"[red]{error}[/red]")
            return False
        info = self.get_info(url)
        if not info:
            return False
        if is_collection(info):
            return self.download_collection(url, info)
        return self.download_single(url, info)

    def progress_hook(self, data: dict):
        status = data.get("status")
        key = data.get("filename") or str(id(data))
        if status == "downloading":
            filename = Path(data.get("filename") or "arquivo").name
            if len(filename) > 38:
                filename = filename[:35] + "..."
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            downloaded = data.get("downloaded_bytes") or 0
            prefix = f"[{self.video_index + 1}/{self.total_videos}] " if self.total_videos > 1 else ""
            label = prefix + filename
            if key not in self.tasks:
                self.tasks[key] = self.progress.add_task("download", filename=label, total=total or None)
            update = {"completed": downloaded, "filename": label}
            if total:
                update["total"] = total
            self.progress.update(self.tasks[key], **update)
        elif status == "finished":
            if key in self.tasks:
                self.progress.update(self.tasks[key], completed=data.get("total_bytes") or 0)
                self.progress.remove_task(self.tasks.pop(key))
            info = data.get("info_dict") or {}
            self.last_filepath = data.get("filename") or self.last_filepath
            media_id = str(info.get("id") or info.get("webpage_url") or key)
            if media_id not in self.completed_ids:
                self.completed_ids.add(media_id)
                self.video_index += 1
                console.print(f"[green]✓[/green] {Path(data.get('filename') or 'arquivo').name}")

    def postprocessor_hook(self, data: dict):
        phase = postprocessor_phase(data.get("postprocessor"))
        info = data.get("info_dict") or {}
        if info.get("filepath"):
            self.last_filepath = info["filepath"]
        if phase and data.get("status") == "started":
            console.print(f"[dim]{phase}[/dim]")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Baixe vídeos, áudios, playlists e canais com yt-dlp.")
    parser.add_argument("urls", nargs="*", help="Uma ou mais URLs a baixar")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help=f"pasta de destino (padrão: última usada, ou {DEFAULT_DOWNLOAD_DIR})",
    )
    parser.add_argument(
        "--cookies",
        choices=[b.lower() for b in COOKIE_BROWSERS],
        default=None,
        help="usar cookies de um navegador para conteúdo que exige login",
    )
    parser.add_argument("--items", default=None, help="itens da playlist (ex.: 1-10, 3,5)")
    parser.add_argument("--history", action="store_true", help="mostra os downloads mais recentes e sai")
    parser.add_argument("--update", action="store_true", help="atualiza o yt-dlp e sai")
    return parser


def print_header():
    console.print(
        Panel.fit(
            "[bold cyan]Downloader Perfeito[/bold cyan]\n"
            "[dim]Vídeos, áudios, playlists e canais[/dim]",
            border_style="cyan",
        )
    )


def show_history():
    entries = load_history()
    if not entries:
        console.print("[dim]Nenhum download no histórico ainda.[/dim]")
        return
    table = Table(title="Últimos downloads", box=None)
    table.add_column("Quando", style="dim")
    table.add_column("Título", style="bold")
    table.add_column("Pasta")
    for entry in entries[:20]:
        when = (entry.get("timestamp") or "").replace("T", " ")
        table.add_row(when, entry.get("title", ""), entry.get("destination", ""))
    console.print(table)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print_header()

    if args.update:
        with console.status("[bold green]Atualizando o yt-dlp...[/bold green]"):
            ok, message = update_engine()
        console.print(f"[{'green' if ok else 'red'}]{message}[/]")
        return 0 if ok else 1

    if args.history:
        show_history()
        return 0

    settings = load_settings()
    if args.cookies:
        settings["cookies_browser"] = args.cookies.capitalize()
    output_dir = args.output or Path(settings.get("output_dir") or DEFAULT_DOWNLOAD_DIR)
    downloader = RichDownloader(output_dir, settings)
    downloader.forced_items = args.items
    downloader.show_runtime_status()
    if args.output:
        save_settings(output_dir=str(output_dir))

    if args.urls:
        success = True
        for url in args.urls:
            if not downloader.download(url):
                success = False
        return 0 if success else 1

    while True:
        url = Prompt.ask("\n[bold yellow]Cole a URL[/bold yellow]").strip()
        if url:
            downloader.download(url)
        if not Confirm.ask("Baixar outro conteúdo?", default=False):
            break
    console.print("[dim]Até a próxima![/dim]")
    return 0


if __name__ == "__main__":
    if os.name == "nt":
        os.environ.setdefault("PYTHONUTF8", "1")
    sys.exit(main())
