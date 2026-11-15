#!/usr/bin/env python3
# ReLink's window: what to build from, where, the language, then the build with its own output shown as it goes.
# Called by AppRun when it is given no argument; any argument goes to make_game.py as it is (the command line).
# tkinter only: the AppImage's Python carries it, and nothing else has to be installed or built.
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox

HERE = os.environ.get("RELINK_APPDIR") or os.path.dirname(os.path.abspath(__file__)) + "/../../../../.."
PY = os.path.join(HERE, "usr", "python", "bin", "python3")
MK = os.path.join(HERE, "usr", "share", "relink", "nx2", "make_game.py")

LANGUAGES = [
    ("en-US", "English (US)"), ("en-GB", "English (UK)"), ("fr", "Français"),
    ("fr-CA", "Français (Canada)"), ("de", "Deutsch"), ("it", "Italiano"),
    ("es", "Español (España)"), ("es-419", "Español (Latinoamérica)"),
    ("pt-BR", "Português (Brasil)"), ("pt-PT", "Português (Portugal)"),
    ("nl", "Nederlands"), ("pl", "Polski"), ("ru", "Русский"),
    ("ja", "日本語"), ("ko", "한국어"), ("zh-Hans", "简体中文"), ("zh-Hant", "繁體中文"),
]

BG      = "#151a21"   # the window
CARD    = "#1c232c"   # the panels
LINE    = "#2b3542"   # their edges
FG      = "#e6edf3"   # text
DIM     = "#8b98a5"   # the notes under a row
ACCENT  = "#5bb8a6"   # what to press, and what the build says
ACCENT2 = "#3f8f81"   # its shade when the mouse is on it
LOG_BG  = "#0e1318"
ERR     = "#e0755f"


def pick_font(root, wanted, fallback):
    have = {f.lower() for f in tkfont.families(root)}
    for name in wanted:
        if name.lower() in have:
            return name
    return fallback


