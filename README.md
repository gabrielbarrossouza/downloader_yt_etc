# Downloader Perfeito

Aplicativo em Python para baixar vídeos, áudios, playlists e canais usando o
`yt-dlp`. Ele oferece uma interface gráfica em Tkinter e uma interface de
terminal com Rich e Questionary.

Use o aplicativo apenas para conteúdo que você tem autorização para baixar e
respeite os termos do site de origem.

## Principais recursos

- Qualidades reais disponíveis para vídeos individuais.
- Download de playlists e canais em uma pasta organizada, com escolha de
  quais itens baixar (ex.: `1-10`, `3,5,9`).
- Fila de múltiplos links: cole vários URLs (um por linha) e baixe todos de
  uma vez, na GUI ou pelo terminal.
- Conversão de áudio para MP3, M4A, WAV ou FLAC, com qualidade selecionável
  (128 a 320 kbps ou "Melhor").
- Saída de vídeo em MP4, MKV ou WebM.
- Legendas: baixa e, quando o formato permite (MP4/MKV), embute no vídeo.
- Metadados (título, autor, capítulos) e miniatura como capa gravados no
  arquivo (capa embutida em MP3/M4A/FLAC e MKV).
- Cookies do navegador (Firefox, Chrome, Edge, Brave, Opera, Vivaldi) para
  conteúdo que exige login ou confirmação de idade.
- Downloads mais rápidos e resistentes: fragmentos em paralelo, várias
  tentativas automáticas e pausa entre requisições para evitar bloqueios.
- Limite opcional de velocidade em MB/s.
- Progresso, velocidade, tempo restante, fase de conversão do FFmpeg e
  retomada de arquivos parciais.
- Ignora automaticamente itens já baixados (arquivo de controle por
  playlist/canal e também para vídeos avulsos).
- Histórico de downloads concluídos com o caminho do arquivo: aba dedicada
  na GUI (abrir arquivo, abrir pasta, copiar link, baixar de novo, remover,
  ordenar por coluna) e comando `--history` no terminal.
- Preferências (pasta, qualidade, formato, tema, legendas, cookies e mais)
  são lembradas entre uma execução e outra.
- Tema claro/escuro alternável na interface gráfica, com janela nítida em
  telas de alta resolução e ícone próprio.
- Cancelamento seguro (inclusive durante a conversão) e botão para abrir a
  pasta de destino.
- Detecção de FFmpeg e Node.js e botão para atualizar o yt-dlp pela própria
  interface (aba **Ajustes**).

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

Outras opções de terminal:

```powershell
python downloader.py --update                       # atualiza o yt-dlp e sai
python downloader.py URL --cookies firefox           # usa cookies do navegador
python downloader.py URL_DA_PLAYLIST --items 1-10    # baixa só parte da coleção
```

Os arquivos vão por padrão para a última pasta usada (ou para `downloads`,
localizada ao lado dos scripts, na primeira execução), independentemente do
diretório usado para iniciar o programa.

## Estrutura

- `interface.py`: interface gráfica (abas Baixar / Histórico / Ajustes,
  tema claro/escuro).
- `downloader.py`: interface de terminal.
- `downloader_core.py`: validações, preferências, histórico, tradução de
  erros e configuração compartilhada do yt-dlp.
- `icon.ico` / `icon.png`: ícone da janela.
- `tests/`: testes das regras que não dependem de acesso à internet.
- `baixar.bat`: iniciador para Windows.
- `settings.json` / `history.json` / `downloader.log`: gerados
  automaticamente ao lado dos scripts para preferências, histórico e
  registro local de erros (não versionados).

## Testes

```powershell
python -m unittest discover -s tests -v
```

## Solução de problemas

- **FFmpeg não encontrado:** instale-o, adicione a pasta do executável ao
  `PATH` e reabra o aplicativo.
- **Falha em um site específico:** atualize o motor pelo botão
  "Atualizar yt-dlp" na aba **Ajustes** (ou `python downloader.py --update`).
- **"O site exige login" / restrição de idade:** escolha o navegador em que
  você está logado no campo **Cookies** (aba Ajustes na GUI, `--cookies` no
  terminal).
- **Download interrompido:** inicie novamente com o mesmo link e destino; o
  arquivo parcial será retomado quando o site permitir.
- **Erros recentes:** veja `downloader.log`, gerado ao lado dos scripts.
