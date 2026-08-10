# Downloader Perfeito

Aplicativo em Python para baixar vídeos, áudios, playlists e canais usando o
`yt-dlp`. Ele oferece uma interface gráfica em Tkinter e uma interface de
terminal com Rich e Questionary.

Use o aplicativo apenas para conteúdo que você tem autorização para baixar e
respeite os termos do site de origem.

## Principais recursos

- Qualidades reais disponíveis para vídeos individuais.
- Download de playlists e canais em uma pasta organizada.
- Fila de múltiplos links: cole vários URLs (um por linha) e baixe todos de
  uma vez, na GUI ou pelo terminal.
- Conversão de áudio para MP3, M4A, WAV ou FLAC.
- Saída de vídeo em MP4, MKV ou WebM.
- Progresso, velocidade, tempo restante e retomada de arquivos parciais.
- Ignora automaticamente itens já baixados de uma coleção (arquivo de
  controle por playlist/canal).
- Histórico de downloads concluídos, com aba dedicada na GUI e comando
  `--history` no terminal.
- Preferências (pasta, qualidade, formato, tema) são lembradas entre uma
  execução e outra.
- Tema claro/escuro alternável na interface gráfica.
- Cancelamento seguro e botão para abrir a pasta de destino na interface gráfica.
- Detecção de FFmpeg e Node.js.

## Requisitos

- Python 3.10 ou mais recente.
- [FFmpeg](https://ffmpeg.org/download.html) disponível no `PATH`. Ele é usado
  para unir vídeo e áudio e para conversões.
- Node.js é opcional, mas ajuda o `yt-dlp` em alguns extratores.

## Instalação

No PowerShell, dentro da pasta do projeto:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Uso

No Windows, dê dois cliques em `baixar.bat`. O iniciador usa o ambiente virtual
quando ele existe e só instala dependências se estiverem ausentes.

Para abrir a interface diretamente:

```powershell
python interface.py
```

Para usar o terminal interativo:

```powershell
python downloader.py
```

Também é possível informar um ou mais links e a pasta de destino diretamente:

```powershell
python downloader.py "https://exemplo.com/video" --output "D:\Videos"
python downloader.py "https://exemplo.com/video1" "https://exemplo.com/video2"
```

Para ver os downloads mais recentes:

```powershell
python downloader.py --history
```

Os arquivos vão por padrão para a última pasta usada (ou para `downloads`,
localizada ao lado dos scripts, na primeira execução), independentemente do
diretório usado para iniciar o programa.

## Estrutura

- `interface.py`: interface gráfica (abas Baixar/Histórico, tema claro/escuro).
- `downloader.py`: interface de terminal.
- `downloader_core.py`: validações, preferências, histórico e configuração
  compartilhada do yt-dlp.
- `tests/`: testes das regras que não dependem de acesso à internet.
- `baixar.bat`: iniciador para Windows.
- `settings.json` / `history.json`: gerados automaticamente ao lado dos
  scripts para guardar preferências e histórico locais (não versionados).

## Testes

```powershell
python -m unittest discover -s tests -v
```

## Solução de problemas

- **FFmpeg não encontrado:** instale-o, adicione a pasta do executável ao
  `PATH` e reabra o aplicativo.
- **Falha em um site específico:** atualize o motor com
  `python -m pip install --upgrade yt-dlp`.
- **Download interrompido:** inicie novamente com o mesmo link e destino; o
  arquivo parcial será retomado quando o site permitir.
