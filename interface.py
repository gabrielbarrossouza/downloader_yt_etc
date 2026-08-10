from __future__ import annotations

import os
import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import yt_dlp

from downloader_core import (
    AUDIO_FORMATS,
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_RESOLUTIONS,
    VIDEO_FORMATS,
    DownloadCancelled,
    add_history_entry,
    available_resolutions,
    build_ydl_options,
    clear_history,
    collection_size,
    is_collection,
    js_runtime_options,
    load_history,
    load_settings,
    readable_error,
    runtime_status,
    sanitize_filename,
    save_settings,
    split_urls,
    validate_url,
)


THEMES = {
    "dark": {
        "bg": "#101522",
        "card": "#192235",
        "accent": "#ff4d6d",
        "accent_hover": "#d93f5b",
        "fg": "#f5f7fb",
        "muted": "#9aa6ba",
        "entry": "#222e45",
        "entry_hover": "#2c3a55",
        "green": "#35c78a",
        "danger": "#ff6b6b",
    },
    "light": {
        "bg": "#eef0f7",
        "card": "#ffffff",
        "accent": "#e0335a",
        "accent_hover": "#c22a4c",
        "fg": "#1c2333",
        "muted": "#6b7385",
        "entry": "#eef0f7",
        "entry_hover": "#e2e5f0",
        "green": "#1f9d67",
        "danger": "#d92c2c",
    },
}

RAW_COLOR_OPTIONS = ("bg", "fg", "activebackground", "activeforeground", "insertbackground", "disabledforeground")
RAW_WIDGET_CLASSES = {"Frame", "Label", "Button", "Entry", "Text"}


class DownloaderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Downloader Perfeito")
        self.root.geometry("840x700")
        self.root.minsize(760, 640)

        self.runtimes = runtime_status()
        self.settings = load_settings()
        self.theme_name = self.settings.get("theme") if self.settings.get("theme") in THEMES else "dark"
        self.colors = THEMES[self.theme_name]

        self.video_info: dict | None = None
        self.fetched_url = ""
        self.queued_count = 1
        self.is_collection = False
        self.total_videos = 0
        self.downloaded_count = 0
        self.completed_ids: set[str] = set()
        self.busy: str | None = None
        self.last_output_dir = Path(self.settings.get("output_dir") or DEFAULT_DOWNLOAD_DIR)
        self.queue_total = 0
        self.queue_done = 0
        self.queue_errors: list[tuple[str, str]] = []
        self.cancel_event = threading.Event()
        self.events: queue.Queue[tuple] = queue.Queue()
        self.closed = False
        self._history_entries: list[dict] = []

        self.root.configure(bg=self.colors["bg"])
        self._build_styles()
        self._build_widgets()
        self._set_idle_state()
        self._prev_colors = {value: role for role, value in self.colors.items()}

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_events)
        self.url_text.focus_set()

    # ------------------------------------------------------------------ #
    # Estilo e tema
    # ------------------------------------------------------------------ #
    def _build_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        c = self.colors

        style.configure("App.TFrame", background=c["bg"])
        style.configure("Card.TFrame", background=c["card"])
        style.configure("App.TCheckbutton", background=c["card"], foreground=c["fg"], font=("Segoe UI", 10))
        style.map("App.TCheckbutton", background=[("active", c["card"])])
        style.configure(
            "App.Horizontal.TProgressbar",
            troughcolor=c["entry"],
            background=c["accent"],
            lightcolor=c["accent"],
            darkcolor=c["accent"],
            thickness=9,
        )
        style.configure(
            "App.TCombobox",
            fieldbackground=c["entry"],
            background=c["entry"],
            foreground=c["fg"],
            arrowcolor=c["fg"],
            padding=5,
        )
        style.map(
            "App.TCombobox",
            fieldbackground=[("readonly", c["entry"])],
            foreground=[("readonly", c["fg"])],
            selectbackground=[("readonly", c["entry"])],
            selectforeground=[("readonly", c["fg"])],
        )
        style.configure("App.TNotebook", background=c["bg"], borderwidth=0)
        style.configure(
            "App.TNotebook.Tab",
            background=c["card"],
            foreground=c["muted"],
            padding=(18, 9),
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
        )
        style.map(
            "App.TNotebook.Tab",
            background=[("selected", c["bg"])],
            foreground=[("selected", c["accent"])],
        )
        style.configure(
            "App.Treeview",
            background=c["card"],
            fieldbackground=c["card"],
            foreground=c["fg"],
            bordercolor=c["entry"],
            borderwidth=0,
            rowheight=26,
            font=("Segoe UI", 9),
        )
        style.map("App.Treeview", background=[("selected", c["accent"])], foreground=[("selected", "white")])
        style.configure(
            "App.Treeview.Heading",
            background=c["entry"],
            foreground=c["fg"],
            font=("Segoe UI", 9, "bold"),
            relief="flat",
        )
        style.map("App.Treeview.Heading", background=[("active", c["entry_hover"])])

    def _repaint(self, widget=None):
        if widget is None:
            widget = self.root
            self.root.configure(bg=self.colors["bg"])
        for child in widget.winfo_children():
            if child.winfo_class() in RAW_WIDGET_CLASSES:
                for option in RAW_COLOR_OPTIONS:
                    try:
                        current = child.cget(option)
                    except tk.TclError:
                        continue
                    role = self._prev_colors.get(current)
                    if role:
                        try:
                            child.config(**{option: self.colors[role]})
                        except tk.TclError:
                            pass
            self._repaint(child)

    def _toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.colors = THEMES[self.theme_name]
        save_settings(theme=self.theme_name)
        self._build_styles()
        self._repaint()
        self._prev_colors = {value: role for role, value in self.colors.items()}
        self.btn_theme.config(text="☀  Tema claro" if self.theme_name == "dark" else "🌙  Tema escuro")

    # ------------------------------------------------------------------ #
    # Widgets auxiliares
    # ------------------------------------------------------------------ #
    def _button(self, parent, text, command, *, primary=False, width=None):
        c = self.colors
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            width=width,
            bg=c["accent"] if primary else c["entry"],
            fg="white" if primary else c["fg"],
            activebackground=c["accent_hover"] if primary else c["entry_hover"],
            activeforeground="white",
            disabledforeground=c["muted"],
            relief="flat",
            cursor="hand2",
            font=("Segoe UI", 10, "bold" if primary else "normal"),
            padx=12,
            pady=7,
            bd=0,
            highlightthickness=0,
        )
        btn._primary = primary

        def on_enter(_event):
            if str(btn["state"]) != "disabled":
                btn.config(bg=self.colors["accent_hover"] if btn._primary else self.colors["entry_hover"])

        def on_leave(_event):
            if str(btn["state"]) != "disabled":
                btn.config(bg=self.colors["accent"] if btn._primary else self.colors["entry"])

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        return btn

    # ------------------------------------------------------------------ #
    # Construção da interface
    # ------------------------------------------------------------------ #
    def _build_widgets(self):
        c = self.colors
        header = tk.Frame(self.root, bg=c["card"], padx=28, pady=16)
        header.pack(fill=tk.X)
        title_box = tk.Frame(header, bg=c["card"])
        title_box.pack(side=tk.LEFT)
        tk.Label(
            title_box,
            text="Downloader Perfeito",
            font=("Segoe UI", 19, "bold"),
            fg=c["fg"],
            bg=c["card"],
        ).pack(anchor=tk.W)
        tk.Label(
            title_box,
            text="Vídeos, áudios, playlists e canais em poucos cliques",
            font=("Segoe UI", 10),
            fg=c["muted"],
            bg=c["card"],
        ).pack(anchor=tk.W, pady=(2, 0))

        self.btn_theme = self._button(
            header,
            "☀  Tema claro" if self.theme_name == "dark" else "🌙  Tema escuro",
            self._toggle_theme,
        )
        self.btn_theme.pack(side=tk.RIGHT, anchor=tk.CENTER)

        self.notebook = ttk.Notebook(self.root, style="App.TNotebook")
        self.notebook.pack(fill=tk.BOTH, expand=True)

        download_tab = tk.Frame(self.notebook, bg=c["bg"])
        history_tab = tk.Frame(self.notebook, bg=c["bg"])
        self.notebook.add(download_tab, text="Baixar")
        self.notebook.add(history_tab, text="Histórico")

        self._build_download_tab(download_tab)
        self._build_history_tab(history_tab)

        ffmpeg_text = "FFmpeg pronto" if self.runtimes["ffmpeg"] else "FFmpeg não encontrado"
        node_text = "Node.js pronto" if self.runtimes["node"] else "Node.js opcional não encontrado"
        self.lbl_runtime = tk.Label(
            self.root,
            text=f"{ffmpeg_text}  •  {node_text}",
            font=("Segoe UI", 8),
            fg=c["muted"] if self.runtimes["ffmpeg"] else c["danger"],
            bg=c["bg"],
            anchor=tk.W,
            padx=28,
            pady=8,
        )
        self.lbl_runtime.pack(fill=tk.X)

    def _build_download_tab(self, parent):
        c = self.colors
        body = tk.Frame(parent, bg=c["bg"], padx=28, pady=18)
        body.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            body,
            text="Link(s) do conteúdo — um por linha para baixar vários de uma vez",
            font=("Segoe UI", 10, "bold"),
            fg=c["fg"],
            bg=c["bg"],
        ).pack(anchor=tk.W)

        text_frame = tk.Frame(body, bg=c["bg"])
        text_frame.pack(fill=tk.X, pady=(6, 8))
        self.url_text = tk.Text(
            text_frame,
            height=3,
            wrap=tk.WORD,
            bg=c["entry"],
            fg=c["fg"],
            insertbackground=c["fg"],
            relief="flat",
            font=("Segoe UI", 10),
            padx=9,
            pady=7,
        )
        self.url_text.pack(fill=tk.X)

        url_buttons = tk.Frame(body, bg=c["bg"])
        url_buttons.pack(fill=tk.X, pady=(0, 14))
        self.btn_paste = self._button(url_buttons, "Colar", self._paste_url)
        self.btn_paste.pack(side=tk.LEFT, padx=(0, 7))
        self.btn_clear = self._button(url_buttons, "Limpar", self._clear_urls)
        self.btn_clear.pack(side=tk.LEFT, padx=(0, 7))
        self.btn_fetch = self._button(url_buttons, "Analisar", self.fetch_info_thread, primary=True)
        self.btn_fetch.pack(side=tk.LEFT)

        self.info_card = tk.Frame(body, bg=c["card"], padx=18, pady=14)
        self.info_card.pack(fill=tk.X)
        self.lbl_title = tk.Label(
            self.info_card,
            text="Cole um ou mais links para começar",
            font=("Segoe UI", 11, "bold"),
            fg=c["fg"],
            bg=c["card"],
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=700,
        )
        self.lbl_title.pack(fill=tk.X)
        self.lbl_count = tk.Label(
            self.info_card,
            text="",
            font=("Segoe UI", 9),
            fg=c["accent"],
            bg=c["card"],
            anchor=tk.W,
        )
        self.lbl_count.pack(fill=tk.X, pady=(3, 9))

        options = tk.Frame(self.info_card, bg=c["card"])
        options.pack(fill=tk.X)
        options.columnconfigure(1, weight=1)
        options.columnconfigure(3, weight=1)

        def option_label(text, row, column):
            tk.Label(
                options,
                text=text,
                font=("Segoe UI", 9),
                fg=c["muted"],
                bg=c["card"],
            ).grid(row=row, column=column, sticky=tk.W, padx=(0, 8), pady=5)

        option_label("Qualidade", 0, 0)
        self.res_var = tk.StringVar()
        self.combo_res = ttk.Combobox(
            options,
            textvariable=self.res_var,
            state="disabled",
            style="App.TCombobox",
            width=19,
        )
        self.combo_res.grid(row=0, column=1, sticky=tk.EW, padx=(0, 18), pady=5)
        self.combo_res.bind("<<ComboboxSelected>>", self._on_res_change)

        option_label("Formato", 0, 2)
        self.fmt_var = tk.StringVar()
        self.combo_fmt = ttk.Combobox(
            options,
            textvariable=self.fmt_var,
            state="disabled",
            style="App.TCombobox",
            width=13,
        )
        self.combo_fmt.grid(row=0, column=3, sticky=tk.EW, pady=5)

        option_label("Salvar em", 1, 0)
        self.dir_var = tk.StringVar(value=str(self.last_output_dir))
        self.dir_entry = tk.Entry(
            options,
            textvariable=self.dir_var,
            bg=c["entry"],
            fg=c["fg"],
            insertbackground=c["fg"],
            relief="flat",
            font=("Segoe UI", 9),
            bd=6,
        )
        self.dir_entry.grid(row=1, column=1, columnspan=2, sticky=tk.EW, padx=(0, 8), pady=5)
        self.btn_browse = self._button(options, "Escolher...", self.browse_dir)
        self.btn_browse.grid(row=1, column=3, sticky=tk.EW, pady=5)

        self.skip_var = tk.BooleanVar(value=bool(self.settings.get("skip_existing", True)))
        self.chk_skip = ttk.Checkbutton(
            self.info_card,
            text="Ignorar itens que já foram baixados",
            variable=self.skip_var,
            style="App.TCheckbutton",
        )

        status_frame = tk.Frame(body, bg=c["bg"], pady=14)
        status_frame.pack(fill=tk.X)
        self.lbl_status = tk.Label(
            status_frame,
            text="Aguardando um link",
            font=("Segoe UI", 9),
            fg=c["muted"],
            bg=c["bg"],
            anchor=tk.W,
            justify=tk.LEFT,
        )
        self.lbl_status.pack(fill=tk.X, pady=(0, 5))
        self.progress = ttk.Progressbar(
            status_frame,
            mode="determinate",
            style="App.Horizontal.TProgressbar",
        )
        self.progress.pack(fill=tk.X)
        self.lbl_overall = tk.Label(
            status_frame,
            text="",
            font=("Segoe UI", 8),
            fg=c["muted"],
            bg=c["bg"],
            anchor=tk.W,
        )
        self.lbl_overall.pack(fill=tk.X, pady=(5, 0))

        actions = tk.Frame(body, bg=c["bg"])
        actions.pack(fill=tk.X)
        self.btn_download = self._button(actions, "BAIXAR AGORA", self.download_thread, primary=True)
        self.btn_download.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_cancel = self._button(actions, "Cancelar", self.cancel_download)
        self.btn_cancel.pack(side=tk.LEFT, padx=(8, 0))
        self.btn_open = self._button(actions, "Abrir pasta", self.open_output_dir)
        self.btn_open.pack(side=tk.LEFT, padx=(8, 0))

    def _build_history_tab(self, parent):
        c = self.colors
        container = tk.Frame(parent, bg=c["bg"], padx=28, pady=18)
        container.pack(fill=tk.BOTH, expand=True)

        header_row = tk.Frame(container, bg=c["bg"])
        header_row.pack(fill=tk.X, pady=(0, 10))
        tk.Label(
            header_row,
            text="Downloads concluídos",
            font=("Segoe UI", 12, "bold"),
            fg=c["fg"],
            bg=c["bg"],
        ).pack(side=tk.LEFT)
        self.btn_history_clear = self._button(header_row, "Limpar histórico", self._on_clear_history)
        self.btn_history_clear.pack(side=tk.RIGHT)
        self.btn_history_open = self._button(header_row, "Abrir pasta", self._on_open_history_selection)
        self.btn_history_open.pack(side=tk.RIGHT, padx=(0, 8))

        columns = ("title", "when", "path")
        self.history_tree = ttk.Treeview(
            container,
            columns=columns,
            show="headings",
            style="App.Treeview",
            height=14,
        )
        self.history_tree.heading("title", text="Título")
        self.history_tree.heading("when", text="Quando")
        self.history_tree.heading("path", text="Pasta")
        self.history_tree.column("title", width=320, anchor=tk.W)
        self.history_tree.column("when", width=140, anchor=tk.W)
        self.history_tree.column("path", width=260, anchor=tk.W)
        self.history_tree.pack(fill=tk.BOTH, expand=True)
        self.history_tree.bind("<Double-1>", lambda _event: self._on_open_history_selection())

        self._refresh_history()

    # ------------------------------------------------------------------ #
    # Estado dos controles
    # ------------------------------------------------------------------ #
    def _set_status(self, text: str, color: str | None = None):
        self.lbl_status.config(text=text, fg=color or self.colors["muted"])

    def _set_idle_state(self):
        self.busy = None
        for widget in (self.btn_fetch, self.btn_paste, self.btn_clear, self.url_text, self.dir_entry, self.btn_browse):
            widget.config(state=tk.NORMAL)
        has_info = self.video_info is not None
        self.combo_res.config(state="readonly" if has_info else "disabled")
        self.combo_fmt.config(state="readonly" if has_info else "disabled")
        self.btn_download.config(state=tk.NORMAL if has_info else tk.DISABLED)
        self.btn_cancel.config(state=tk.DISABLED)
        self.btn_open.config(state=tk.NORMAL)

    def _set_busy_state(self, operation: str):
        self.busy = operation
        for widget in (
            self.btn_fetch,
            self.btn_paste,
            self.btn_clear,
            self.url_text,
            self.dir_entry,
            self.btn_browse,
            self.combo_res,
            self.combo_fmt,
            self.btn_download,
        ):
            widget.config(state=tk.DISABLED)
        self.btn_cancel.config(state=tk.NORMAL if operation == "download" else tk.DISABLED)

    # ------------------------------------------------------------------ #
    # Ações da fila de links
    # ------------------------------------------------------------------ #
    def _get_queue_urls(self, show_errors: bool = True) -> list[str]:
        raw = self.url_text.get("1.0", tk.END)
        candidates = split_urls(raw)
        valid: list[str] = []
        invalid: list[str] = []
        for candidate in candidates:
            try:
                valid.append(validate_url(candidate))
            except ValueError:
                invalid.append(candidate)
        if invalid and show_errors:
            preview = "\n".join(invalid[:5])
            if len(invalid) > 5:
                preview += "\n..."
            messagebox.showwarning(
                "Links ignorados",
                f"{len(invalid)} link(s) inválido(s) foram ignorados:\n{preview}",
            )
        return valid

    def _paste_url(self):
        try:
            value = self.root.clipboard_get().strip()
        except tk.TclError:
            messagebox.showinfo("Área de transferência", "Não há texto para colar.")
            return
        if not value:
            return
        current = self.url_text.get("1.0", tk.END).strip()
        combined = f"{current}\n{value}" if current else value
        self.url_text.delete("1.0", tk.END)
        self.url_text.insert("1.0", combined)

    def _clear_urls(self):
        self.url_text.delete("1.0", tk.END)
        self.url_text.focus_set()

    def browse_dir(self):
        selected = filedialog.askdirectory(initialdir=self.dir_var.get() or str(DEFAULT_DOWNLOAD_DIR))
        if selected:
            self.dir_var.set(selected)

    def _open_folder(self, path):
        folder = Path(path).expanduser()
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(folder))
            elif os.name == "posix":
                command = "open" if os.uname().sysname == "Darwin" else "xdg-open"
                subprocess.Popen([command, str(folder)])
        except Exception as error:
            messagebox.showerror("Abrir pasta", readable_error(error))

    def open_output_dir(self):
        self._open_folder(self.last_output_dir if self.last_output_dir else self.dir_var.get())

    def _on_res_change(self, _event=None):
        values = AUDIO_FORMATS if self.res_var.get() == "Só o áudio" else VIDEO_FORMATS
        self.combo_fmt["values"] = values
        preferred = self.settings.get("format")
        if preferred in values:
            self.fmt_var.set(preferred)
        else:
            self.combo_fmt.current(0)

    # ------------------------------------------------------------------ #
    # Histórico
    # ------------------------------------------------------------------ #
    def _refresh_history(self):
        if not hasattr(self, "history_tree"):
            return
        self.history_tree.delete(*self.history_tree.get_children())
        self._history_entries = load_history()
        for index, entry in enumerate(self._history_entries):
            when = (entry.get("timestamp") or "").replace("T", " ")
            self.history_tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(entry.get("title", ""), when, entry.get("destination", "")),
            )

    def _on_open_history_selection(self):
        selection = self.history_tree.selection()
        if not selection:
            messagebox.showinfo("Histórico", "Selecione um item da lista.")
            return
        entry = self._history_entries[int(selection[0])]
        self._open_folder(entry.get("destination", ""))

    def _on_clear_history(self):
        if not self._history_entries:
            return
        if messagebox.askyesno("Limpar histórico", "Remover todos os itens do histórico de downloads?"):
            clear_history()
            self._refresh_history()

    # ------------------------------------------------------------------ #
    # Análise do link
    # ------------------------------------------------------------------ #
    def fetch_info_thread(self):
        if self.busy:
            return
        urls = self._get_queue_urls()
        if not urls:
            messagebox.showwarning("Link inválido", "Cole ao menos um link válido (um por linha).")
            self.url_text.focus_set()
            return

        self.video_info = None
        self.fetched_url = urls[0]
        self.queued_count = len(urls)
        self.lbl_title.config(text="Analisando conteúdo...")
        self.lbl_count.config(text="")
        self.chk_skip.pack_forget()
        self.progress.config(mode="indeterminate")
        self.progress.start(12)
        self._set_status("Coletando título, formatos e itens...", self.colors["accent"])
        self._set_busy_state("fetch")
        threading.Thread(target=self._fetch_worker, args=(self.fetched_url,), daemon=True).start()

    def _fetch_worker(self, url: str):
        options = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
        }
        options.update(js_runtime_options(self.runtimes["node"]))
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
            self.events.put(("info_ok", info))
        except Exception as error:
            self.events.put(("info_error", readable_error(error)))

    def _show_info(self, info: dict):
        self.progress.stop()
        self.progress.config(mode="determinate", value=0)
        self.video_info = info
        title = info.get("title") or "Conteúdo sem título"
        self.lbl_title.config(text=title)
        self.is_collection = is_collection(info)
        self.total_videos = collection_size(info) if self.is_collection else 1
        extra = f" • {self.queued_count} links na fila" if self.queued_count > 1 else ""

        if self.is_collection:
            count = f"{self.total_videos} itens encontrados" if self.total_videos else "Playlist ou canal"
            choices = list(DEFAULT_RESOLUTIONS)
            self.lbl_count.config(text=count + extra)
            self.chk_skip.pack(anchor=tk.W, pady=(9, 0))
        else:
            choices = available_resolutions(info)
            self.lbl_count.config(text="Vídeo único" + extra)

        self.combo_res["values"] = choices
        preferred_res = self.settings.get("resolution")
        if preferred_res in choices:
            self.res_var.set(preferred_res)
        else:
            self.combo_res.current(0)
        self._on_res_change()
        self._set_status("Tudo pronto. Escolha a qualidade e o formato.", self.colors["green"])
        self._set_idle_state()

    # ------------------------------------------------------------------ #
    # Download
    # ------------------------------------------------------------------ #
    def download_thread(self):
        if self.busy or not self.video_info:
            return
        if not self.runtimes["ffmpeg"]:
            messagebox.showerror(
                "FFmpeg necessário",
                "O FFmpeg não foi encontrado no PATH. Instale-o para converter áudio e unir vídeo com áudio.",
            )
            return

        urls = self._get_queue_urls()
        if not urls:
            messagebox.showwarning("Link inválido", "Cole ao menos um link válido.")
            return

        base_dir_text = self.dir_var.get().strip()
        if not base_dir_text:
            messagebox.showwarning("Pasta inválida", "Escolha uma pasta de destino.")
            return
        base_dir = Path(base_dir_text).expanduser()
        try:
            base_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            messagebox.showerror("Pasta inválida", readable_error(error))
            return

        self.last_output_dir = base_dir
        self.cancel_event.clear()
        self.queue_total = len(urls)
        self.queue_done = 0
        self.queue_errors = []
        self.progress.config(mode="determinate", value=0)
        self.lbl_overall.config(text="")
        self._set_status("Preparando fila de downloads...", self.colors["accent"])
        self._set_busy_state("download")

        resolution = self.res_var.get()
        output_format = self.fmt_var.get()
        skip_existing = bool(self.skip_var.get())
        self.settings.update(
            output_dir=str(base_dir),
            resolution=resolution,
            format=output_format,
            skip_existing=skip_existing,
        )
        save_settings(
            output_dir=str(base_dir),
            resolution=resolution,
            format=output_format,
            skip_existing=skip_existing,
        )
        threading.Thread(
            target=self._download_worker,
            args=(urls, resolution, output_format, base_dir, skip_existing),
            daemon=True,
        ).start()

    def _download_worker(
        self,
        urls: list[str],
        resolution: str,
        output_format: str,
        base_dir: Path,
        skip_existing: bool,
    ):
        for index, url in enumerate(urls, start=1):
            if self.cancel_event.is_set():
                break
            self.events.put(("queue_item_start", index, len(urls)))

            fetch_options = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": "in_playlist",
            }
            fetch_options.update(js_runtime_options(self.runtimes["node"]))
            try:
                with yt_dlp.YoutubeDL(fetch_options) as ydl:
                    info = ydl.extract_info(url, download=False)
            except Exception as error:
                self.events.put(("link_error", url, readable_error(error)))
                continue

            collection = is_collection(info)
            title = info.get("title") or "downloads"
            if collection:
                out_dir = base_dir / sanitize_filename(title)
                template = str(out_dir / "%(playlist_index)03d - %(title)s [%(id)s].%(ext)s")
                archive = str(out_dir / ".download_archive.txt") if skip_existing else None
            else:
                out_dir = base_dir
                template = str(out_dir / "%(title)s [%(id)s].%(ext)s")
                archive = None

            try:
                out_dir.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                self.events.put(("link_error", url, readable_error(error)))
                continue

            self.is_collection = collection
            self.total_videos = collection_size(info) if collection else 1
            self.downloaded_count = 0
            self.completed_ids.clear()

            options = build_ydl_options(
                resolution,
                output_format,
                template,
                progress_hook=self._progress_hook,
                archive_file=archive,
                node_path=self.runtimes["node"],
            )
            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    ydl.download([url])
            except Exception as error:
                if self.cancel_event.is_set() or isinstance(error, DownloadCancelled):
                    self.events.put(("cancelled",))
                    return
                self.events.put(("link_error", url, readable_error(error)))
                continue

            self.last_output_dir = out_dir
            add_history_entry(title, url, out_dir)
            self.events.put(("link_done",))

        if self.cancel_event.is_set():
            self.events.put(("cancelled",))
        else:
            self.events.put(("queue_finished",))

    def _progress_hook(self, data: dict):
        if self.cancel_event.is_set():
            raise DownloadCancelled("Download cancelado pelo usuário.")
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            downloaded = data.get("downloaded_bytes") or 0
            percentage = downloaded / total * 100 if total else 0
            filename = Path(data.get("filename") or "arquivo").name
            if len(filename) > 58:
                filename = filename[:55] + "..."
            speed = (data.get("_speed_str") or "—").strip()
            eta = (data.get("_eta_str") or "—").strip()
            self.events.put(("progress", percentage, speed, eta, filename))
        elif status == "finished":
            info = data.get("info_dict") or {}
            media_id = str(info.get("id") or info.get("webpage_url") or data.get("filename"))
            if media_id not in self.completed_ids:
                self.completed_ids.add(media_id)
                self.events.put(("item_done",))

    def cancel_download(self):
        if self.busy != "download" or self.cancel_event.is_set():
            return
        self.cancel_event.set()
        self.btn_cancel.config(state=tk.DISABLED)
        self._set_status("Cancelando com segurança...", self.colors["danger"])

    # ------------------------------------------------------------------ #
    # Loop de eventos
    # ------------------------------------------------------------------ #
    def _poll_events(self):
        if self.closed:
            return
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "info_ok":
                    self._show_info(event[1])
                elif kind == "info_error":
                    self.progress.stop()
                    self.progress.config(mode="determinate", value=0)
                    self.lbl_title.config(text="Não foi possível analisar o link")
                    self._set_status("Falha ao coletar informações.", self.colors["danger"])
                    self._set_idle_state()
                    messagebox.showerror("Erro ao analisar", event[1])
                elif kind == "queue_item_start":
                    _, index, total = event
                    self.progress["value"] = 0
                    if total > 1:
                        self.lbl_overall.config(text=f"Link {index}/{total}")
                elif kind == "progress":
                    _, percentage, speed, eta, filename = event
                    self.progress["value"] = percentage
                    prefix = ""
                    if self.is_collection and self.total_videos:
                        prefix = f"Item {min(self.downloaded_count + 1, self.total_videos)}/{self.total_videos} • "
                    self._set_status(
                        f"{prefix}{filename} — {percentage:.1f}% • {speed} • restante {eta}",
                        self.colors["accent"],
                    )
                elif kind == "item_done":
                    self.downloaded_count += 1
                    self.progress["value"] = 0
                elif kind == "link_error":
                    _, url, message = event
                    self.queue_errors.append((url, message))
                    self._set_status("Falha em um link. Continuando a fila...", self.colors["danger"])
                elif kind == "link_done":
                    self.queue_done += 1
                    if self.queue_total > 1:
                        self.lbl_overall.config(text=f"Concluídos: {self.queue_done}/{self.queue_total}")
                    self._refresh_history()
                elif kind == "queue_finished":
                    self.progress["value"] = 100
                    summary = f"{self.queue_done}/{self.queue_total} concluído(s)"
                    if self.queue_errors:
                        summary += f" • {len(self.queue_errors)} com erro"
                    self.lbl_overall.config(text=summary)
                    self._set_idle_state()
                    if self.queue_errors:
                        details = "\n".join(f"- {url}: {msg}" for url, msg in self.queue_errors[:6])
                        self._set_status("Fila concluída com pendências.", self.colors["danger"])
                        messagebox.showwarning("Concluído com pendências", f"{summary}\n\n{details}")
                    else:
                        self._set_status("Download concluído com sucesso!", self.colors["green"])
                        messagebox.showinfo("Concluído", f"Arquivos salvos em:\n{self.last_output_dir}")
                elif kind == "cancelled":
                    self.progress["value"] = 0
                    self._set_status("Download cancelado. Arquivos parciais podem ser retomados depois.")
                    self._set_idle_state()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _on_close(self):
        if self.busy == "download":
            close = messagebox.askyesno(
                "Download em andamento",
                "Cancelar o download e fechar o aplicativo?",
            )
            if not close:
                return
            self.cancel_event.set()
        save_settings(
            output_dir=self.dir_var.get().strip() or str(self.last_output_dir),
            skip_existing=bool(self.skip_var.get()),
            theme=self.theme_name,
        )
        self.closed = True
        self.root.destroy()


def main():
    root = tk.Tk()
    DownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
