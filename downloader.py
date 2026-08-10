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
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_RESOLUTIONS,
    VIDEO_FORMATS,
    add_history_entry,
    available_resolutions,
    build_ydl_options,
    collection_size,
    is_collection,
    js_runtime_options,
    load_history,
    load_settings,
    readable_error,
    runtime_status,
    sanitize_filename,
    save_settings,
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
    def __init__(self, output_dir: Path = DEFAULT_DOWNLOAD_DIR):
        self.output_dir = output_dir.expanduser().resolve()
        self.runtimes = runtime_status()
        self.tasks: dict[str, int] = {}
        self.completed_ids: set[str] = set()
        self.video_index = 0
        self.total_videos = 0
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
        console.print(f"[dim]FFmpeg:[/dim] {ffmpeg}  [dim]Node.js:[/dim] {node}")

    def get_info(self, url: str) -> dict | None:
        with console.status("[bold green]Analisando o link...[/bold green]"):
            options = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": "in_playlist",
            }
            options.update(js_runtime_options(self.runtimes["node"]))
            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    return ydl.extract_info(url, download=False)
            except Exception as error:
                console.print(f"[red]Não foi possível analisar o link: {readable_error(error)}[/red]")
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

    def _choose_options(self, choices: list[str]) -> tuple[str, str] | None:
        resolution = self.select_resolution(choices)
        if not resolution:
            return None
        output_format = self.select_format(resolution)
        if not output_format:
            return None
        return resolution, output_format

    def download_collection(self, url: str, info: dict) -> bool:
        title = info.get("title") or "Coleção"
        self.total_videos = collection_size(info)
        table = Table(box=None, show_header=False, padding=(0, 1))
        table.add_row("[bold cyan]Nome[/bold cyan]", title)
        count = str(self.total_videos) if self.total_videos else "será calculado durante o download"
        table.add_row("[bold cyan]Itens[/bold cyan]", count)
        console.print(Panel(table, title="[bold]Playlist / canal[/bold]", border_style="cyan"))

        selection = self._choose_options(list(DEFAULT_RESOLUTIONS))
        if not selection or not self._require_ffmpeg():
            return False
        resolution, output_format = selection

        destination = self.output_dir / sanitize_filename(title)
        destination.mkdir(parents=True, exist_ok=True)
        skip_existing = Confirm.ask("Ignorar itens já baixados anteriormente?", default=True)
        archive = str(destination / ".download_archive.txt") if skip_existing else None
        template = str(destination / "%(playlist_index)03d - %(title)s [%(id)s].%(ext)s")
        return self._run_download(url, resolution, output_format, template, archive, destination, title)

    def download_single(self, url: str, info: dict) -> bool:
        title = info.get("title") or "Vídeo"
        console.print(f"[green]Encontrado:[/green] {title}")
        selection = self._choose_options(available_resolutions(info))
        if not selection or not self._require_ffmpeg():
            return False
        resolution, output_format = selection

        self.total_videos = 1
        self.output_dir.mkdir(parents=True, exist_ok=True)
        template = str(self.output_dir / "%(title)s [%(id)s].%(ext)s")
        return self._run_download(url, resolution, output_format, template, None, self.output_dir, title)

    def _run_download(
        self,
        url: str,
        resolution: str,
        output_format: str,
        template: str,
        archive: str | None,
        destination: Path,
        title: str,
    ) -> bool:
        self.video_index = 0
        self.tasks.clear()
        self.completed_ids.clear()
        options = build_ydl_options(
            resolution,
            output_format,
            template,
            progress_hook=self.progress_hook,
            archive_file=archive,
            node_path=self.runtimes["node"],
            logger=MyLogger(),
        )
        console.print(f"\n[bold green]Baixando para:[/bold green] [white]{destination}[/white]\n")
        try:
            with self.progress:
                with yt_dlp.YoutubeDL(options) as ydl:
                    result = ydl.download([url])
            if result:
                console.print("[red]O yt-dlp encerrou com falha.[/red]")
                return False
        except KeyboardInterrupt:
            console.print("\n[yellow]Download interrompido. Ele poderá ser retomado depois.[/yellow]")
            return False
        except Exception as error:
            console.print(f"\n[red]Falha no download: {readable_error(error)}[/red]")
            return False

        console.print(f"\n[bold green]✓ Concluído:[/bold green] [white]{destination}[/white]")
        add_history_entry(title, url, destination)
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
            media_id = str(info.get("id") or info.get("webpage_url") or key)
            if media_id not in self.completed_ids:
                self.completed_ids.add(media_id)
                self.video_index += 1
                console.print(f"[green]✓[/green] {Path(data.get('filename') or 'arquivo').name}")


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
        "--history",
        action="store_true",
        help="mostra os downloads mais recentes e sai",
    )
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

    if args.history:
        show_history()
        return 0

    settings = load_settings()
    output_dir = args.output or Path(settings.get("output_dir") or DEFAULT_DOWNLOAD_DIR)
    downloader = RichDownloader(output_dir)
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
