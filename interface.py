import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import yt_dlp
import threading
import os
import shutil

class DownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Downloader de Alta Eficiência")
        self.root.geometry("600x450")
        self.root.resizable(False, False)
        
        # Configurar estilo
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Caminho do Node.js para yt_dlp
        self.node_path = shutil.which('node')
        self.js_runtimes_opts = {}
        if self.node_path:
            self.js_runtimes_opts = {'js_runtimes': {'node': {'args': [self.node_path]}}}
            
        self.video_info = None
        
        self.create_widgets()
        
    def create_widgets(self):
        # Frame principal
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Título
        lbl_header = tk.Label(main_frame, text="Youtube Downloader", font=("Helvetica", 18, "bold"), fg="#e74c3c")
        lbl_header.pack(pady=(0, 20))

        # --- Frame da URL ---
        url_frame = ttk.Frame(main_frame)
        url_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(url_frame, text="URL do Vídeo/Canal:", font=("Helvetica", 10)).pack(anchor=tk.W, pady=(0, 5))
        
        url_input_frame = ttk.Frame(url_frame)
        url_input_frame.pack(fill=tk.X)
        
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(url_input_frame, textvariable=self.url_var, font=("Helvetica", 10))
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        self.btn_fetch = ttk.Button(url_input_frame, text="Buscar Video", command=self.fetch_info_thread)
        self.btn_fetch.pack(side=tk.LEFT)
        
        # --- Frame de Informações e Opções ---
        self.info_frame = ttk.LabelFrame(main_frame, text="Informações e Opções", padding=15)
        self.info_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        self.lbl_title = tk.Label(self.info_frame, text="Título: N/A", font=("Helvetica", 10), justify=tk.LEFT, wraplength=500)
        self.lbl_title.pack(anchor=tk.W, pady=(0, 15))
        
        # Grid para as opções
        opts_frame = ttk.Frame(self.info_frame)
        opts_frame.pack(fill=tk.X)
        
        # Resolução
        ttk.Label(opts_frame, text="Resolução/Tipo:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.res_var = tk.StringVar()
        self.combo_res = ttk.Combobox(opts_frame, textvariable=self.res_var, state="disabled", width=20)
        self.combo_res.grid(row=0, column=1, padx=10, pady=5, sticky=tk.W)
        self.combo_res.bind("<<ComboboxSelected>>", self.update_formats)
        
        # Formato
        ttk.Label(opts_frame, text="Formato:").grid(row=0, column=2, sticky=tk.W, padx=(15, 0), pady=5)
        self.fmt_var = tk.StringVar()
        self.combo_fmt = ttk.Combobox(opts_frame, textvariable=self.fmt_var, state="disabled", width=15)
        self.combo_fmt.grid(row=0, column=3, padx=10, pady=5, sticky=tk.W)

        # Pasta de Saída
        ttk.Label(opts_frame, text="Salvar em:").grid(row=1, column=0, sticky=tk.W, pady=15)
        self.dir_var = tk.StringVar(value=os.path.join(os.getcwd(), "downloads"))
        self.dir_entry = ttk.Entry(opts_frame, textvariable=self.dir_var, width=22)
        self.dir_entry.grid(row=1, column=1, padx=10, pady=15, sticky=tk.W)
        self.btn_dir = ttk.Button(opts_frame, text="Procurar...", command=self.browse_dir)
        self.btn_dir.grid(row=1, column=2, columnspan=2, padx=10, pady=15, sticky=tk.W)
        
        # --- Frame de Download e Status ---
        dl_frame = ttk.Frame(main_frame)
        dl_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.lbl_status = tk.Label(dl_frame, text="Aguardando URL...", font=("Helvetica", 9), fg="#7f8c8d")
        self.lbl_status.pack(side=tk.TOP, anchor=tk.W, pady=(0, 5))
        
        self.progress = ttk.Progressbar(dl_frame, mode='determinate')
        self.progress.pack(fill=tk.X, pady=(0, 10))
        
        self.btn_download = tk.Button(dl_frame, text="BAIXAR AGORA", font=("Helvetica", 11, "bold"), 
                                      bg="#3498db", fg="white", relief=tk.FLAT, 
                                      command=self.download_thread, state=tk.DISABLED,
                                      activebackground="#2980b9", activeforeground="white")
        self.btn_download.pack(fill=tk.X, ipady=5)

    def browse_dir(self):
        directory = filedialog.askdirectory(initialdir=self.dir_var.get())
        if directory:
            self.dir_var.set(directory)

    def disable_ui(self):
        self.btn_fetch.config(state=tk.DISABLED)
        self.btn_download.config(state=tk.DISABLED, bg="#bdc3c7")
        self.url_entry.config(state=tk.DISABLED)
        self.combo_res.config(state=tk.DISABLED)
        self.combo_fmt.config(state=tk.DISABLED)
        self.btn_dir.config(state=tk.DISABLED)
        self.dir_entry.config(state=tk.DISABLED)
        
    def enable_ui(self):
        self.btn_fetch.config(state=tk.NORMAL)
        self.url_entry.config(state=tk.NORMAL)
        self.btn_dir.config(state=tk.NORMAL)
        self.dir_entry.config(state=tk.NORMAL)
        if self.video_info:
            self.combo_res.config(state="readonly")
            self.combo_fmt.config(state="readonly")
            self.btn_download.config(state=tk.NORMAL, bg="#3498db")
            
    def fetch_info_thread(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Aviso", "Por favor, insira uma URL válida.")
            return
            
        self.disable_ui()
        self.lbl_status.config(text="Coletando informações do vídeo...", fg="#2980b9")
        self.progress.config(mode='indeterminate')
        self.progress.start()
        
        threading.Thread(target=self.fetch_info, args=(url,), daemon=True).start()
        
    def fetch_info(self, url):
        opts = {'quiet': True, 'no_warnings': True}
        opts.update(self.js_runtimes_opts)
        
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                self.root.after(0, self.on_info_fetched, info)
        except Exception as e:
            self.root.after(0, self.on_info_error, str(e))
            
    def on_info_fetched(self, info):
        self.progress.stop()
        self.progress.config(mode='determinate', value=0)
        self.video_info = info
        
        title = info.get('title', 'Desconhecido')
        self.lbl_title.config(text=f"Título: {title}")
        
        # Obter resoluções
        if info.get('_type') == 'playlist':
            res_choices = ["Melhor qualidade"]
        else:
            formats = info.get('formats', [])
            resolutions = set()
            for f in formats:
                if f.get('vcodec') != 'none' and f.get('height'):
                    resolutions.add(f['height'])
            
            sorted_res = sorted(list(resolutions), reverse=True)
            res_choices = [f"{r}p" for r in sorted_res] + ["Melhor qualidade", "Só o áudio"]
            
        self.combo_res['values'] = res_choices
        if res_choices:
            self.combo_res.current(0)
            self.update_formats()
            
        self.lbl_status.config(text="Pronto para baixar.", fg="#27ae60")
        self.enable_ui()
        
    def on_info_error(self, error_msg):
        self.progress.stop()
        self.progress.config(mode='determinate', value=0)
        self.lbl_status.config(text="Erro ao obter informações.", fg="#c0392b")
        messagebox.showerror("Erro", f"Não foi possível obter informações do vídeo:\n{error_msg}")
        self.enable_ui()
        
    def update_formats(self, event=None):
        res = self.res_var.get()
        if res == "Só o áudio":
            self.combo_fmt['values'] = ["mp3", "m4a", "wav", "flac"]
            self.combo_fmt.current(0)
        else:
            self.combo_fmt['values'] = ["mp4", "mkv", "webm"]
            self.combo_fmt.current(0)
            
    def my_hook(self, d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                percent = (downloaded / total) * 100
                speed = d.get('_speed_str', 'N/A')
                eta = d.get('_eta_str', 'N/A')
                if isinstance(speed, str): speed = speed.split('m')[-1] if '\x1b[' in speed else speed
                if isinstance(eta, str): eta = eta.split('m')[-1] if '\x1b[' in eta else eta
                
                self.root.after(0, self.update_progress, percent, speed, eta)
        elif d['status'] == 'finished':
            self.root.after(0, self.update_progress, 100, "0", "0")
            
    def update_progress(self, percent, speed, eta):
        self.progress['value'] = percent
        # Clean up any potential ansi color codes from yt-dlp
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        speed = ansi_escape.sub('', speed)
        eta = ansi_escape.sub('', eta)
        
        self.lbl_status.config(text=f"Baixando... {percent:.1f}% | Vel: {speed} | ETA: {eta}")
        
    def download_thread(self):
        if not self.video_info:
            return
            
        self.disable_ui()
        self.lbl_status.config(text="Iniciando download...", fg="#2980b9")
        self.progress['value'] = 0
        
        res_choice = self.res_var.get()
        format_choice = self.fmt_var.get()
        out_dir = self.dir_var.get()
        
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível criar o diretório de destino:\n{e}")
            self.enable_ui()
            return
            
        url = self.video_info.get('webpage_url', self.url_var.get())
        threading.Thread(target=self.download, args=(url, res_choice, format_choice, out_dir), daemon=True).start()
        
    def download(self, url, res_choice, format_choice, out_dir):
        out_tmpl = os.path.join(out_dir, '%(title)s.%(ext)s')
        ydl_opts = {
            'outtmpl': out_tmpl,
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [self.my_hook]
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
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
            ydl_opts['merge_output_format'] = format_choice
        else:
            height = res_choice.replace('p', '')
            ydl_opts['format'] = f'bestvideo[height<={height}]+bestaudio/best[height<={height}]'
            ydl_opts['merge_output_format'] = format_choice
            
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            self.root.after(0, self.on_download_complete)
        except Exception as e:
            self.root.after(0, self.on_download_error, str(e))
            
    def on_download_complete(self):
        self.lbl_status.config(text="Download concluído com sucesso!", fg="#27ae60")
        messagebox.showinfo("Sucesso", "O download foi concluído com sucesso!")
        self.enable_ui()
        
    def on_download_error(self, error_msg):
        self.lbl_status.config(text="Erro no download.", fg="#c0392b")
        messagebox.showerror("Erro", f"Ocorreu um erro durante o download:\n{error_msg}")
        self.enable_ui()

if __name__ == "__main__":
    root = tk.Tk()
    app = DownloaderApp(root)
    root.mainloop()
