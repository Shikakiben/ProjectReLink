#!/usr/bin/env python3
"""The window's own paths, without building anything: every step, the bar, and the Install button.

Run against a built AppDir (the CI does, before publishing):

    RELINK_APPDIR=build-linux/AppDir usr/python/bin/python3 scripts/linux/selftest.py

Why this exists: v0.7.6 shipped with a window that opened and whose Install button did nothing. A Qt slot that raises
is printed and then swallowed, so the button only looked dead — and starting the window, which is all the CI checked,
was enough to pass. This drives the same slot with the builder stubbed out, so a rename or a missing attribute shows up
as a failure instead of a silent button.
"""
import os
import sys
import tempfile
import threading

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["RELINK_NO_SEARCH"] = "1"   # (the search is not what this tests, and it would walk the runner's disk)
# (its own choices and work.txt: the test must not read, or write, the ones of whoever runs it)
os.environ.setdefault("XDG_CONFIG_HOME", os.path.join(tempfile.gettempdir(), "relink-selftest-config"))

from PySide6.QtWidgets import QApplication


class FakeProcess:
    """Stands in for the builder: start() only needs to not fail, and read() only needs a stream that does not end.

    A stream that ended at once made read() queue its None at once, and the next 100 ms tick called done(): the page
    moved before the test looked at it (and a real build never ends in the same breath as it starts)."""

    def __init__(self):
        self.stdout = _Never()

    def poll(self):
        return None

    def terminate(self):
        pass


class _Never:
    """An output stream that never yields and never ends: the build keeps running, as far as the window knows."""

    def __iter__(self):
        return self

    def __next__(self):
        _never.wait()
        raise StopIteration


_never = threading.Event()


def main():
    app = QApplication(sys.argv)
    import theme as T
    T.load_fonts()          # (after QApplication: QFontDatabase needs it)
    import gui

    gui.subprocess.Popen = lambda *a, **k: FakeProcess()

    # (the window answers a failure with a modal box, which has nothing to click here: the box is stubbed so a failed
    #  start is an error code instead of a run that never returns)
    class NoDialogs:
        class StandardButton:
            Yes = 1
            No = 2

        @staticmethod
        def critical(*a, **k):
            return None

        @staticmethod
        def question(*a, **k):
            return NoDialogs.StandardButton.No

    gui.QMessageBox = NoDialogs

    w = gui.Window()
    w.resize(1120, 700)

    # the window comes up
    w.show()
    app.processEvents()

    # every step, and the bar, can be driven
    for step in ("read", "lift", "compile", "finish"):
        w.set_stage(step)
        app.processEvents()
    w.progress(0.5)
    w.progress(1.0)
    app.processEvents()

    # the Install button opens the installation page and starts the builder
    w.nup, w.out = "/dev/null", os.path.join(os.environ.get("TMPDIR", "/tmp"), "relink-selftest")
    w.refresh()
    if not w.go.isEnabled():
        print("selftest: the Install button is disabled with a copy and a folder chosen", file=sys.stderr)
        return 1
    # (a slot that raises prints the traceback and carries on, so a click that fails must be caught here, before the
    #  page check below can hang on a state the failure left behind)
    try:
        w.go.click()
    except Exception as error:
        print("selftest: Install raised %s: %s" % (type(error).__name__, error), file=sys.stderr)
        return 1
    app.processEvents()
    if w.pages.currentIndex() != 1:
        print("selftest: Install did not open the installation page", file=sys.stderr)
        return 1
    if w.proc is None:
        print("selftest: Install did not start the builder", file=sys.stderr)
        return 1

    # the ready page: the button says Play, and the line under it the version
    w.proc = None
    w.show_ready()
    app.processEvents()
    if w.pages.currentIndex() != 2 or w.go.text() != "Play":
        print("selftest: the ready page did not come up with Play", file=sys.stderr)
        return 1

    # the problem page: what went wrong, and a report to copy
    w.show_problem("the selftest's own reason")
    app.processEvents()
    if w.pages.currentIndex() != 3 or "the selftest's own reason" not in w.problem_text.text():
        print("selftest: the problem page did not say what went wrong", file=sys.stderr)
        return 1
    w.copy_report()
    if "the selftest's own reason" not in QApplication.clipboard().text():
        print("selftest: Copy for a report copied nothing", file=sys.stderr)
        return 1
    w.toggle_problem_log()
    if not w.problem_log.isVisible():
        print("selftest: Show details on the problem page did nothing", file=sys.stderr)
        return 1

    # the home page reads the game's own options and keeps every line it does not show
    open(os.path.join(w.out, "relink"), "w").write("#!/bin/sh\n")
    os.chmod(os.path.join(w.out, "relink"), 0o755)
    with open(os.path.join(w.out, "relink_options.ini"), "w", encoding="utf-8") as f:
        f.write("fullscreen=1\nresolution=2\nsome_future_key=42\n")
    w.show_home()
    app.processEvents()
    if w.pages.currentIndex() != 4 or w.opt_resolution.currentData() != 2:
        print("selftest: the home page did not read the game's options", file=sys.stderr)
        return 1
    w.opt_framegen.setCurrentIndex(w.opt_framegen.findData(3))
    with open(os.path.join(w.out, "relink_options.ini"), encoding="utf-8") as f:
        saved = f.read()
    if "frame_generation=3" not in saved or "some_future_key=42" not in saved:
        print("selftest: the home page did not keep the options it does not show", file=sys.stderr)
        return 1

    # a window started with a built game opens on the home page, not on Install (and the way back is always there)
    import json
    os.makedirs(os.path.dirname(gui.CHOICES), exist_ok=True)
    with open(gui.CHOICES, "w", encoding="utf-8") as f:
        json.dump({"nup": "/dev/null", "romfs": "", "exefs": "", "out": w.out, "language": "fr"}, f)
    second = gui.Window()
    app.processEvents()
    if second.pages.currentIndex() != 4:
        print("selftest: a window with a built game did not open on the home page", file=sys.stderr)
        return 1
    second.show_page(0)
    app.processEvents()
    if second.your_game.isHidden():
        print("selftest: the setup page has no way back to the home page", file=sys.stderr)
        return 1
    second.close()

    print("selftest: the window starts, every step and the bar move, Install opens the installation page, "
          "the ready page says Play, the problem page explains and copies, the home page reads and keeps "
          "the game's options, and a built game opens on it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
