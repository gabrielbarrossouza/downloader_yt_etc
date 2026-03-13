import os
import sys
import yt_dlp
import questionary
import shutil
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
from rich.prompt import Prompt
from rich.panel import Panel

console = Console()

class MyLogger:
    def debug(self, msg):
        if msg.startswith('[debug] '):
            pass
        else:
            pass

    def info(self, msg):
        pass

    def warning(self, msg):
        console.print(f"[yellow]Warning: {msg}[/yellow]")

    def error(self, msg):
        console.print(f"[red]Error: {msg}[/red]")

class RichDownloader:
    def __init__(self):
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
            console=console
        )
        self.tasks = {}
        # Resolve 'node' path once
        self.node_path = shutil.which('node')
        self.js_runtimes_opts = {}
        if self.node_path:
            self.js_runtimes_opts = {'js_runtimes': {'node': {'args': [self.node_path]}}}
        else:
             console.print("[yellow]Warning: Node.js not found. Some downloads might fail.[/yellow]")

    def get_video_info(self, url):
        with console.status("[bold green]Coletando as informações do vídeo...[/bold green]"):
            opts = {'quiet': True, 'no_warnings': True}
            opts.update(self.js_runtimes_opts)
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    return ydl.extract_info(url, download=False)
                except Exception as e:
                    console.print(f"[red]Error fetching info: {e}[/red]")
                    return None

    def select_resolution(self, info):
        # If it's a playlist, we can't easily list all resolutions for all videos.
        if info.get('_type') == 'playlist':
            return 'best' # Default to best for playlists

        formats = info.get('formats', [])
        # Filter for video formats that have height
        resolutions = set()
        for f in formats:
            if f.get('vcodec') != 'none' and f.get('height'):
                resolutions.add(f['height'])
        
        sorted_res = sorted(list(resolutions), reverse=True)
        res_choices = [str(r) + "p" for r in sorted_res] + ["Melhor qualidade", "Só o áudio"]
        
        return questionary.select(
            "Selecione a resolução/tipo:",
            choices=res_choices
        ).ask()

    def select_format(self, mode):
        if mode == "Só o áudio":
            return questionary.select(
                "Selecione um formato de áudio:",
                choices=["mp3", "m4a", "wav", "flac"]
            ).ask()
        else:
            return questionary.select(
                "Selecione o formato:",
                choices=["mp4", "mkv", "webm"]
            ).ask()

    def download(self, url):
        info = self.get_video_info(url)
        if not info:
            return

        title = info.get('title', 'Unknown')
        console.print(f"[green]Found:[/green] {title}")

        # Interactive Selection
        res_choice = self.select_resolution(info)
        
        if res_choice is None: # User cancelled
            return

        format_choice = self.select_format(res_choice)
        
        if format_choice is None:
            return

        # Configure Options
        ydl_opts = {
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
        }
        ydl_opts.update(self.js_runtimes_opts)

        if res_choice == "Só o áudio":
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': format_choice,
                'preferredquality': '192',
            }]
        elif res_choice == "Melhor qualidade":
            ydl_opts['format'] = f'bestvideo+bestaudio/best'
            ydl_opts['merge_output_format'] = format_choice
        else:
            # Specific resolution
            height = res_choice.replace('p', '')
            ydl_opts['format'] = f'bestvideo[height<={height}]+bestaudio/best[height<={height}]'
            ydl_opts['merge_output_format'] = format_choice

        console.print(f"[bold]Baixando {title} as {format_choice}...[/bold]")

        with self.progress:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

    def progress_hook(self, d):
        if d['status'] == 'downloading':
            filename = d.get('filename', 'Unknown').split('/')[-1]
            # Truncate filename if too long
            if len(filename) > 30:
                filename = filename[:27] + "..."
                
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            
            if filename not in self.tasks:
                task_id = self.progress.add_task("download", filename=filename, total=total)
                self.tasks[filename] = task_id
            else:
                task_id = self.tasks[filename]
                self.progress.update(task_id, completed=downloaded, total=total)
                
        elif d['status'] == 'finished':
            filename = d.get('filename', 'Unknown').split('/')[-1]
            console.print(f"[green]Concluído:[/green] {filename}")

def main():
    console.print(Panel.fit("[bold cyan]Downloader de alta eficiência[/bold cyan]", border_style="cyan"))
    
    if len(sys.argv) > 1:
        url = sys.argv[1]
        console.print(f"[yellow]URL do vídeo: {url}[/yellow]")
        # Clear args so next run asks for URL if looping
        sys.argv = [sys.argv[0]]
    else:
        url = Prompt.ask("[bold yellow]Cole a URL do YouTube (Video ou Canal)[/bold yellow]")
    
    if not url:
        console.print("[red]URL inválida ou não fornecida. Fechando aplicação...[/red]")
        return

    downloader = RichDownloader()
    downloader.download(url)

if __name__ == "__main__":
    while True:
        baixar_novamente = input('Quer baixar alguma coisa? [S]Sim, [N]Não: ').upper()
        if baixar_novamente == 'S':
            os.system('cls')
            main()
        else:
            print('Saindo do programa...')
            break
