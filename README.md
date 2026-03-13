# Downloader Perfeito (Alta Eficiência)

Um aplicativo em Python simples e poderoso para baixar vídeos e áudios do YouTube (e muitos outros sites suportados pelo yt-dlp). Este projeto oferece duas opções de uso: uma **Interface Gráfica (GUI)** amigável construída com Tkinter e uma **Interface de Linha de Comando (CLI)** elegante feita com Rich e Questionary.

## 🚀 Funcionalidades

- **Duas abordagens**:
  - `interface.py`: Interface visual para quem busca praticidade.
  - `downloader.py`: Terminal interativo e esteticamente agradável para "power users".
- **Múltiplas resoluções**: Baixe vídeos na resolução que preferir, inclusive na "melhor qualidade" disponível (o sistema junta os melhores fluxos de vídeo e áudio).
- **Extração de Áudio**: Baixe apenas o áudio do vídeo, escolhendo imediatamente formatos como `.mp3`, `.m4a`, `.wav` ou `.flac`.
- **Informações em Tempo Real**: Barra de progresso, percentual, velocidade de download e tempo restante (ETA).
- **Integração com Node.js**: Usa Node.js automaticamente (se instalado) via yt-dlp para burlar restrições complexas do YouTube.

## 📋 Pré-requisitos

Certifique-se de que seu sistema possui:

- [Python 3.8+](https://www.python.org/downloads/)
- [FFmpeg](https://ffmpeg.org/download.html) (Crucial. É ele que permite ao `yt-dlp` mesclar áudio e vídeo em altas resoluções ou converter para *.mp3*). Certifique-se de adicioná-lo ao `PATH` do Windows.
- Opcional mas recomendado: [Node.js](https://nodejs.org/) instalado no sistema operacional para ajudar com extrações mais eficientes em alguns sites.

## 🔧 Instalação

1. Clone o repositório para o seu computador:
   ```bash
   git clone https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
   cd SEU_REPOSITORIO
   ```

2. Crie e ative um ambiente virtual (recomendado boas práticas):
   ```bash
   python -m venv .venv
   # Ativando no Windows:
   .venv\Scripts\activate
   ```

3. Instale as dependências do projeto:
   ```bash
   pip install -r requirements.txt
   ```

## 💻 Como Usar

### Pela Interface Gráfica
Basta executar o atalho `.bat` ou rodar o script no terminal:

```bash
python interface.py
```
> *(Dê um clique duplo no `baixar.bat` se estiver no Windows! Ele atualizará o motor do yt-dlp e iniciará a interface sozinho).*

### Pela Linha de Comando (CLI)
Através do terminal, você terá um passo a passo agradável e interativo:

```bash
python downloader.py
```
> *(Ou você pode puxá-lo direto colando o link: `python downloader.py https://link-do-video...`)*

As opções de formato, arquivo e destino serão perguntadas com menus amigáveis graças à biblioteca `questionary`. Arquivos baixados por padrão vão para a pasta `downloads`.

## 📁 Estrutura do Código

- `downloader.py` - Script CLI de alta fidelidade visual.
- `interface.py` - Ferramenta de janelas.
- `requirements.txt` - Depedências (`yt-dlp`, `rich`, `questionary` etc.).
- `baixar.bat` - Executável de facilitação no Windows.
