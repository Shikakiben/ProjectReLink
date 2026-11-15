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

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["RELINK_NO_SEARCH"] = "1"   # (the search is not what this tests, and it would walk the runner's disk)

from PySide6.QtWidgets import QApplication


class FakeProcess:
    """Stands in for the builder: start() only needs to not fail, and read() only needs an empty stream."""

    stdout = ()

    def poll(self):
        return None

    def terminate(self):
        pass


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

    print("selftest: the window starts, every step and the bar move, and Install opens the installation page")
    return 0


if __name__ == "__main__":
    sys.exit(main())