class Window:
    def __init__(self, root):
        self.root = root
        self.proc = None
        self.q = queue.Queue()
        self.src = tk.StringVar(value="nup")
        self.nup = tk.StringVar()
        self.romfs = tk.StringVar()
        self.exefs = tk.StringVar()
        self.out = tk.StringVar()
        self.lang = tk.StringVar(value="fr")

        ui = pick_font(root, ["Inter", "Cantarell", "Noto Sans", "Liberation Sans", "DejaVu Sans"], "TkDefaultFont")
        mono = pick_font(root, ["JetBrains Mono", "Cascadia Mono", "Liberation Mono", "DejaVu Sans Mono"], "TkFixedFont")
        self.f_body = (ui, 10)
        self.f_small = (ui, 9)
        self.f_head = (ui, 17, "bold")
        self.f_sec = (ui, 9, "bold")
        self.f_mono = (mono, 9)

        root.title("ReLink — Ocarina of Time (Switch 2)")
        root.minsize(860, 700)
        root.configure(background=BG)
        self.centre(920, 740)

        st = ttk.Style(root)
        st.theme_use("clam")
        st.configure(".", background=BG, foreground=FG, font=self.f_body)
        st.configure("TFrame", background=BG)
        st.configure("Card.TFrame", background=CARD)
        st.configure("TLabel", background=BG, foreground=FG, font=self.f_body)
        st.configure("Card.TLabel", background=CARD, foreground=FG, font=self.f_body)
        st.configure("Dim.TLabel", background=CARD, foreground=DIM, font=self.f_small)
        st.configure("Sec.TLabel", background=CARD, foreground=ACCENT, font=self.f_sec)
        st.configure("Head.TLabel", background=BG, foreground=FG, font=self.f_head)
        st.configure("Status.TLabel", background=BG, foreground=DIM, font=self.f_small)
        st.configure("TRadiobutton", background=CARD, foreground=FG, font=self.f_body,
                     indicatorcolor=CARD, focuscolor=CARD)
        st.map("TRadiobutton", background=[("active", CARD)], foreground=[("disabled", DIM)])
        st.configure("TButton", background="#232d38", foreground=FG, font=self.f_body,
                     borderwidth=0, focusthickness=0, padding=(14, 7))
        st.map("TButton", background=[("active", "#2c3846"), ("disabled", "#1a212a")],
               foreground=[("disabled", "#5d6b7a")])
        st.configure("Accent.TButton", background=ACCENT, foreground="#0b1116",
                     font=(ui, 10, "bold"), borderwidth=0, padding=(20, 9))
        st.map("Accent.TButton", background=[("active", ACCENT2), ("disabled", "#2a3d3a")],
               foreground=[("disabled", "#6b807c")])
        st.configure("TCombobox", fieldbackground="#232d38", background="#232d38",
                     foreground=FG, arrowcolor=FG, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE,
                     selectbackground="#232d38", selectforeground=FG, padding=(8, 6))
        st.map("TCombobox", fieldbackground=[("readonly", "#232d38")], foreground=[("readonly", FG)])
        st.configure("Bar.Horizontal.TProgressbar", background=ACCENT, troughcolor="#0d1218",
                     bordercolor="#0d1218", lightcolor=ACCENT, darkcolor=ACCENT, thickness=8)

        # ---- header ----
        head = ttk.Frame(root)
        head.pack(fill="x", padx=26, pady=(22, 4))
        ttk.Label(head, text="ReLink", style="Head.TLabel").pack(side="left")
        ttk.Label(head, text="Ocarina of Time · Switch 2 · built from your own copy",
                  style="Status.TLabel").pack(side="left", padx=(12, 0), pady=(6, 0))
        tk.Frame(root, background=ACCENT, height=2).pack(fill="x", padx=26, pady=(10, 0))

        body = ttk.Frame(root)
        body.pack(fill="both", expand=True, padx=26, pady=18)

        # ---- 1. the game ----
        c1 = self.card(body, "1", "Your copy of the game")
        ttk.Radiobutton(c1, text="A .nup file", value="nup", variable=self.src,
                        command=self.refresh).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Radiobutton(c1, text="The romfs and exefs folders", value="folders", variable=self.src,
                        command=self.refresh).grid(row=2, column=0, sticky="w", pady=2)
        self.nup_label = ttk.Label(c1, style="Dim.TLabel")
        self.nup_label.grid(row=1, column=1, sticky="w", padx=12)
        ttk.Button(c1, text="Choose…", command=self.choose_nup).grid(row=1, column=2, sticky="e")
        self.folders_label = ttk.Label(c1, style="Dim.TLabel")
        self.folders_label.grid(row=2, column=1, sticky="w", padx=12)
        ttk.Button(c1, text="Choose…", command=self.choose_folders).grid(row=2, column=2, sticky="e")
        c1.columnconfigure(1, weight=1)

        # ---- 2. where ----
        c2 = self.card(body, "2", "Where the game is built")
        self.out_label = ttk.Label(c2, style="Dim.TLabel")
        self.out_label.grid(row=1, column=0, sticky="w", columnspan=2)
        ttk.Button(c2, text="Choose…", command=self.choose_out).grid(row=1, column=2, sticky="e")
        c2.columnconfigure(0, weight=1)

        # ---- 3. language ----
        c3 = self.card(body, "3", "The game's language")
        ttk.Combobox(c3, textvariable=self.lang, state="readonly", width=34, font=self.f_body,
                     values=["%s — %s" % (c, n) for c, n in LANGUAGES]).grid(row=1, column=0, sticky="w")

        # ---- the build ----
        bar = ttk.Frame(body)
        bar.pack(fill="x", pady=(16, 0))
        self.go = ttk.Button(bar, text="Build the game", style="Accent.TButton",
                             command=self.start, state="disabled")
        self.go.pack(side="left")
        self.stop = ttk.Button(bar, text="Stop", command=self.cancel, state="disabled")
        self.stop.pack(side="left", padx=8)
        self.state = ttk.Label(bar, text="", style="Status.TLabel")
        self.state.pack(side="left", padx=12)

        self.bar = ttk.Progressbar(body, style="Bar.Horizontal.TProgressbar", maximum=100)
        self.bar.pack(fill="x", pady=(12, 0))

        # ---- the builder's own output ----
        wrap = tk.Frame(body, background=LINE, padx=1, pady=1)
        wrap.pack(fill="both", expand=True, pady=(14, 0))
        self.log = tk.Text(wrap, wrap="none", height=16, background=LOG_BG, foreground="#c9d4df",
                           insertbackground=FG, font=self.f_mono, borderwidth=0, padx=12, pady=10,
                           selectbackground="#2b3542", selectforeground=FG)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)
        self.log.tag_configure("stage", foreground=ACCENT, font=(mono, 9, "bold"), spacing1=6, spacing3=2)
        self.log.tag_configure("err", foreground=ERR, font=(mono, 9, "bold"))
        self.log.tag_configure("cmd", foreground="#6f8296")
        self.log.configure(state="disabled")

        self.refresh()
        root.after(100, self.drain)

    # ---- drawing ----
    def centre(self, w, h):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry("%dx%d+%d+%d" % (w, h, max(0, (sw - w) // 2), max(0, (sh - h) // 3)))

    def card(self, parent, number, title):
        wrap = tk.Frame(parent, background=LINE, padx=1, pady=1)
        wrap.pack(fill="x", pady=(0, 12))
        inner = ttk.Frame(wrap, style="Card.TFrame", padding=(16, 12))
        inner.pack(fill="x")
        head = ttk.Frame(inner, style="Card.TFrame")
        head.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(head, text=number, style="Sec.TLabel").pack(side="left")
        ttk.Label(head, text=title, style="Card.TLabel").pack(side="left", padx=(8, 0))
        return inner

    # ---- the fields ----
    def refresh(self):
        is_nup = self.src.get() == "nup"
        self.nup_label.configure(text=self.nup.get() or "none chosen",
                                 foreground=FG if self.nup.get() else DIM)
        text = self.romfs.get() + "  +  " + self.exefs.get() if (self.romfs.get() and self.exefs.get()) else ""
        self.folders_label.configure(text=text or "none chosen", foreground=FG if text else DIM)
        ready = (bool(self.nup.get()) if is_nup else bool(self.romfs.get() and self.exefs.get())) and bool(self.out.get())
        self.go.configure(state="normal" if ready and not self.proc else "disabled")
        if not self.proc:
            missing = []
            if is_nup and not self.nup.get():
                missing.append("your .nup")
            if not is_nup and not (self.romfs.get() and self.exefs.get()):
                missing.append("the romfs and exefs folders")
            if not self.out.get():
                missing.append("where to build")
            self.state.configure(text=("Choose " + ", ".join(missing) + ".") if missing else "Ready.")

    def choose_nup(self):
        p = filedialog.askopenfilename(title="Your .nup file",
                                       filetypes=[("Game dump", "*.nup"), ("All files", "*")])
        if p:
            self.nup.set(p)
            self.src.set("nup")
            self.refresh()

    def choose_folders(self):
        p = filedialog.askdirectory(title="The romfs folder")
        if not p:
            return
        self.romfs.set(p)
        p = filedialog.askdirectory(title="The exefs folder")
        if not p:
            return
        self.exefs.set(p)
        self.src.set("folders")
        self.refresh()

    def choose_out(self):
        p = filedialog.askdirectory(title="Where the game is built (a ReLink folder is made inside)",
                                    initialdir=os.path.expanduser("~"))
        if p:
            self.out.set(os.path.join(p, "ReLink"))
            self.out_label.configure(text=self.out.get(), foreground=FG)
            self.refresh()

    # ---- the build ----
    def start(self):
        args = [PY, "-I", MK, "--out", self.out.get(), "--language", self.lang.get().split(" ")[0]]
        if self.src.get() == "nup":
            args += ["--nup", self.nup.get()]
        else:
            args += ["--romfs", self.romfs.get(), "--exefs", self.exefs.get()]
        self.log_path = os.path.join(self.out.get(), "build.log")
        os.makedirs(self.out.get(), exist_ok=True)
        args += ["--log", self.log_path]
        self.written("$ " + " ".join(args) + "\n\n", "cmd")
        self.bar.configure(value=0)
        self.go.configure(state="disabled")
        self.stop.configure(state="normal")
        self.state.configure(text="Building…")
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace", bufsize=1, env=env, cwd=HERE)
        threading.Thread(target=self.read, args=(self.proc,), daemon=True).start()

    def read(self, proc):
        for line in proc.stdout:
            self.q.put(line)
        self.q.put(None)

    def written(self, text, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", text, tag or ())
        self.log.see("end")
        self.log.configure(state="disabled")

    def drain(self):
        try:
            while True:
                line = self.q.get_nowait()
                if line is None:
                    self.done()
                    return
                line = line.rstrip("\n")
                if line.startswith("@@"):
                    kind, _, rest = line[2:].partition(" ")
                    if kind == "progress":
                        try:
                            self.bar.configure(value=float(rest) * 100)
                        except ValueError:
                            pass
                    elif kind == "stage":
                        text = rest.split(" ", 1)[-1]
                        self.state.configure(text=text)
                        self.written("\n== " + text + " ==\n", "stage")
                    elif kind == "eta":
                        head = self.state.cget("text").split(" · ")[0]
                        self.state.configure(text="%s · about %ss left" % (head, rest))
                    elif kind == "file":
                        head = self.state.cget("text").split(" · ")[0]
                        self.state.configure(text="%s · %s" % (head, rest.split(" ")[0]))
                    elif kind == "error":
                        self.written("\n!! " + rest + "\n", "err")
                else:
                    self.written(line + "\n")
        except queue.Empty:
            pass
        self.root.after(100, self.drain)

    def cancel(self):
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("ReLink", "Stop the build?"):
                return
            self.proc.terminate()
            self.state.configure(text="Stopping…")

    def done(self):
        code = self.proc.poll() if self.proc else None
        self.proc = None
        self.stop.configure(state="disabled")
        self.go.configure(state="normal")
        game = os.path.join(self.out.get(), "relink")
        if code == 0 and os.access(game, os.X_OK):
            self.state.configure(text="Built.")
            self.bar.configure(value=100)
            self.written("\n== done: %s ==\n" % game, "stage")
            if messagebox.askyesno("ReLink", "The game is built in\n%s\n\nPlay it now?" % self.out.get()):
                # The builder's own variables are dropped: the built game loads relink_vk.so and libSDL2-2.0.so.0 from
                # beside itself, and an LD_LIBRARY_PATH, APPDIR or PYTHON* left over from the AppImage can make it pick
                # the image's copies instead. The same list the Longshot builder's longshot-launch drops.
                env = {k: v for k, v in os.environ.items()
                       if not (k.startswith(("RELINK_", "PYTHON", "APPDIR", "APPIMAGE", "ARGV0", "OWD"))
                               or k == "LD_LIBRARY_PATH")}
                env["RELINK_NO_UPDATE_CHECK"] = "1"
                subprocess.Popen([game], cwd=self.out.get(), env=env)
                self.root.after(500, self.root.destroy)
        else:
            self.state.configure(text="The build did not finish.")
            messagebox.showerror("ReLink", "The build did not finish. Its log is in\n%s/build.log" % self.out.get())


def main():
    root = tk.Tk()
    Window(root)
    root.mainloop()


if __name__ == "__main__":
    main()
