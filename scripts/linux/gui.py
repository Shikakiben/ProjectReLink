#!/usr/bin/env python3
# ReLink's window: what to build from, where, the language, then the build with its own output shown as it goes.
# Called by AppRun when it is given no argument; any argument goes to make_game.py as it is (the command line).
# customtkinter over the AppImage's own tkinter: rounded widgets and a real dark theme, 1.7 MB, nothing to build.
import os
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

try:
    import customtkinter as ctk
except ImportError:   # (an AppImage built before customtkinter was added to deps.sh: say so, do not vanish)
    import tkinter as _tk
    import tkinter.messagebox as _mb
    _r = _tk.Tk()
    _r.withdraw()
    _mb.showerror("ReLink", "This AppImage has no customtkinter, so it cannot draw its window.\n"
                            "Run it with --help for the command line.")
    raise SystemExit(1)

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

BG     = "#12161c"
CARD   = "#1b222b"
CARD2  = "#232c37"
LINE   = "#2d3845"
FG     = "#e8eef5"
DIM    = "#8794a3"
ACCENT = "#57b9a5"
ACCENT_HOVER = "#48a491"
LOG_BG = "#0c1015"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")


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
        self.lang = ctk.StringVar(value="fr — Français")

        self.f_head = ctk.CTkFont(size=24, weight="bold")
        self.f_sub = ctk.CTkFont(size=12)
        self.f_body = ctk.CTkFont(size=13)
        self.f_sec = ctk.CTkFont(size=11, weight="bold")
        self.f_small = ctk.CTkFont(size=11)
        self.f_btn = ctk.CTkFont(size=13, weight="bold")
        self.f_mono = ctk.CTkFont(family="Liberation Mono", size=11)

        root.title("ReLink — Ocarina of Time (Switch 2)")
        root.minsize(880, 720)
        root.configure(fg_color=BG)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry("940x780+%d+%d" % (max(0, (sw - 940) // 2), max(0, (sh - 780) // 3)))

        page = ctk.CTkFrame(root, fg_color=BG, corner_radius=0)
        page.pack(fill="both", expand=True, padx=26, pady=22)

        # ---- header ----
        head = ctk.CTkFrame(page, fg_color=BG)
        head.pack(fill="x")
        ctk.CTkLabel(head, text="ReLink", font=self.f_head, text_color=FG).pack(side="left")
        ctk.CTkLabel(head, text="Ocarina of Time · Switch 2 · built from your own copy",
                     font=self.f_sub, text_color=DIM).pack(side="left", padx=(14, 0), pady=(8, 0))
        ctk.CTkFrame(page, fg_color=ACCENT, height=2, corner_radius=1).pack(fill="x", pady=(14, 18))

        # ---- 1. the game ----
        c1 = self.card(page, "1", "YOUR COPY OF THE GAME")
        self.rb_nup = ctk.CTkRadioButton(c1, text="A .nup file", variable=self.src, value="nup",
                                         command=self.refresh, font=self.f_body, text_color=FG,
                                         fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color=LINE)
        self.rb_nup.pack(anchor="w", pady=(2, 6))
        self.nup_label = ctk.CTkLabel(c1, text="none chosen", font=self.f_small, text_color=DIM,
                                      anchor="w")
        self.nup_label.pack(fill="x", padx=(28, 0))
        self.bt_nup = ctk.CTkButton(c1, text="Choose the .nup…", width=170, command=self.choose_nup,
                                    fg_color=CARD2, hover_color=LINE, text_color=FG, font=self.f_small,
                                    corner_radius=8)
        self.bt_nup.pack(anchor="w", padx=(28, 0), pady=(0, 10))

        ctk.CTkRadioButton(c1, text="The romfs and exefs folders", variable=self.src, value="folders",
                           command=self.refresh, font=self.f_body, text_color=FG,
                           fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color=LINE).pack(anchor="w", pady=(2, 6))
        self.folders_label = ctk.CTkLabel(c1, text="none chosen", font=self.f_small, text_color=DIM, anchor="w")
        self.folders_label.pack(fill="x", padx=(28, 0))
        ctk.CTkButton(c1, text="Choose the folders…", width=170, command=self.choose_folders,
                      fg_color=CARD2, hover_color=LINE, text_color=FG, font=self.f_small,
                      corner_radius=8).pack(anchor="w", padx=(28, 0))

        # ---- 2. where ----
        c2 = self.card(page, "2", "WHERE THE GAME IS BUILT")
        self.out_label = ctk.CTkLabel(c2, text="none chosen", font=self.f_small, text_color=DIM, anchor="w")
        self.out_label.pack(fill="x")
        ctk.CTkButton(c2, text="Choose the folder…", width=170, command=self.choose_out,
                      fg_color=CARD2, hover_color=LINE, text_color=FG, font=self.f_small,
                      corner_radius=8).pack(anchor="w", pady=(6, 0))

        # ---- 3. language ----
        c3 = self.card(page, "3", "THE GAME'S LANGUAGE")
        ctk.CTkOptionMenu(c3, variable=self.lang, values=["%s — %s" % (c, n) for c, n in LANGUAGES],
                          width=280, font=self.f_body, dropdown_font=self.f_body,
                          fg_color=CARD2, button_color=LINE, button_hover_color=ACCENT_HOVER,
                          text_color=FG, dropdown_fg_color=CARD, dropdown_hover_color=LINE,
                          dropdown_text_color=FG, corner_radius=8).pack(anchor="w")

        # ---- the build ----
        bar = ctk.CTkFrame(page, fg_color=BG)
        bar.pack(fill="x", pady=(6, 0))
        self.go = ctk.CTkButton(bar, text="Build the game", width=190, height=42, command=self.start,
                                state="disabled", font=self.f_btn, corner_radius=10,
                                fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#08120f")
        self.go.pack(side="left")
        self.stop = ctk.CTkButton(bar, text="Stop", width=90, height=42, command=self.cancel,
                                  state="disabled", font=self.f_body, corner_radius=10,
                                  fg_color=CARD2, hover_color=LINE, text_color=FG)
        self.stop.pack(side="left", padx=10)
        self.state = ctk.CTkLabel(bar, text="", font=self.f_small, text_color=DIM, anchor="w")
        self.state.pack(side="left", padx=12)

        self.bar = ctk.CTkProgressBar(page, height=6, corner_radius=3, progress_color=ACCENT,
                                      fg_color="#0a0e12")
        self.bar.set(0)
        self.bar.pack(fill="x", pady=(14, 0))

        # ---- the builder's own output ----
        self.log = ctk.CTkTextbox(page, fg_color=LOG_BG, border_color=LINE, border_width=1,
                                  corner_radius=10, font=self.f_mono, text_color="#c6d2df",
                                  wrap="none", activate_scrollbars=True)
        self.log.pack(fill="both", expand=True, pady=(14, 0))
        self.log.tag_config("stage", foreground=ACCENT)
        self.log.tag_config("err", foreground="#e0755f")
        self.log.tag_config("cmd", foreground="#64758a")
        self.log.configure(state="disabled")

        self.refresh()
        root.after(100, self.drain)

    def card(self, parent, number, title):
        card = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=12, border_width=1, border_color=LINE)
        card.pack(fill="x", pady=(0, 12))
        head = ctk.CTkFrame(card, fg_color=CARD)
        head.pack(fill="x", padx=18, pady=(14, 8))
        ctk.CTkLabel(head, text=number, font=self.f_sec, text_color=ACCENT).pack(side="left")
        ctk.CTkLabel(head, text=title, font=self.f_sec, text_color=DIM).pack(side="left", padx=(8, 0))
        body = ctk.CTkFrame(card, fg_color=CARD)
        body.pack(fill="x", padx=18, pady=(0, 16))
        return body

    # ---- the fields ----
    def refresh(self):
        is_nup = self.src.get() == "nup"
        self.nup_label.configure(text=self.nup.get() or "none chosen",
                                 text_color=FG if self.nup.get() else DIM)
        text = self.romfs.get() + "  +  " + self.exefs.get() if (self.romfs.get() and self.exefs.get()) else ""
        self.folders_label.configure(text=text or "none chosen", text_color=FG if text else DIM)
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
            self.out_label.configure(text=self.out.get(), text_color=FG)
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
        self.bar.set(0)
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
                            self.bar.set(max(0.0, min(1.0, float(rest))))
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
            self.bar.set(1)
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


if __name__ == "__main__":
    root = ctk.CTk()
    Window(root)
    root.mainloop()
