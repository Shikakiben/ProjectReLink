#!/usr/bin/env python3
# ReLink's window: what to build from, where, the language, then the build with its own output shown as it goes.
# Called by AppRun when it is given no argument; any argument goes to make_game.py as it is (the command line).
# tkinter draws it: the AppImage's Python carries it (python-build-standalone's Tk 9).
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

HERE = os.environ.get("RELINK_APPDIR") or os.path.dirname(os.path.abspath(__file__)) + "/../../../../.."
PY = os.path.join(HERE, "usr", "python", "bin", "python3")
MK = os.path.join(HERE, "usr", "share", "relink", "nx2", "make_game.py")

LANGUAGES = [
    ("en-US", "English (US)"), ("en-GB", "English (UK)"), ("fr", "Français"),
    ("fr-CA", "Français (Canada)"), ("de", "Deutsch"), ("es", "Español"),
    ("es-419", "Español (Latinoamérica)"), ("it", "Italiano"), ("ja", "日本語"),
    ("ko", "한국어"), ("nl", "Nederlands"), ("pt-BR", "Português (Brasil)"),
    ("pt-PT", "Português (Portugal)"), ("ru", "Русский"), ("zh-CN", "简体中文"),
    ("zh-TW", "繁體中文"),
]


class Window:
    def __init__(self, root):
        self.root = root
        self.proc = None
        self.q = queue.Queue()
        self.src = tk.StringVar(value="nup")        # nup | folders
        self.nup = tk.StringVar()
        self.romfs = tk.StringVar()
        self.exefs = tk.StringVar()
        self.out = tk.StringVar()
        self.lang = tk.StringVar(value="fr")

        root.title("ReLink — build The Legend of Zelda: Ocarina of Time (Switch 2)")
        root.minsize(760, 620)
        f = ttk.Frame(root, padding=12)
        f.pack(fill="both", expand=True)

        # ---- your copy of the game ----
        g = ttk.LabelFrame(f, text=" 1. Your copy of the game ", padding=8)
        g.pack(fill="x")
        ttk.Radiobutton(g, text="A .nup file", value="nup", variable=self.src,
                        command=self.refresh).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(g, text="The romfs and exefs folders", value="folders", variable=self.src,
                        command=self.refresh).grid(row=1, column=0, sticky="w")
        self.nup_label = ttk.Label(g, text="(none chosen)", foreground="#666")
        self.nup_label.grid(row=0, column=1, sticky="w", padx=8)
        ttk.Button(g, text="Choose…", command=self.choose_nup).grid(row=0, column=2, sticky="e")
        self.folders_label = ttk.Label(g, text="(none chosen)", foreground="#666")
        self.folders_label.grid(row=1, column=1, sticky="w", padx=8)
        ttk.Button(g, text="Choose…", command=self.choose_folders).grid(row=1, column=2, sticky="e")
        g.columnconfigure(1, weight=1)

        # ---- where it goes ----
        o = ttk.LabelFrame(f, text=" 2. Where the game is built ", padding=8)
        o.pack(fill="x", pady=(8, 0))
        self.out_label = ttk.Label(o, text="(none chosen)", foreground="#666")
        self.out_label.pack(side="left", fill="x", expand=True)
        ttk.Button(o, text="Choose…", command=self.choose_out).pack(side="right")

        # ---- the language ----
        l = ttk.LabelFrame(f, text=" 3. The game's language ", padding=8)
        l.pack(fill="x", pady=(8, 0))
        ttk.Combobox(l, textvariable=self.lang, state="readonly", width=28,
                     values=["%s — %s" % (c, n) for c, n in LANGUAGES]).pack(side="left")

        # ---- the build ----
        b = ttk.Frame(f)
        b.pack(fill="x", pady=(10, 0))
        self.go = ttk.Button(b, text="Build the game", command=self.start, state="disabled")
        self.go.pack(side="left")
        self.stop = ttk.Button(b, text="Stop", command=self.cancel, state="disabled")
        self.stop.pack(side="left", padx=6)
        self.state = ttk.Label(b, text="Choose your copy and where to build it.", foreground="#444")
        self.state.pack(side="left", padx=10)

        self.bar = ttk.Progressbar(f, mode="determinate", maximum=100)
        self.bar.pack(fill="x", pady=(8, 0))

        # ---- what the builder says, as it says it ----
        self.log = tk.Text(f, wrap="none", height=18, background="#111", foreground="#ddd",
                           insertbackground="#ddd", font=("TkFixedFont", 9))
        sb = ttk.Scrollbar(f, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True, pady=(8, 0))
        self.log.configure(state="disabled")

        self.refresh()
        root.after(100, self.drain)

    # ---- the fields ----
    def refresh(self):
        is_nup = self.src.get() == "nup"
        self.nup_label.configure(text=self.nup.get() or "(none chosen)",
                                 foreground="#000" if self.nup.get() else "#666")
        text = ""
        if self.romfs.get() and self.exefs.get():
            text = self.romfs.get() + "  +  " + self.exefs.get()
        self.folders_label.configure(text=text or "(none chosen)", foreground="#000" if text else "#666")
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
            self.state.configure(text="Choose " + ", ".join(missing) + "." if missing else "Ready when you are.")

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
        p = filedialog.askdirectory(title="Where the game is built (ReLink makes a folder inside it)",
                                    initialdir=os.path.expanduser("~"))
        if p:
            self.out.set(os.path.join(p, "ReLink"))
            self.out_label.configure(text=self.out.get(), foreground="#000")
            self.refresh()

    # ---- the build ----
    def start(self):
        args = [PY, "-I", MK, "--out", self.out.get(), "--language", self.lang.get().split(" ")[0]]
        if self.src.get() == "nup":
            args += ["--nup", self.nup.get()]
        else:
            args += ["--romfs", self.romfs.get(), "--exefs", self.exefs.get()]
        log = os.path.join(self.out.get(), "build.log")
        os.makedirs(self.out.get(), exist_ok=True)
        args += ["--log", log]
        self.written("$ " + " ".join(args) + "\n\n")
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

    def written(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
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
                        self.state.configure(text=rest.split(" ", 1)[-1])
                        self.written("\n== " + rest.split(" ", 1)[-1] + " ==\n")
                    elif kind == "eta":
                        self.state.configure(text=self.state.cget("text").split(" — ")[0] + " — about " + rest + "s left")
                    elif kind == "file":
                        self.state.configure(text=self.state.cget("text").split(" — ")[0] + " — " + rest.split(" ")[0])
                    elif kind == "error":
                        self.written("\n!! " + rest + "\n")
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
            self.written("\n== done: %s ==\n" % game)
            if messagebox.askyesno("ReLink", "The game is built in\n%s\n\nPlay it now?" % self.out.get()):
                # The builder's own variables are dropped: the built game loads relink_vk.so and libSDL2-2.0.so.0 from
                # beside itself, and an LD_LIBRARY_PATH, APPDIR or PYTHON* left over from the AppImage can make it pick
                # the image's copies instead. The same list the Longshot builder's longshot-launch drops.
                env = {k: v for k, v in os.environ.items()
                       if not (k.startswith(("RELINK_", "PYTHON", "APPDIR", "APPIMAGE", "ARGV0", "OWD"))
                               or k == "LD_LIBRARY_PATH")}
                env["RELINK_NO_UPDATE_CHECK"] = "1"   # (this folder was just built; the launcher's own check is not wanted)
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
