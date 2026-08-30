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
    APP_DIR,
    AUDIO_FORMATS,
    AUDIO_QUALITIES,
    COOKIE_BROWSERS,
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_RESOLUTIONS,
    VIDEO_FORMATS,
    DownloadCancelled,
    add_history_entry,
    append_log,
    available_resolutions,
    build_output_template,
    build_ydl_options,
    clear_history,
    collection_size,
    engine_version,
    explain_error,
    is_collection,
    js_runtime_options,
    load_history,
    load_settings,
    parse_subtitle_langs,
    postprocessor_phase,
    remove_history_entry,
    runtime_status,
    sanitize_filename,
    save_settings,
    split_urls,
    update_engine,
    validate_url,
)


# ---------------------------------------------------------------------------- #
# Identidade visual — "signal deck": console escuro, âmbar para o que está
# acontecendo agora, teal para o que terminou. Todo hex é único dentro do tema
# para que a repintura por papel nunca confunda duas cores.
# ---------------------------------------------------------------------------- #
THEMES = {
    "dark": {
        "bg": "#0E1017",
        "panel": "#171A24",
        "groove": "#20242F",
        "fg": "#E8EAF0",
        "muted": "#7C8398",
        "entry": "#252B3D",
        "entry_hover": "#2F3648",
        "field_border": "#3A4256",
        "active": "#FFB454",
        "active_hover": "#F0A63C",
        "on_active": "#0E1017",
        "ok": "#46D8A8",
        "danger": "#FF6B6B",
    },
    "light": {
        "bg": "#EEF0F5",
        "panel": "#FFFFFF",
        "groove": "#E2E5EE",
        "fg": "#1B1E27",
        "muted": "#5C6373",
        "entry": "#EEF1F7",
        "entry_hover": "#E3E7F1",
        "field_border": "#C4CAD8",
        "active": "#C97A16",
        "active_hover": "#B36B12",
        "on_active": "#FFFFFF",
        "ok": "#12936A",
        "danger": "#CC2E2E",
    },
}

FONT_DISPLAY = ("Segoe UI Semibold", 20)
FONT_H = ("Segoe UI Semibold", 12)
FONT_BODY = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_TINY = ("Segoe UI", 8)
FONT_MONO = ("Consolas", 9)


def enable_windows_polish() -> None:
    """Deixa a janela nítida em telas HiDPI e com ícone próprio na barra."""
    if os.name != "nt":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "downloaderperfeito.app"
            )
        except Exception:
            pass
    except Exception:
        pass


class DownloaderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Downloader Perfeito")
        self.root.geometry("880x820")
        self.root.minsize(720, 560)
        self._apply_icon()

        self.runtimes = runtime_status()
        self.settings = load_settings()
        self.theme_name = self.settings.get("theme") if self.settings.get("theme") in THEMES else "dark"
        self.colors = THEMES[self.theme_name]

        self.video_info: dict | None = None
        self.fetched_url = ""
        self.queued_count = 1
        self.audio_selected = False
        self.collection_selected = False
        # Estado só do thread principal, alimentado pelos eventos da fila.
        self.ui_is_collection = False
        self.ui_total_videos = 0
        self.ui_done_in_link = 0
        self.completed_ids: set[str] = set()
        self._cookies_choice = "Nenhum"
        self.busy: str | None = None
        self.last_output_dir = Path(self.settings.get("output_dir") or DEFAULT_DOWNLOAD_DIR)
        self.last_filepath: str | None = None
        self.queue_total = 0
        self.queue_done = 0
        self.queue_errors: list[tuple[str, str]] = []
        self.cancel_event = threading.Event()
        self.events: queue.Queue[tuple] = queue.Queue()
        self.closed = False
        self._themed: list[tuple[tk.Widget, dict]] = []
        self._history_entries: list[dict] = []
        self._history_sort = ("timestamp", True)

        self.root.configure(bg=self.colors["bg"])
        self._build_styles()
        self._build_widgets()
        self._set_idle_state()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_events)
        self.url_text.focus_set()

    def _apply_icon(self):
        for loader in (
            lambda: self.root.iconbitmap(str(APP_DIR / "icon.ico")),
            lambda: self._set_iconphoto(),
        ):
            try:
                loader()
                return
            except Exception:
                continue

    def _set_iconphoto(self):
        self._icon_img = tk.PhotoImage(file=str(APP_DIR / "icon.png"))
        self.root.iconphoto(True, self._icon_img)

    # ------------------------------------------------------------------ #
    # Tema
    # ------------------------------------------------------------------ #
    def _track(self, widget: tk.Widget, **roles: str) -> tk.Widget:
        """Marca quais opções de cor do widget seguem quais papéis do tema."""
        self._themed.append((widget, roles))
        return widget

    def _build_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        c = self.colors

        style.configure("App.TFrame", background=c["bg"])
        style.configure("Card.TFrame", background=c["panel"])
        style.configure(
            "App.TCheckbutton",
            background=c["panel"],
            foreground=c["fg"],
            font=FONT_SMALL,
        )
        style.map(
            "App.TCheckbutton",
            background=[("active", c["panel"])],
            foreground=[("disabled", c["muted"])],
        )
        style.configure(
            "App.Horizontal.TProgressbar",
            troughcolor=c["groove"],
            background=c["active"],
            lightcolor=c["active"],
            darkcolor=c["active"],
            bordercolor=c["groove"],
            thickness=10,
        )
        style.configure(
            "Done.Horizontal.TProgressbar",
            troughcolor=c["groove"],
            background=c["ok"],
            lightcolor=c["ok"],
            darkcolor=c["ok"],
            bordercolor=c["groove"],
            thickness=10,
        )
        for name in ("App.TCombobox", "Card.TCombobox"):
            bg = c["entry"]
            style.configure(
                name,
                fieldbackground=bg,
                background=bg,
                foreground=c["fg"],
                arrowcolor=c["fg"],
                bordercolor=c["field_border"],
                lightcolor=c["field_border"],
                darkcolor=c["field_border"],
                padding=5,
            )
            style.map(
                name,
                fieldbackground=[("readonly", bg), ("disabled", c["groove"])],
                foreground=[("readonly", c["fg"]), ("disabled", c["muted"])],
                selectbackground=[("readonly", bg)],
                selectforeground=[("readonly", c["fg"])],
            )
        style.configure("App.TNotebook", background=c["bg"], borderwidth=0)
        style.configure(
            "App.TNotebook.Tab",
            background=c["panel"],
            foreground=c["muted"],
            padding=(20, 9),
            font=("Segoe UI Semibold", 10),
            borderwidth=0,
        )
        style.map(
            "App.TNotebook.Tab",
            background=[("selected", c["bg"])],
            foreground=[("selected", c["active"])],
        )
        style.configure(
            "App.Treeview",
            background=c["panel"],
            fieldbackground=c["panel"],
            foreground=c["fg"],
            bordercolor=c["groove"],
            borderwidth=0,
            rowheight=27,
            font=FONT_SMALL,
        )
        style.map(
            "App.Treeview",
            background=[("selected", c["active"])],
            foreground=[("selected", c["on_active"])],
        )
        style.configure(
            "App.Treeview.Heading",
            background=c["groove"],
            foreground=c["fg"],
            font=("Segoe UI Semibold", 9),
            relief="flat",
        )
        style.map("App.Treeview.Heading", background=[("active", c["entry_hover"])])

    def _repaint(self):
        self.root.configure(bg=self.colors["bg"])
        for widget, roles in self._themed:
            if not str(widget):
                continue
            for option, role in roles.items():
                try:
                    widget.config(**{option: self.colors[role]})
                except tk.TclError:
                    pass
        for btn in getattr(self, "_buttons", []):
            self._style_button(btn)
        if hasattr(self, "history_tree"):
            self._tag_history_rows()

    def _toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.colors = THEMES[self.theme_name]
        save_settings(theme=self.theme_name)
        self._build_styles()
        self._repaint()
        self.btn_theme.config(text=self._theme_button_label())

    def _theme_button_label(self) -> str:
        return "  Tema claro" if self.theme_name == "dark" else "  Tema escuro"

    # ------------------------------------------------------------------ #
    # Botões
    # ------------------------------------------------------------------ #
    def _style_button(self, btn: tk.Button):
        c = self.colors
        disabled = str(btn["state"]) == "disabled"
        if disabled:
            btn.config(bg=c["groove"], fg=c["muted"])
        elif btn._primary:
            btn.config(bg=c["active"], fg=c["on_active"])
        else:
            btn.config(bg=c["entry"], fg=c["fg"])

    def _button(self, parent, text, command, *, primary=False, width=None):
        c = self.colors
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            width=width,
            activebackground=c["active_hover"] if primary else c["entry_hover"],
            activeforeground=c["on_active"] if primary else c["fg"],
            relief="flat",
            cursor="hand2",
            font=("Segoe UI Semibold", 10) if primary else FONT_BODY,
            padx=13,
            pady=7,
            bd=0,
            highlightthickness=0,
        )
        btn._primary = primary
        self._style_button(btn)

        def on_enter(_event):
            if str(btn["state"]) != "disabled":
                btn.config(bg=self.colors["active_hover"] if primary else self.colors["entry_hover"])

        def on_leave(_event):
            if str(btn["state"]) != "disabled":
                self._style_button(btn)

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        self._buttons = getattr(self, "_buttons", [])
        self._buttons.append(btn)
        return btn

    def _entry(self, parent, textvariable, *, width=None) -> tk.Entry:
        c = self.colors
        entry = tk.Entry(
            parent,
            textvariable=textvariable,
            width=width,
            bg=c["entry"],
            fg=c["fg"],
            insertbackground=c["fg"],
            relief="flat",
            font=FONT_SMALL,
            bd=6,
            highlightthickness=1,
            highlightbackground=c["field_border"],
            highlightcolor=c["active"],
        )
        self._track(
            entry,
            bg="entry",
            fg="fg",
            insertbackground="fg",
            highlightbackground="field_border",
            highlightcolor="active",
        )
        return entry

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #
    def _section_label(self, parent, step: str, text: str):
        c = self.colors
        row = tk.Frame(parent, bg=c["bg"])
        self._track(row, bg="bg")
        badge = tk.Label(
            row,
            text=step,
            font=("Consolas", 10, "bold"),
            fg=c["on_active"],
            bg=c["active"],
            padx=7,
            pady=1,
        )
        self._track(badge, bg="active", fg="on_active")
        badge.pack(side=tk.LEFT)
        title = tk.Label(row, text=text, font=FONT_H, fg=c["fg"], bg=c["bg"])
        self._track(title, bg="bg", fg="fg")
        title.pack(side=tk.LEFT, padx=(9, 0))
        return row

    def _build_widgets(self):
        c = self.colors

        header = tk.Frame(self.root, bg=c["panel"], padx=28, pady=16)
        self._track(header, bg="panel")
        header.pack(fill=tk.X)
        title_box = tk.Frame(header, bg=c["panel"])
        self._track(title_box, bg="panel")
        title_box.pack(side=tk.LEFT)
        lbl = tk.Label(title_box, text="Downloader Perfeito", font=FONT_DISPLAY, fg=c["fg"], bg=c["panel"])
        self._track(lbl, bg="panel", fg="fg")
        lbl.pack(anchor=tk.W)
        sub = tk.Label(
            title_box,
            text="Vídeos, áudios, playlists e canais em poucos cliques",
            font=FONT_SMALL,
            fg=c["muted"],
            bg=c["panel"],
        )
        self._track(sub, bg="panel", fg="muted")
        sub.pack(anchor=tk.W, pady=(2, 0))

        self.btn_theme = self._button(header, self._theme_button_label(), self._toggle_theme)
        self.btn_theme.pack(side=tk.RIGHT, anchor=tk.CENTER)

        self.notebook = ttk.Notebook(self.root, style="App.TNotebook")
        self.notebook.pack(fill=tk.BOTH, expand=True)

        download_tab = self._track(tk.Frame(self.notebook, bg=c["bg"]), bg="bg")
        history_tab = self._track(tk.Frame(self.notebook, bg=c["bg"]), bg="bg")
        settings_tab = self._track(tk.Frame(self.notebook, bg=c["bg"]), bg="bg")
        self.notebook.add(download_tab, text="Baixar")
        self.notebook.add(history_tab, text="Histórico")
        self.notebook.add(settings_tab, text="Ajustes")

        self._build_download_tab(download_tab)
        self._build_history_tab(history_tab)
        self._build_settings_tab(settings_tab)

    def _scrollable(self, parent) -> tk.Frame:
        """Área rolável: o conteúdo cresce à vontade sem empurrar o rodapé."""
        c = self.colors
        canvas = tk.Canvas(parent, bg=c["bg"], highlightthickness=0, bd=0)
        self._track(canvas, bg="bg")
        vbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        inner = tk.Frame(canvas, bg=c["bg"])
        self._track(inner, bg="bg")
        window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _resize(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(window, width=canvas.winfo_width())

        inner.bind("<Configure>", _resize)
        canvas.bind("<Configure>", _resize)

        def _wheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")

        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
        return inner

    def _build_download_tab(self, parent):
        c = self.colors

        # Rodapé fixo: status, progresso e ações ficam sempre visíveis.
        footer = tk.Frame(parent, bg=c["bg"], padx=28, pady=12)
        self._track(footer, bg="bg")
        footer.pack(side=tk.BOTTOM, fill=tk.X)

        self.lbl_status = tk.Label(
            footer,
            text="Aguardando um link",
            font=FONT_SMALL,
            fg=c["muted"],
            bg=c["bg"],
            anchor=tk.W,
            justify=tk.LEFT,
        )
        self._track(self.lbl_status, bg="bg")
        self.lbl_status.pack(fill=tk.X, pady=(0, 4))
        self.progress = ttk.Progressbar(footer, mode="determinate", style="App.Horizontal.TProgressbar")
        self.progress.pack(fill=tk.X)
        self.lbl_metrics = tk.Label(
            footer, text="", font=FONT_MONO, fg=c["muted"], bg=c["bg"], anchor=tk.W
        )
        self._track(self.lbl_metrics, bg="bg", fg="muted")
        self.lbl_metrics.pack(fill=tk.X, pady=(5, 10))

        actions = tk.Frame(footer, bg=c["bg"])
        self._track(actions, bg="bg")
        actions.pack(fill=tk.X)
        self.btn_download = self._button(actions, "BAIXAR AGORA", self.download_thread, primary=True)
        self.btn_download.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_cancel = self._button(actions, "Cancelar", self.cancel_download)
        self.btn_cancel.pack(side=tk.LEFT, padx=(8, 0))
        self.btn_open = self._button(actions, "Abrir pasta", self.open_output_dir)
        self.btn_open.pack(side=tk.LEFT, padx=(8, 0))

        outer = self._scrollable(parent)
        body = tk.Frame(outer, bg=c["bg"], padx=28, pady=16)
        self._track(body, bg="bg")
        body.pack(fill=tk.BOTH, expand=True)

        # 1 · LINKS -----------------------------------------------------
        self._section_label(body, " 1 ", "Cole o link — um por linha para baixar vários").pack(anchor=tk.W)

        text_frame = tk.Frame(body, bg=c["bg"])
        self._track(text_frame, bg="bg")
        text_frame.pack(fill=tk.X, pady=(8, 8))
        self.url_text = tk.Text(
            text_frame,
            height=3,
            wrap=tk.WORD,
            bg=c["entry"],
            fg=c["fg"],
            insertbackground=c["fg"],
            relief="flat",
            font=FONT_BODY,
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground=c["field_border"],
            highlightcolor=c["active"],
        )
        self._track(
            self.url_text,
            bg="entry",
            fg="fg",
            insertbackground="fg",
            highlightbackground="field_border",
            highlightcolor="active",
        )
        self.url_text.pack(fill=tk.X)

        url_buttons = tk.Frame(body, bg=c["bg"])
        self._track(url_buttons, bg="bg")
        url_buttons.pack(fill=tk.X, pady=(0, 16))
        self.btn_paste = self._button(url_buttons, "Colar", self._paste_url)
        self.btn_paste.pack(side=tk.LEFT, padx=(0, 7))
        self.btn_clear = self._button(url_buttons, "Limpar", self._clear_urls)
        self.btn_clear.pack(side=tk.LEFT, padx=(0, 7))
        self.btn_fetch = self._button(url_buttons, "Analisar", self.fetch_info_thread, primary=True)
        self.btn_fetch.pack(side=tk.LEFT)

        # 2 · CONTEÚDO -------------------------------------------------
        self._section_label(body, " 2 ", "Conteúdo").pack(anchor=tk.W, pady=(0, 6))
        self.info_card = tk.Frame(body, bg=c["panel"], padx=18, pady=14)
        self._track(self.info_card, bg="panel")
        self.info_card.pack(fill=tk.X)
        self.lbl_title = tk.Label(
            self.info_card,
            text="Cole um ou mais links e clique em Analisar",
            font=("Segoe UI Semibold", 11),
            fg=c["fg"],
            bg=c["panel"],
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=720,
        )
        self._track(self.lbl_title, bg="panel", fg="fg")
        self.lbl_title.pack(fill=tk.X)
        self.lbl_count = tk.Label(
            self.info_card, text="", font=FONT_SMALL, fg=c["active"], bg=c["panel"], anchor=tk.W
        )
        self._track(self.lbl_count, bg="panel", fg="active")
        self.lbl_count.pack(fill=tk.X, pady=(3, 0))

        # 3 · OPÇÕES -------------------------------------------------
        self._section_label(body, " 3 ", "Opções").pack(anchor=tk.W, pady=(16, 6))
        opts = tk.Frame(body, bg=c["panel"], padx=18, pady=14)
        self._track(opts, bg="panel")
        opts.pack(fill=tk.X)
        opts.columnconfigure(1, weight=1)
        opts.columnconfigure(3, weight=1)

        def opt_label(text, row, column):
            lab = tk.Label(opts, text=text, font=FONT_SMALL, fg=c["muted"], bg=c["panel"])
            self._track(lab, bg="panel", fg="muted")
            lab.grid(row=row, column=column, sticky=tk.W, padx=(0, 8), pady=6)
            return lab

        opt_label("Qualidade", 0, 0)
        self.res_var = tk.StringVar()
        self.combo_res = ttk.Combobox(
            opts, textvariable=self.res_var, state="disabled", style="Card.TCombobox", width=19
        )
        self.combo_res.grid(row=0, column=1, sticky=tk.EW, padx=(0, 18), pady=6)
        self.combo_res.bind("<<ComboboxSelected>>", self._on_res_change)

        opt_label("Formato", 0, 2)
        self.fmt_var = tk.StringVar()
        self.combo_fmt = ttk.Combobox(
            opts, textvariable=self.fmt_var, state="disabled", style="Card.TCombobox", width=13
        )
        self.combo_fmt.grid(row=0, column=3, sticky=tk.EW, pady=6)

        self.lbl_aq = opt_label("Áudio", 1, 0)
        self.aq_var = tk.StringVar(value=self.settings.get("audio_quality", "192 kbps"))
        self.combo_aq = ttk.Combobox(
            opts,
            textvariable=self.aq_var,
            state="disabled",
            style="Card.TCombobox",
            width=19,
            values=list(AUDIO_QUALITIES),
        )
        self.combo_aq.grid(row=1, column=1, sticky=tk.EW, padx=(0, 18), pady=6)

        self.lbl_items = opt_label("Itens", 1, 2)
        self.items_var = tk.StringVar()
        self.entry_items = self._entry(opts, self.items_var)
        self.entry_items.grid(row=1, column=3, sticky=tk.EW, pady=6)
        self.lbl_items.grid_remove()
        self.entry_items.grid_remove()

        opt_label("Salvar em", 2, 0)
        self.dir_var = tk.StringVar(value=str(self.last_output_dir))
        self.dir_entry = self._entry(opts, self.dir_var)
        self.dir_entry.grid(row=2, column=1, columnspan=2, sticky=tk.EW, padx=(0, 8), pady=6)
        self.btn_browse = self._button(opts, "Escolher...", self.browse_dir)
        self.btn_browse.grid(row=2, column=3, sticky=tk.EW, pady=6)

        checks = tk.Frame(opts, bg=c["panel"])
        self._track(checks, bg="panel")
        checks.grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))
        self.skip_var = tk.BooleanVar(value=bool(self.settings.get("skip_existing", True)))
        self.chk_skip = ttk.Checkbutton(
            checks, text="Ignorar itens já baixados", variable=self.skip_var, style="App.TCheckbutton"
        )
        self.chk_skip.pack(side=tk.LEFT, padx=(0, 18))
        self.subs_var = tk.BooleanVar(value=bool(self.settings.get("download_subtitles", False)))
        self.chk_subs = ttk.Checkbutton(
            checks, text="Baixar legendas", variable=self.subs_var, style="App.TCheckbutton"
        )
        self.chk_subs.pack(side=tk.LEFT)

    def _build_history_tab(self, parent):
        c = self.colors
        container = tk.Frame(parent, bg=c["bg"], padx=28, pady=18)
        self._track(container, bg="bg")
        container.pack(fill=tk.BOTH, expand=True)

        header_row = tk.Frame(container, bg=c["bg"])
        self._track(header_row, bg="bg")
        header_row.pack(fill=tk.X, pady=(0, 10))
        title = tk.Label(
            header_row, text="Downloads concluídos", font=FONT_H, fg=c["fg"], bg=c["bg"]
        )
        self._track(title, bg="bg", fg="fg")
        title.pack(side=tk.LEFT)
        self.btn_history_clear = self._button(header_row, "Limpar histórico", self._on_clear_history)
        self.btn_history_clear.pack(side=tk.RIGHT)
        hint = tk.Label(
            header_row,
            text="Clique com o botão direito para mais ações",
            font=FONT_TINY,
            fg=c["muted"],
            bg=c["bg"],
        )
        self._track(hint, bg="bg", fg="muted")
        hint.pack(side=tk.RIGHT, padx=(0, 12))

        columns = ("title", "when", "path")
        self.history_tree = ttk.Treeview(
            container, columns=columns, show="headings", style="App.Treeview", height=15
        )
        self.history_tree.heading("title", text="Título", command=lambda: self._sort_history("title"))
        self.history_tree.heading("when", text="Quando", command=lambda: self._sort_history("timestamp"))
        self.history_tree.heading("path", text="Pasta", command=lambda: self._sort_history("destination"))
        self.history_tree.column("title", width=340, anchor=tk.W)
        self.history_tree.column("when", width=150, anchor=tk.W)
        self.history_tree.column("path", width=260, anchor=tk.W)
        self.history_tree.pack(fill=tk.BOTH, expand=True)
        self.history_tree.bind("<Double-1>", lambda _e: self._history_open_file())
        self.history_tree.bind("<Button-3>", self._history_context_menu)

        self.history_menu = tk.Menu(self.root, tearoff=0)
        self.history_menu.add_command(label="Abrir arquivo", command=self._history_open_file)
        self.history_menu.add_command(label="Abrir pasta", command=self._history_open_folder)
        self.history_menu.add_command(label="Copiar link", command=self._history_copy_url)
        self.history_menu.add_command(label="Baixar de novo", command=self._history_redownload)
        self.history_menu.add_separator()
        self.history_menu.add_command(label="Remover do histórico", command=self._history_remove)

        self._refresh_history()

    def _build_settings_tab(self, parent):
        c = self.colors
        wrap = tk.Frame(parent, bg=c["bg"], padx=28, pady=18)
        self._track(wrap, bg="bg")
        wrap.pack(fill=tk.BOTH, expand=True)

        card = tk.Frame(wrap, bg=c["panel"], padx=18, pady=16)
        self._track(card, bg="panel")
        card.pack(fill=tk.X)
        card.columnconfigure(1, weight=1)

        def row_label(text, row):
            lab = tk.Label(card, text=text, font=FONT_SMALL, fg=c["muted"], bg=c["panel"])
            self._track(lab, bg="panel", fg="muted")
            lab.grid(row=row, column=0, sticky=tk.W, padx=(0, 12), pady=7)

        row_label("Cookies do navegador", 0)
        self.cookies_var = tk.StringVar(value=self.settings.get("cookies_browser", "Nenhum"))
        self.combo_cookies = ttk.Combobox(
            card,
            textvariable=self.cookies_var,
            state="readonly",
            style="Card.TCombobox",
            values=list(COOKIE_BROWSERS),
            width=20,
        )
        self.combo_cookies.grid(row=0, column=1, sticky=tk.W, pady=7)

        row_label("Idiomas das legendas", 1)
        self.langs_var = tk.StringVar(value=self.settings.get("subtitle_langs", "pt-BR, en"))
        self._entry(card, self.langs_var, width=24).grid(row=1, column=1, sticky=tk.W, pady=7)

        row_label("Limite de velocidade (MB/s)", 2)
        self.limit_var = tk.StringVar(value=self.settings.get("speed_limit_mbps", ""))
        self._entry(card, self.limit_var, width=10).grid(row=2, column=1, sticky=tk.W, pady=7)

        toggles = tk.Frame(card, bg=c["panel"])
        self._track(toggles, bg="panel")
        toggles.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(10, 0))
        self.meta_var = tk.BooleanVar(value=bool(self.settings.get("embed_metadata", True)))
        self.thumb_var = tk.BooleanVar(value=bool(self.settings.get("embed_thumbnail", True)))
        self.embed_subs_var = tk.BooleanVar(value=bool(self.settings.get("embed_subtitles", True)))
        self.include_id_var = tk.BooleanVar(value=bool(self.settings.get("include_id", True)))
        self.restrict_var = tk.BooleanVar(value=bool(self.settings.get("restrict_filenames", False)))
        for text, var in (
            ("Gravar título, autor e capítulos no arquivo", self.meta_var),
            ("Inserir a miniatura como capa", self.thumb_var),
            ("Embutir as legendas no vídeo", self.embed_subs_var),
            ("Incluir o ID no nome do arquivo", self.include_id_var),
            ("Usar nomes de arquivo simples (ASCII)", self.restrict_var),
        ):
            ttk.Checkbutton(toggles, text=text, variable=var, style="App.TCheckbutton").pack(anchor=tk.W, pady=2)

        engine_card = tk.Frame(wrap, bg=c["panel"], padx=18, pady=16)
        self._track(engine_card, bg="panel")
        engine_card.pack(fill=tk.X, pady=(16, 0))
        self.lbl_engine = tk.Label(
            engine_card,
            text=self._engine_text(),
            font=FONT_SMALL,
            fg=c["fg"],
            bg=c["panel"],
            anchor=tk.W,
            justify=tk.LEFT,
        )
        self._track(self.lbl_engine, bg="panel", fg="fg")
        self.lbl_engine.pack(side=tk.LEFT)
        self.btn_update = self._button(engine_card, "Atualizar yt-dlp", self._update_engine_thread)
        self.btn_update.pack(side=tk.RIGHT)

    def _engine_text(self) -> str:
        ffmpeg = "FFmpeg pronto" if self.runtimes["ffmpeg"] else "FFmpeg não encontrado"
        node = "Node.js pronto" if self.runtimes["node"] else "Node.js opcional ausente"
        return f"Motor yt-dlp {engine_version()}\n{ffmpeg}  •  {node}"

    # ------------------------------------------------------------------ #
    # Estado dos controles
    # ------------------------------------------------------------------ #
    def _set_status(self, text: str, color: str | None = None):
        self.lbl_status.config(text=text, fg=color or self.colors["muted"])

    def _set_metrics(self, text: str, color: str | None = None):
        self.lbl_metrics.config(text=text, fg=color or self.colors["muted"])

    def _progress_style(self, done: bool):
        self.progress.config(style="Done.Horizontal.TProgressbar" if done else "App.Horizontal.TProgressbar")

    def _set_idle_state(self):
        self.busy = None
        for widget in (self.btn_fetch, self.btn_paste, self.btn_clear, self.url_text, self.dir_entry,
                       self.btn_browse, self.entry_items):
            widget.config(state=tk.NORMAL)
        has_info = self.video_info is not None
        self.combo_res.config(state="readonly" if has_info else "disabled")
        self.combo_fmt.config(state="readonly" if has_info else "disabled")
        self.combo_aq.config(state="readonly" if has_info and self.audio_selected else "disabled")
        self.btn_download.config(state=tk.NORMAL if has_info else tk.DISABLED)
        self.btn_cancel.config(state=tk.DISABLED)
        self.btn_open.config(state=tk.NORMAL)
        for btn in (self.btn_fetch, self.btn_paste, self.btn_clear, self.btn_browse,
                    self.btn_download, self.btn_cancel, self.btn_open):
            self._style_button(btn)

    def _set_busy_state(self, operation: str):
        self.busy = operation
        for widget in (self.btn_fetch, self.btn_paste, self.btn_clear, self.url_text, self.dir_entry,
                       self.btn_browse, self.entry_items, self.combo_res, self.combo_fmt,
                       self.combo_aq, self.btn_download):
            widget.config(state=tk.DISABLED)
        self.btn_cancel.config(state=tk.NORMAL if operation == "download" else tk.DISABLED)
        for btn in (self.btn_fetch, self.btn_paste, self.btn_clear, self.btn_browse,
                    self.btn_download, self.btn_cancel):
            self._style_button(btn)

    # ------------------------------------------------------------------ #
    # Fila de links
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
                "Links ignorados", f"{len(invalid)} link(s) inválido(s) foram ignorados:\n{preview}"
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

    def _open_path(self, path: str | Path, select: bool = False):
        target = Path(path).expanduser()
        try:
            if select and target.is_file():
                if os.name == "nt":
                    subprocess.Popen(["explorer", "/select,", str(target)])
                    return
                target = target.parent
            folder = target if target.is_dir() else target.parent
            folder.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(target if target.exists() else folder))
            elif os.name == "posix":
                command = "open" if os.uname().sysname == "Darwin" else "xdg-open"
                subprocess.Popen([command, str(folder)])
        except Exception as error:
            messagebox.showerror("Abrir", explain_error(error))

    def open_output_dir(self):
        self._open_path(self.last_output_dir or self.dir_var.get())

    def _on_res_change(self, _event=None):
        self.audio_selected = self.res_var.get() == "Só o áudio"
        values = AUDIO_FORMATS if self.audio_selected else VIDEO_FORMATS
        self.combo_fmt["values"] = values
        preferred = self.settings.get("format")
        if preferred in values:
            self.fmt_var.set(preferred)
        else:
            self.combo_fmt.current(0)
        self.combo_aq.config(state="readonly" if self.audio_selected and not self.busy else "disabled")

    # ------------------------------------------------------------------ #
    # Histórico
    # ------------------------------------------------------------------ #
    def _tag_history_rows(self):
        c = self.colors
        self.history_tree.tag_configure("odd", background=c["panel"])
        self.history_tree.tag_configure("even", background=c["groove"])

    def _refresh_history(self):
        if not hasattr(self, "history_tree"):
            return
        self.history_tree.delete(*self.history_tree.get_children())
        entries = load_history()
        key, reverse = self._history_sort
        entries = sorted(entries, key=lambda e: (e.get(key) or "").lower(), reverse=reverse)
        self._history_entries = entries
        self._tag_history_rows()
        for index, entry in enumerate(entries):
            when = (entry.get("timestamp") or "").replace("T", " ")
            self.history_tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(entry.get("title", ""), when, entry.get("destination", "")),
                tags=("even" if index % 2 else "odd",),
            )

    def _sort_history(self, key: str):
        current_key, reverse = self._history_sort
        self._history_sort = (key, not reverse if key == current_key else False)
        self._refresh_history()

    def _selected_history_entry(self) -> dict | None:
        selection = self.history_tree.selection()
        if not selection:
            return None
        return self._history_entries[int(selection[0])]

    def _history_context_menu(self, event):
        row = self.history_tree.identify_row(event.y)
        if row:
            self.history_tree.selection_set(row)
            self.history_menu.tk_popup(event.x_root, event.y_root)

    def _history_open_file(self):
        entry = self._selected_history_entry()
        if not entry:
            return
        path = entry.get("filepath")
        if path and Path(path).exists():
            self._open_path(path, select=True)
        else:
            self._open_path(entry.get("destination", ""))

    def _history_open_folder(self):
        entry = self._selected_history_entry()
        if entry:
            self._open_path(entry.get("destination", ""))

    def _history_copy_url(self):
        entry = self._selected_history_entry()
        if entry and entry.get("url"):
            self.root.clipboard_clear()
            self.root.clipboard_append(entry["url"])

    def _history_redownload(self):
        entry = self._selected_history_entry()
        if entry and entry.get("url"):
            self.url_text.delete("1.0", tk.END)
            self.url_text.insert("1.0", entry["url"])
            self.notebook.select(0)
            self.url_text.focus_set()

    def _history_remove(self):
        entry = self._selected_history_entry()
        if not entry:
            return
        remove_history_entry(entry.get("url", ""), entry.get("timestamp", ""))
        self._refresh_history()

    def _on_clear_history(self):
        if not self._history_entries:
            return
        if messagebox.askyesno("Limpar histórico", "Remover todos os itens do histórico de downloads?"):
            clear_history()
            self._refresh_history()

    # ------------------------------------------------------------------ #
    # Motor yt-dlp
    # ------------------------------------------------------------------ #
    def _update_engine_thread(self):
        self.btn_update.config(state=tk.DISABLED)
        self._style_button(self.btn_update)
        self.lbl_engine.config(text="Atualizando o yt-dlp...")
        threading.Thread(target=self._update_engine_worker, daemon=True).start()

    def _update_engine_worker(self):
        ok, message = update_engine()
        self.events.put(("engine_update", ok, message))

    # ------------------------------------------------------------------ #
    # Análise
    # ------------------------------------------------------------------ #
    def _analysis_options(self, cookies: str | None = None) -> dict:
        """Opções do yt-dlp para só coletar metadados. `cookies` deve vir do
        thread principal — nunca leia variáveis Tk fora dele."""
        extra = {}
        if cookies and cookies != "Nenhum":
            extra["cookiesfrombrowser"] = (cookies.lower(),)
        return {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            **js_runtime_options(self.runtimes["node"]),
            **extra,
        }

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
        self._cookies_choice = self.cookies_var.get()
        self.lbl_title.config(text="Analisando conteúdo...")
        self.lbl_count.config(text="")
        self.progress.config(mode="indeterminate")
        self._progress_style(False)
        self.progress.start(12)
        self._set_status("Coletando título, formatos e itens...", self.colors["active"])
        self._set_metrics("")
        self._set_busy_state("fetch")
        threading.Thread(target=self._fetch_worker, args=(self.fetched_url,), daemon=True).start()

    def _fetch_worker(self, url: str):
        try:
            with yt_dlp.YoutubeDL(self._analysis_options(self._cookies_choice)) as ydl:
                info = ydl.extract_info(url, download=False)
            self.events.put(("info_ok", info))
        except Exception as error:
            append_log(f"análise falhou: {url} :: {error}")
            self.events.put(("info_error", explain_error(error)))

    def _show_info(self, info: dict):
        self.progress.stop()
        self.progress.config(mode="determinate", value=0)
        self.video_info = info
        title = info.get("title") or "Conteúdo sem título"
        self.lbl_title.config(text=title)
        self.collection_selected = is_collection(info)
        total = collection_size(info) if self.collection_selected else 1
        extra = f"  •  {self.queued_count} links na fila" if self.queued_count > 1 else ""

        if self.collection_selected:
            count = f"{total} itens encontrados" if total else "Playlist ou canal"
            choices = list(DEFAULT_RESOLUTIONS)
            self.lbl_count.config(text=count + extra)
            self.lbl_items.grid()
            self.entry_items.grid()
        else:
            choices = available_resolutions(info)
            self.lbl_count.config(text="Vídeo único" + extra)
            self.lbl_items.grid_remove()
            self.entry_items.grid_remove()

        self.combo_res["values"] = choices
        preferred_res = self.settings.get("resolution")
        if preferred_res in choices:
            self.res_var.set(preferred_res)
        else:
            self.combo_res.current(0)
        self._on_res_change()
        self._set_status("Tudo pronto. Escolha a qualidade e o formato.", self.colors["ok"])
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
            messagebox.showerror("Pasta inválida", explain_error(error))
            return

        self.last_output_dir = base_dir
        self.cancel_event.clear()
        self.queue_total = len(urls)
        self.queue_done = 0
        self.queue_errors = []
        self.progress.config(mode="determinate", value=0)
        self._progress_style(False)
        self._set_metrics("")
        self._set_status("Preparando fila de downloads...", self.colors["active"])
        self._set_busy_state("download")

        params = self._collect_download_params(base_dir)
        save_settings(**params["persist"])
        self.settings.update(params["persist"])
        threading.Thread(target=self._download_worker, args=(urls, params), daemon=True).start()

    def _collect_download_params(self, base_dir: Path) -> dict:
        resolution = self.res_var.get()
        output_format = self.fmt_var.get()
        audio_quality = self.aq_var.get()
        skip_existing = bool(self.skip_var.get())
        want_subs = bool(self.subs_var.get())
        langs = parse_subtitle_langs(self.langs_var.get()) if want_subs else None
        return {
            "resolution": resolution,
            "output_format": output_format,
            "audio_quality": audio_quality,
            "skip_existing": skip_existing,
            "subtitle_langs": langs,
            "embed_subtitles": bool(self.embed_subs_var.get()),
            "embed_metadata": bool(self.meta_var.get()),
            "embed_thumbnail": bool(self.thumb_var.get()),
            "cookies_browser": self.cookies_var.get(),
            "playlist_items": self.items_var.get().strip() or None,
            "include_id": bool(self.include_id_var.get()),
            "restrict_filenames": bool(self.restrict_var.get()),
            "speed_limit_mbps": self.limit_var.get().strip(),
            "base_dir": base_dir,
            "persist": {
                "output_dir": str(base_dir),
                "resolution": resolution,
                "format": output_format,
                "audio_quality": audio_quality,
                "skip_existing": skip_existing,
                "download_subtitles": want_subs,
                "subtitle_langs": self.langs_var.get(),
                "embed_subtitles": bool(self.embed_subs_var.get()),
                "embed_metadata": bool(self.meta_var.get()),
                "embed_thumbnail": bool(self.thumb_var.get()),
                "cookies_browser": self.cookies_var.get(),
                "include_id": bool(self.include_id_var.get()),
                "restrict_filenames": bool(self.restrict_var.get()),
                "speed_limit_mbps": self.limit_var.get().strip(),
            },
        }

    def _download_worker(self, urls: list[str], params: dict):
        base_dir: Path = params["base_dir"]
        for index, url in enumerate(urls, start=1):
            if self.cancel_event.is_set():
                break
            self.events.put(("queue_item_start", index, len(urls)))

            try:
                with yt_dlp.YoutubeDL(self._analysis_options(params["cookies_browser"])) as ydl:
                    info = ydl.extract_info(url, download=False)
            except Exception as error:
                append_log(f"link falhou na análise: {url} :: {error}")
                self.events.put(("link_error", url, explain_error(error)))
                continue

            collection = is_collection(info)
            title = info.get("title") or "downloads"
            total = collection_size(info) if collection else 1
            if collection:
                out_dir = base_dir / sanitize_filename(title)
                archive = str(out_dir / ".download_archive.txt") if params["skip_existing"] else None
            else:
                out_dir = base_dir
                archive = str(base_dir / ".download_archive.txt") if params["skip_existing"] else None

            try:
                out_dir.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                self.events.put(("link_error", url, explain_error(error)))
                continue

            self.events.put(("link_context", collection, total))
            self.completed_ids.clear()
            template = build_output_template(
                out_dir, collection=collection, include_id=params["include_id"]
            )
            options = build_ydl_options(
                params["resolution"],
                params["output_format"],
                template,
                progress_hook=self._progress_hook,
                postprocessor_hook=self._pp_hook,
                archive_file=archive,
                node_path=self.runtimes["node"],
                audio_quality=params["audio_quality"],
                embed_metadata=params["embed_metadata"],
                embed_thumbnail=params["embed_thumbnail"],
                subtitle_langs=params["subtitle_langs"],
                embed_subtitles=params["embed_subtitles"],
                cookies_from_browser=params["cookies_browser"],
                playlist_items=params["playlist_items"] if collection else None,
                speed_limit_mbps=params["speed_limit_mbps"],
                restrict_filenames=params["restrict_filenames"],
                tolerate_errors=collection,
            )
            self.last_filepath = None
            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    ydl.download([url])
            except Exception as error:
                if self.cancel_event.is_set() or isinstance(error, DownloadCancelled):
                    self.events.put(("cancelled",))
                    return
                append_log(f"download falhou: {url} :: {error}")
                self.events.put(("link_error", url, explain_error(error)))
                continue

            add_history_entry(title, url, out_dir, filepath=self.last_filepath)
            self.events.put(("link_done", str(out_dir)))

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
            if len(filename) > 60:
                filename = filename[:57] + "..."
            speed = (data.get("_speed_str") or "—").strip()
            eta = (data.get("_eta_str") or "—").strip()
            self.events.put(("progress", percentage, speed, eta, filename))
        elif status == "finished":
            self.last_filepath = data.get("filename") or self.last_filepath
            info = data.get("info_dict") or {}
            media_id = str(info.get("id") or info.get("webpage_url") or data.get("filename"))
            if media_id not in self.completed_ids:
                self.completed_ids.add(media_id)
                self.events.put(("item_done", media_id))

    def _pp_hook(self, data: dict):
        if self.cancel_event.is_set():
            raise DownloadCancelled("Download cancelado pelo usuário.")
        info = data.get("info_dict") or {}
        if info.get("filepath"):
            self.last_filepath = info["filepath"]
        phase = postprocessor_phase(data.get("postprocessor"))
        if phase and data.get("status") == "started":
            self.events.put(("phase", phase))

    def cancel_download(self):
        if self.busy != "download" or self.cancel_event.is_set():
            return
        self.cancel_event.set()
        self.btn_cancel.config(state=tk.DISABLED)
        self._style_button(self.btn_cancel)
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
                elif kind == "engine_update":
                    _, ok, message = event
                    self.lbl_engine.config(text=self._engine_text())
                    self.btn_update.config(state=tk.NORMAL)
                    self._style_button(self.btn_update)
                    messagebox.showinfo("Atualização" if ok else "Falha", message)
                elif kind == "queue_item_start":
                    _, index, total = event
                    self.progress["value"] = 0
                    self._progress_style(False)
                    self.ui_done_in_link = 0
                    if total > 1:
                        self._set_metrics(f"Link {index}/{total}")
                elif kind == "link_context":
                    _, collection, total = event
                    self.ui_is_collection = collection
                    self.ui_total_videos = total
                elif kind == "phase":
                    self._set_status(event[1], self.colors["active"])
                elif kind == "progress":
                    _, percentage, speed, eta, filename = event
                    self.progress["value"] = percentage
                    prefix = ""
                    if self.ui_is_collection and self.ui_total_videos:
                        current = min(self.ui_done_in_link + 1, self.ui_total_videos)
                        prefix = f"Item {current}/{self.ui_total_videos}  •  "
                    self._set_status(filename, self.colors["fg"])
                    self._set_metrics(
                        f"{prefix}{percentage:5.1f}%   {speed:>11}   restante {eta}", self.colors["active"]
                    )
                elif kind == "item_done":
                    self.ui_done_in_link += 1
                    self.progress["value"] = 0
                elif kind == "link_error":
                    _, url, message = event
                    self.queue_errors.append((url, message))
                    self._set_status("Falha em um link. Continuando a fila...", self.colors["danger"])
                elif kind == "link_done":
                    self.queue_done += 1
                    self.last_output_dir = Path(event[1])
                    if self.queue_total > 1:
                        self._set_metrics(f"Concluídos: {self.queue_done}/{self.queue_total}")
                    self._refresh_history()
                elif kind == "queue_finished":
                    self.progress["value"] = 100
                    self._progress_style(True)
                    summary = f"{self.queue_done}/{self.queue_total} concluído(s)"
                    if self.queue_errors:
                        summary += f"  •  {len(self.queue_errors)} com erro"
                    self._set_metrics(summary)
                    self._set_idle_state()
                    if self.queue_errors:
                        details = "\n".join(f"- {url}: {msg}" for url, msg in self.queue_errors[:6])
                        self._set_status("Fila concluída com pendências.", self.colors["danger"])
                        messagebox.showwarning("Concluído com pendências", f"{summary}\n\n{details}")
                    else:
                        self._set_status("Download concluído com sucesso!", self.colors["ok"])
                        messagebox.showinfo("Concluído", f"Arquivos salvos em:\n{self.last_output_dir}")
                elif kind == "cancelled":
                    self.progress["value"] = 0
                    self._progress_style(False)
                    self._set_status("Download cancelado. Arquivos parciais podem ser retomados depois.")
                    self._set_metrics("")
                    self._set_idle_state()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _on_close(self):
        if self.busy == "download":
            if not messagebox.askyesno("Download em andamento", "Cancelar o download e fechar o aplicativo?"):
                return
            self.cancel_event.set()
        save_settings(
            output_dir=self.dir_var.get().strip() or str(self.last_output_dir),
            skip_existing=bool(self.skip_var.get()),
            download_subtitles=bool(self.subs_var.get()),
            subtitle_langs=self.langs_var.get(),
            speed_limit_mbps=self.limit_var.get().strip(),
            cookies_browser=self.cookies_var.get(),
            embed_metadata=bool(self.meta_var.get()),
            embed_thumbnail=bool(self.thumb_var.get()),
            embed_subtitles=bool(self.embed_subs_var.get()),
            include_id=bool(self.include_id_var.get()),
            restrict_filenames=bool(self.restrict_var.get()),
            theme=self.theme_name,
        )
        self.closed = True
        self.root.destroy()


def main():
    enable_windows_polish()
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", root.winfo_fpixels("1i") / 72.0)
    except tk.TclError:
        pass
    DownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
