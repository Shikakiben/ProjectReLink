"""The update check: the fork's latest release on GitHub, asked for once at start, in the background.

Nothing is downloaded and nothing is replaced. When the latest release is not the one this AppImage was built from,
`done(tag, page)` is called and the window shows a chip that opens the release page in the browser. Offline, or a slow
or silent API, shows nothing at all — the check never delays the window.

    updates.check(appdir, done)     -> in a thread; done(tag, page) only when there is something newer
    updates.version(appdir)         -> the version this AppImage was built from ("dev" when not known)
"""
import json
import os
import threading
import urllib.request

REPO = "Shikakiben/ProjectReLink"
API = "https://api.github.com/repos/%s/releases/latest" % REPO
PAGE = "https://github.com/%s/releases/latest" % REPO


def version(appdir):
    """The version written into the AppImage by scripts/linux/appimage.sh (usr/share/relink/VERSION)."""
    try:
        with open(os.path.join(appdir, "usr", "share", "relink", "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "dev"


def parts(tag):
    """'v0.7.5-linux.19' -> (0, 7, 5, 19): the numbers, in order, whatever the tag spells around them."""
    out, run = [], ""
    for ch in tag:
        if ch.isdigit():
            run += ch
        elif run:
            out.append(int(run))
            run = ""
    if run:
        out.append(int(run))
    return tuple(out)


def newer(tag, mine):
    return parts(tag) > parts(mine)


def check(appdir, done, timeout=6.0):
    """Ask GitHub in a thread and call done(tag, page) from it when a newer release exists."""
    mine = version(appdir)
    if not mine or mine == "dev":
        return

    def run():
        try:
            req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                                       "User-Agent": "ReLink-linux"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                tag = json.load(r).get("tag_name", "")
        except Exception:
            return
        if tag and newer(tag, mine):
            done(tag, PAGE)

    threading.Thread(target=run, daemon=True).start()
