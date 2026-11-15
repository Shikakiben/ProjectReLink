"""The .nup files on this PC, as launcher/Finder.cs looks for them.

Nothing here may raise. A folder that cannot be read is skipped, a filesystem that answers slowly is left alone, a
machine with none gives an empty list, and the window then simply says to choose a file. `RELINK_NO_SEARCH=1` turns the
whole thing off for anyone who would rather browse.

A .nup's name means nothing: two files can be called anything and hold different builds. What identifies the game is the
build id inside it, which `make_game.py --check` reads in about two seconds — so this only finds candidates.
"""
import datetime
import os
import sys
import time

DEADLINE = 6.0          # (seconds; a walk of a whole disk takes 16 s here, but a games folder is shallow and turns up
                        #  in under two. The budget is time, not folders: a count starves the useful tree behind a big one)
SKIP_NAMES = {"proc", "sys", "dev", "run", "boot", "lost+found", "snap", "var", "usr", "lib", "lib64", "bin", "sbin",
              "etc", "opt", "srv", "tmp", "Windows", "Program Files", "Program Files (x86)", "System Volume Information"}


def enabled():
    off = os.environ.get("RELINK_NO_SEARCH", "")
    return not (off and off != "0")


def find_dumps(deadline=DEADLINE, on_found=None):
    """Every .nup under the usual places, newest first, as [{path, where, size, modified}]. Never raises.

    on_found(dump) is called as each one turns up, from the caller's thread, so a window can fill its list while the
    walk continues."""
    if not enabled():
        return []
    begun = time.time()
    seen, found = set(), []

    def look(folder, label):
        try:
            with os.scandir(folder) as it:
                for entry in it:
                    try:
                        name = entry.name
                        if name.startswith(".") or not name.lower().endswith(".nup"):
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        real = os.path.realpath(entry.path)
                        if real in seen:
                            continue
                        seen.add(real)
                        dump = {"path": real, "where": label, "size": os.path.getsize(real),
                                "modified": os.path.getmtime(real)}
                        found.append(dump)
                        if on_found:
                            on_found(dump)
                    except OSError:
                        continue
        except (OSError, ValueError):
            pass

    def walk(root, label):
        try:
            for folder, dirs, _files in os.walk(root, topdown=True):
                if time.time() - begun > deadline:
                    return False
                dirs[:] = [d for d in dirs if not d.startswith((".", "$")) and d not in SKIP_NAMES]
                look(folder, label)
            return True
        except (OSError, ValueError):
            return True

    try:
        for root, label in _roots():
            if not os.path.isdir(root):
                continue
            if not walk(root, label) or time.time() - begun > deadline:
                break
    except Exception:      # (nothing here is worth an error in the player's face)
        pass
    found.sort(key=lambda d: d["modified"], reverse=True)
    return found


def _roots():
    """(folder, what to call it in the window), the player's own places first and the mounted disks after."""
    home = os.path.expanduser("~")
    out, seen = [], set()
    for name, label in (("Téléchargements", "Downloads"), ("Downloads", "Downloads"),
                        ("Bureau", "Desktop"), ("Desktop", "Desktop"),
                        ("Documents", "Documents"), ("", "Home")):
        path = os.path.join(home, name) if name else home
        try:
            key = os.path.realpath(path)
        except OSError:
            continue
        if os.path.isdir(path) and key not in seen:
            seen.add(key)
            out.append((path, label))
    for base in ("/media", "/run/media", "/mnt"):
        if not os.path.isdir(base):
            continue
        try:
            with os.scandir(base) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False) and not entry.name.startswith("."):
                            key = os.path.realpath(entry.path)
                            if key not in seen:
                                seen.add(key)
                                out.append((entry.path, entry.name))
                    except OSError:
                        continue
        except (OSError, ValueError):
            pass
    return out


def title_ids(path):
    """The title ids inside a .nup, read from its table of contents: no extraction, about a third of a second.

    None when the file cannot be read, so a caller can tell "not this game" from "could not say"."""
    try:
        nx2 = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "nx2"))
        if nx2 not in sys.path:
            sys.path.insert(0, nx2)
        import nup
        return {t["id"] for t in nup.Nup(path).titles}
    except Exception:
        return None


def size_text(n):
    try:
        return "%.1f GB" % (n / (1 << 30)) if n >= (1 << 30) else "%.0f MB" % (n / (1 << 20))
    except (TypeError, ValueError):
        return ""


def ago(timestamp):
    """Finder.cs's Ago: today, yesterday, days, weeks, then a date."""
    try:
        then = datetime.datetime.fromtimestamp(timestamp)
        now = datetime.datetime.now()
        days = (now.date() - then.date()).days
        if days <= 0:
            return "modified today"
        if days == 1:
            return "modified yesterday"
        if days < 14:
            return "%d days ago" % days
        if days < 60:
            return "%d weeks ago" % (days // 7)
        return then.strftime("%d %b %Y")
    except (OSError, ValueError, OverflowError):
        return ""
