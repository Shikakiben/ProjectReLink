#!/usr/bin/env python3
# ReLink's window: what to build from, where, the language, then the build with its own output shown as it goes.
# Called by AppRun when it is given no argument; any argument goes to make_game.py as it is (the command line).
# PySide6 and theme.py (Hookshot's builder theme, carried over): the Slate palette, Inter, hand-drawn controls.
# The layout is the Windows launcher's: the sky of scene.py behind, the title on it, and an opaque panel carrying the
# settings, so the window looks like a ReLink launcher at whatever hour the player starts it.
import glob
import json
import math
import os
import re
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import webbrowser

# Before Qt is imported, two things:
#  - the bundled Qt's libraries come first. This machine's own Qt (an installed qt6-qtbase, say) is found otherwise,
#    and the platform plugin then fails on "Qt_6_PRIVATE_API not found": it linked against the image's, not the host's.
#  - on a Wayland session with XWayland, Qt draws no window decoration (GNOME has no server-side decorations and Qt's
#    own factory fails), so the window would have no title bar. xcb has them. A Wayland session without DISPLAY keeps
#    Qt's choice.
_appdir = os.environ.get("RELINK_APPDIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                         "..", "..", "..", "..", "..")
_qtlib = os.environ.get("RELINK_QT_LIB") or ""
if not _qtlib:
    found = glob.glob(os.path.join(_appdir, "usr", "python", "lib", "python3*", "site-packages", "PySide6", "Qt", "lib"))
    _qtlib = found[0] if found else ""
_qtlib = os.path.normpath(_qtlib) if _qtlib else ""
if _qtlib and os.path.isdir(_qtlib):
    os.environ["LD_LIBRARY_PATH"] = _qtlib + ((":" + os.environ["LD_LIBRARY_PATH"]) if os.environ.get("LD_LIBRARY_PATH") else "")
if os.environ.get("XDG_SESSION_TYPE") == "wayland" and os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen, QTextCharFormat,
                           QTextCursor)
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
                               QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

# (-I, which AppRun passes, is isolated mode: it keeps the script's own directory out of sys.path, so the three modules
#  beside this file have to be put there. Without this the AppImage dies on "No module named 'scene'".)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import finder
import scene
import theme as T
import updates
from theme import C, Button, Chip, Choice, PathEdit, css, font

HERE = os.path.normpath(_appdir)
CHOICES = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "relink", "install.json")
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

# The launcher maps a step's own 0..1 into its share of the whole build (launcher/Install.cs: Weight). It has a
# "download" slot first that we do not have, so read starts at 0 here instead of 0.04; everything else is its numbers.
# (the title id inside every .nup of this game: 0400486024dec000. A file with another one is another game, and is not
#  listed at all — a player with fifteen dumps should not have to read fourteen lines about games this cannot build)
OOT_TITLE = 0x0400486024DEC000

STAGE_WEIGHT = {"read": (0.00, 0.08), "lift": (0.08, 0.14), "compile": (0.22, 0.74), "finish": (0.96, 0.04)}

# the launcher's own display face (App.xaml: Palatino Linotype, Book Antiqua, Georgia), with what Linux has of it
DISPLAY = ["Palatino Linotype", "P052", "Book Antiqua", "Georgia", "Noto Serif", "DejaVu Serif", "serif"]


def display(size, weight=QFont.Weight.Normal):
    f = QFont()
    f.setFamilies(DISPLAY)
    f.setPixelSize(int(size))
    f.setWeight(weight)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def label(text, size=13, weight=QFont.Weight.Normal, color="Ink", wrap=False):
    """color: a key of theme.C, or a colour of its own (the launcher's warm greys are not in the Slate palette)."""
    w = QLabel(text)
    w.setFont(font(size, weight))
    w.setStyleSheet("color: %s; background: transparent;" % css(C[color] if color in C else QColor(color)))
    if wrap:
        w.setWordWrap(True)
    return w


def hairline():
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet("background: rgba(255,255,255,18); border: none;")
    return line


class LinkChip(Chip):
    """A Chip that opens a page when clicked (the update offer)."""

    def __init__(self, text, color, soft, url):
        super().__init__(text, color, soft)
        self.url = url
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):
        webbrowser.open(self.url)


class Staff(QWidget):
    """The launcher's staff, carried over from launcher/Staff.cs: five lines, the bar lines that open and close it, and
    one note per step of the build — Read, Translate, Compile, Assemble. A note is hollow while it waits, gold and
    breathing while it is the step at work, gold when done. The lines fill with gold as the build goes, so the staff is
    both the launcher's picture and the progress bar.

    The numbers are the launcher's own: 424 wide, the first line 40 down, 10 between lines, the notes 15 x 11 heads
    tilted 20 degrees with a 34 px stem, and the labels 20 px under the last line."""

    WIDTH = 424
    TOP = 40
    GAP = 10
    GOLD = "#C9A24B"        # (App.xaml's CGold)
    BONE = "#EFE6D0"
    BONE_FAINT = "#8E907B"
    WARN = "#D9825B"

    def __init__(self, items):
        super().__init__()
        self.items = list(items)      # [(id, label), ...]
        self.subs = {}                # {id: the line under its label}
        self.value = 0.0
        self.stage = None             # the id of the step at work
        self.problem = False
        self.phase = 0.0
        self.setFixedSize(self.WIDTH, self.TOP + 4 * self.GAP + 20 + 40)
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._breathe)

    # ---- what the window tells it ----
    def set_items(self, items, subs=None):
        """The notes change with the page: the build's four steps, or the home page's three."""
        self.items = list(items)
        self.subs = dict(subs or {})
        self.stage = None
        self.problem = False
        self._timer.stop()
        self.update()

    def set(self, v):
        self.value = max(0.0, min(1.0, v))
        if self.value >= 1.0:
            self._timer.stop()   # (nothing left to breathe)
        self.update()

    def set_stage(self, stage):
        self.stage, self.problem = stage, False
        self._sync()

    def set_problem(self):
        self.problem = True
        self._sync()

    def _sync(self):
        if self.stage is not None and not self.problem and self.value < 1.0:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def _breathe(self):
        self.phase = (self.phase + 0.03 / 1.8) % 1.0   # (1 -> 0.35 -> 1 over 1.8 s, as the launcher's DoubleAnimation)
        self.update()

    def _state(self, ident):
        if self.problem and ident == self.stage:
            return "problem"
        if self.value >= 1.0:
            return "done"
        if self.stage is None:
            return "waiting"
        order = [i for i, _ in self.items]
        if ident not in order or self.stage not in order:
            return "waiting"
        here, there = order.index(self.stage), order.index(ident)
        return "done" if there < here else ("active" if there == here else "waiting")

    # ---- drawing ----
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        top, gap = self.TOP, self.GAP
        bottom = top + 4 * gap
        line = QColor(self.BONE_FAINT)
        line.setAlphaF(0.55)
        gold = QColor(self.GOLD)
        end = (self.WIDTH - 6) * self.value   # (the fill stops at the closing bar, not over it)

        # the five lines, then the gold that says how far the build has gone
        for i in range(5):
            y = top + i * gap
            p.setPen(QPen(line, 1))
            p.drawLine(QPointF(0, y), QPointF(self.WIDTH, y))
            if end > 0:
                p.setPen(QPen(gold, 1))
                p.drawLine(QPointF(0, y), QPointF(end, y))

        # the bar lines: one where the staff begins, the double one that ends a piece
        for x, thick in ((0.5, 1.0), (self.WIDTH - 6.5, 1.0), (self.WIDTH - 1.5, 3.0)):
            p.setPen(QPen(line, thick))
            p.drawLine(QPointF(x, top), QPointF(x, bottom))

        # the notes, one per step, rising: the last step lands at the top
        n = len(self.items)
        few = n <= 3
        first = 66.0 if few else 50.0
        step = (self.WIDTH - 2 * first) / (n - 1) if n > 1 else 0.0
        text_width = 132 if few else step - 6
        size = 15 if few else (13.5 if n == 4 else 12.5)
        text_top = bottom + 20
        for i, (ident, text) in enumerate(self.items):
            x = first + i * step
            y = bottom - ((10 + i * 10) if few else ((5 if n == 4 else 0) + i * 10))
            state = self._state(ident)
            self._note(p, x, y, state)
            self._label(p, x, text_top, text_width, size, text, state)
            if self.subs.get(ident):
                p.setFont(font(12))
                p.setPen(QColor(self.BONE_FAINT))
                p.drawText(QRectF(x - text_width / 2, text_top + size + 6, text_width, 16),
                           Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self.subs[ident])
        p.end()

    def _note(self, p, x, y, state):
        if state == "waiting":
            colour, fill = QColor(self.BONE_FAINT), None
        elif state == "problem":
            colour, fill = QColor(self.WARN), QColor(self.WARN)
        else:
            colour, fill = QColor(self.GOLD), QColor(self.GOLD)
        if state == "active":   # (the head breathes, the stem does not: the launcher animates the head's opacity)
            colour.setAlphaF(0.675 + 0.325 * math.cos(2 * math.pi * self.phase))
        p.save()
        p.translate(x, y)
        p.rotate(-20)
        p.setPen(QPen(colour, 1.6))
        p.setBrush(fill if fill is not None else Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(-7.5, -5.5, 15, 11))
        p.restore()
        stem = QColor(self.GOLD if state in ("active", "done") else self.WARN if state == "problem" else self.BONE_FAINT)
        p.setPen(QPen(stem, 1.6))
        p.drawLine(QPointF(x + 6.6, y - 2), QPointF(x + 6.6, y - 36))

    @staticmethod
    def _label(p, x, text_top, width, size, text, state):
        p.setFont(font(size))
        p.setPen(QColor(Staff.BONE if state != "waiting" else Staff.BONE_FAINT))
        p.drawText(QRectF(x - width / 2, text_top, width, size + 8),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, text)


class _Mark(QWidget):
    """The diamond beside a step (launcher/Staff.cs's StepRow mark): hollow while it waits, gold outline while it runs,
    gold filled when done, the warning colour when it stopped."""

    def __init__(self):
        super().__init__()
        self.state = "waiting"
        self.setFixedSize(30, 22)

    def set_state(self, state):
        self.state = state
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        colour = QColor({"waiting": Staff.BONE_FAINT, "active": Staff.GOLD, "done": Staff.GOLD,
                         "stopped": Staff.WARN}[self.state])
        p.save()
        p.translate(3 + 4.5, 7 + 4.5)
        p.rotate(45)
        p.setPen(QPen(colour, 1.4))
        p.setBrush(colour if self.state in ("done", "stopped") else Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(-4.5, -4.5, 9, 9))
        p.restore()
        p.end()


class StepRow(QWidget):
    """One step of the build, as launcher/Staff.cs's StepRow: its mark, its name, a line under it, and its time.

    Everything is painted here rather than laid out with child labels: a QLabel clips its own text to its rect, and a
    step's row grows when its sub-line appears, which cut the top of the name in a stacked page."""

    HEIGHT = 58

    def __init__(self, text):
        super().__init__()
        self.text = text
        self.small = ""
        self.seconds = 0.0
        self.state = "waiting"
        self.running = False
        self.setFixedHeight(self.HEIGHT)

    def small_text(self, text):
        self.small = text
        self.update()

    def wait(self):
        self.state, self.running = "waiting", False
        self.seconds = 0.0
        self.update()

    def begin(self):
        self.state, self.running, self.seconds = "active", True, 0.0
        self.update()

    def done(self):
        self.state, self.running = "done", False
        self.update()

    def stopped(self):
        self.state, self.running = "stopped", False
        self.update()

    def tick(self, dt):
        if self.running:
            self.seconds += dt
            if int(self.seconds * 10) % 10 == 0:
                self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        colour = {"waiting": Staff.BONE_FAINT, "active": Staff.GOLD, "done": Staff.GOLD,
                  "stopped": Staff.WARN}[self.state]
        name_font = font(15)
        fm = QFontMetrics(name_font)

        # the diamond centred on the name's capitals. launcher/Staff.cs puts it at y = 7 with the name beside it, but a
        # WPF TextBlock is tight around the glyphs and a Qt baseline sits lower, so the centre comes from the metrics
        centre = 8 + fm.ascent() - fm.capHeight() / 2
        p.save()
        p.translate(3 + 4.5, centre)
        p.rotate(45)
        p.setPen(QPen(QColor(colour), 1.4))
        p.setBrush(QColor(colour) if self.state in ("done", "stopped") else Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(-4.5, -4.5, 9, 9))
        p.restore()

        # the name, then the line under it
        p.setFont(name_font)
        p.setPen(QColor(Staff.BONE if self.state != "waiting" else Staff.BONE_FAINT))
        p.drawText(QPointF(30, 8 + fm.ascent()), self.text)
        if self.small:
            small_font = font(12)
            fm2 = QFontMetrics(small_font)
            p.setFont(small_font)
            p.setPen(QColor(Staff.BONE_FAINT))
            p.drawText(QPointF(30, 8 + fm.ascent() + 5 + fm2.ascent()), self.small)

        # the clock on the right
        if self.state != "waiting":
            p.setFont(name_font)
            p.setPen(QColor(Staff.BONE if self.state == "active" else Staff.BONE_FAINT))
            p.drawText(QRectF(0, 8, self.width() - 6, fm.height()),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                       "%d:%02d" % (int(self.seconds // 60), int(self.seconds % 60)))
        p.end()


def _why(text):
    """launcher/Install.cs's Why: the tools' own words, keeping the build ids."""
    m = re.search(r"^This is build (\w+)\. \w+ supports build (\w+)\.$", text.strip())
    if m:
        return "This is build %s of the game; ReLink needs build %s." % (m.group(1), m.group(2))
    return text


def time_left(seconds):
    """The launcher's own wording (launcher/Install.cs: TimeLeft), with its tail."""
    tail = " Your PC stays usable."
    if seconds < 0:
        return "Allow 10 to 45 minutes in all." + tail
    minutes = int(round(seconds / 60.0))
    if minutes >= 60:
        return "About %d h %d min left.%s" % (minutes // 60, minutes % 60, tail)
    return "About %d minute%s left.%s" % (minutes, "" if minutes == 1 else "s", tail)


class FileRow(QWidget):
    """One .nup found on this PC, as launcher/App.xaml's FileRow: a hairline under it, the launcher's warm text, a gold
    bar down its left side when it is the one chosen, and on the right whether the game inside it is the version ReLink
    can build. Clicking it chooses it."""

    RULE = "#22EFE6D0"
    HOVER = "#10EFE6D0"
    CHOSEN = "#16EFE6D0"
    GOOD = "#8FD09A"     # (launcher/Install.cs's own green for a supported copy)

    def __init__(self, dump, on_click):
        super().__init__()
        self.path = dump["path"]
        self.where = dump["where"]
        self.size = dump["size"]
        self.modified = dump["modified"]
        self.state = "checking"      # checking / ok / bad / unreadable
        self.why = ""
        self.chosen = False
        self.hover = False
        self.on_click = on_click
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(76 if self.why else 58)

    def set_state(self, state, why=""):
        self.state, self.why = state, why
        self.setFixedHeight(76 if why else 58)
        self.update()

    def set_chosen(self, chosen):
        self.chosen = chosen
        self.update()

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        self.update()

    def mousePressEvent(self, e):
        self.on_click(self)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # the ground, the hairline under it, and the gold bar of the chosen one
        if self.chosen:
            p.fillRect(self.rect(), QColor(self.CHOSEN))
            p.fillRect(QRectF(0, 2, 3, h - 4), QColor(Staff.GOLD))
        elif self.hover:
            p.fillRect(self.rect(), QColor(self.HOVER))
        p.setPen(QPen(QColor(self.RULE), 1))
        p.drawLine(QPointF(0, h - 0.5), QPointF(w, h - 0.5))

        # the name, and where it came from
        name_font = font(15)
        fm = QFontMetrics(name_font)
        p.setFont(name_font)
        p.setPen(QColor(Staff.BONE))
        p.drawText(QPointF(14, 10 + fm.ascent()), os.path.basename(self.path))
        small = font(12)
        fm2 = QFontMetrics(small)
        p.setFont(small)
        p.setPen(QColor(Staff.BONE_FAINT))
        meta = "%s, %s, %s" % (self.where, finder.size_text(self.size), finder.ago(self.modified))
        p.drawText(QPointF(14, 10 + fm.ascent() + 3 + fm2.ascent()), meta)
        if self.why:
            p.setPen(QColor(Staff.WARN))
            p.drawText(QPointF(14, 10 + fm.ascent() + 3 + fm2.ascent() + 3 + fm2.ascent()), self.why)

        # and, on the right, what the game inside it is
        state, colour = {
            "checking": ("Checking…", Staff.BONE_FAINT),
            "ok": ("Supported version", self.GOOD),
            "bad": ("Not the supported version", Staff.WARN),
            "unreadable": ("Can't be read", Staff.WARN),
        }[self.state]
        p.setFont(font(13))
        p.setPen(QColor(colour))
        p.drawText(QRectF(0, 10, w - 6, fm.height()),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, state)
        p.end()


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.proc = None
        self.q = queue.Queue()
        self.src = "nup"
        self.nup = ""
        self.romfs = ""
        self.exefs = ""
        self.out = ""
        self.stage_id = None
        self.log_shown = False
        self.dump_q = queue.Queue()      # (the search's finds, from its thread)
        self.check_q = queue.Queue()     # (each file's build id, from the check's thread)
        self.space_q = queue.Queue()     # (the free space under the install folder)
        self.probe = os.path.join(tempfile.gettempdir(), "relink-probe")
        self.files_changed = -1
        self.files_of = 0
        self.files_compiled = 0
        self.hour = scene.hour_now()

        self.setWindowTitle("ReLink — Ocarina of Time (Switch 2)")
        self.setMinimumSize(980, 660)   # (30 + 424 + 50 + 419 + 30: nothing can overflow)
        self.resize(1120, 700)   # (the launcher's own size: the backdrop is drawn for it, at 1:1)

        page = QHBoxLayout(self)
        page.setContentsMargins(30, 24, 30, 24)
        page.setSpacing(50)

        # ================= the left column, on the sky =================
        col = QWidget()
        col.setFixedWidth(Staff.WIDTH)
        col.setMaximumWidth(Staff.WIDTH)
        left = QVBoxLayout(col)
        left.setSpacing(0)
        left.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Project ReLink")
        title.setFont(display(38))
        title.setStyleSheet("color: %s; background: transparent;" % css(C["Ink"]))
        left.addWidget(title)
        left.addWidget(label("Ocarina of Time, rebuilt for Linux", 13, QFont.Weight.Normal, "InkSoft"))
        # ---- what it will build from, above the staff ----
        self.rows_box = QWidget()
        above = QVBoxLayout(self.rows_box)
        above.setContentsMargins(0, 0, 0, 0)
        above.setSpacing(0)
        self.rows = {}
        for key, name in (("copy", "YOUR COPY"), ("out", "BUILT IN"), ("lang", "LANGUAGE")):
            above.addWidget(label(name, 10, T.W_SEMIBOLD, "InkFaint"))
            value = label("—", 13, QFont.Weight.Normal, "Ink")
            value.setWordWrap(True)
            above.addWidget(value)
            above.addSpacing(14)
            self.rows[key] = value
        left.addStretch(2)
        left.addWidget(self.rows_box)
        left.addSpacing(18)

        # the launcher's staff: one note per step of the build, right under what it will build from
        self.staff = Staff([("read", "Read"), ("lift", "Translate"), ("compile", "Compile"), ("finish", "Assemble")])
        left.addWidget(self.staff, 0, Qt.AlignmentFlag.AlignLeft)
        left.addStretch(3)

        # ---- the button, under the staff ----
        self.idle_box = QWidget()
        idle = QVBoxLayout(self.idle_box)
        idle.setContentsMargins(0, 0, 0, 0)
        idle.setSpacing(0)
        self.go = Button("Install", "go")
        self.go.setFixedWidth(300)
        self.go.clicked.connect(self.go_clicked)
        self.go.setEnabled(False)
        idle.addWidget(self.go)
        idle.addSpacing(10)
        self.state = label("Choose your copy and where to build it.", 12, QFont.Weight.Normal, "InkSoft", wrap=True)
        self.state.setFixedWidth(300)
        idle.addWidget(self.state)
        left.addWidget(self.idle_box)

        # ---- during the build: the launcher's own big percentage and its note ----
        self.build_box = QWidget()
        running = QVBoxLayout(self.build_box)
        running.setContentsMargins(0, 0, 0, 0)
        running.setSpacing(0)
        self.percent = QLabel("0 %")
        self.percent.setFont(display(58))
        self.percent.setStyleSheet("color: %s; background: transparent;" % css(C["Ink"]))
        running.addWidget(self.percent)
        self.note = label("", 14, QFont.Weight.Normal, "InkSoft", wrap=True)
        self.note.setFixedWidth(Staff.WIDTH)
        running.addWidget(self.note)
        self.build_box.hide()
        left.addWidget(self.build_box)


        left.addSpacing(12)
        foot = self.foot = QHBoxLayout()
        foot.setSpacing(8)
        self.version = label(updates.version(HERE) or "dev", 12, QFont.Weight.Normal, "InkFaint")
        foot.addWidget(self.version)
        self.update_chip = None
        foot.addStretch(1)
        left.addLayout(foot)
        left.addSpacing(6)

        self.folder = Button("Game folder", "link")
        self.folder.clicked.connect(self.open_folder)
        self.folder.setEnabled(False)
        left.addWidget(self.folder, 0, Qt.AlignmentFlag.AlignLeft)

        page.addWidget(col, 1)

        # ================= the panel: the settings, then the build's own steps =================
        panel = self.panel = QFrame()
        panel.setObjectName("panel")
        panel.setMinimumWidth(419)   # (its own minimumSizeHint: below that its rows clip)
        panel.setStyleSheet("#panel { background: #142219; border: 1px solid #26382D; border-radius: 14px; }")
        v = QVBoxLayout(panel)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(10)

        self.pages = QStackedWidget()

        # ---- page 0: what to build from ----
        setup = QWidget()
        s0 = QVBoxLayout(setup)
        s0.setContentsMargins(0, 0, 0, 0)
        s0.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(10)
        setup_title = QLabel("Install the game")
        setup_title.setFont(display(27))          # (the same serif and size as "Installing the game")
        setup_title.setStyleSheet("color: %s; background: transparent;" % css(C["Ink"]))
        head.addWidget(setup_title, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addStretch(1)
        head.addWidget(Chip("built from your own copy", "Go", "GoSoft"), 0, Qt.AlignmentFlag.AlignVCenter)
        s0.addLayout(head)
        s0.addWidget(label("ReLink builds the game on this PC from your own copy. It happens once and takes 10 to 45 "
                           "minutes.", 14, QFont.Weight.Normal, "InkSoft", wrap=True))
        s0.addWidget(hairline())

        # ---- 1. the game: the .nup files found on this PC, as the launcher lists them ----
        s0.addWidget(label("YOUR COPY OF THE GAME", 10, T.W_SEMIBOLD, Staff.BONE_FAINT))
        self.dumps_hint = label("Looking for .nup files…", 12, QFont.Weight.Normal, Staff.BONE_FAINT)
        s0.addWidget(self.dumps_hint)

        self.dumps_box = QWidget()
        self.dumps_list = QVBoxLayout(self.dumps_box)
        self.dumps_list.setContentsMargins(0, 2, 0, 2)
        self.dumps_list.setSpacing(0)
        s0.addWidget(self.dumps_box)
        self.rows_by_path = {}
        self.pending = []          # (the search's finds, before they are identified)
        self.others = 0            # (how many .nup files were another game)

        # (the folders, when the player has them, sit where the launcher puts its note)
        self.others_note = label("", 12, QFont.Weight.Normal, Staff.BONE_FAINT)
        self.others_note.hide()
        s0.addWidget(self.others_note)

        self.folders_row = label("", 12, QFont.Weight.Normal, Staff.BONE)
        self.folders_row.setWordWrap(True)
        self.folders_row.hide()
        s0.addWidget(self.folders_row)

        # (always there, whatever the search did or could not do)
        links = QHBoxLayout()
        links.setSpacing(22)
        choose_nup = Button("Choose a .nup file…", "link")
        choose_nup.clicked.connect(self.pick_nup)
        links.addWidget(choose_nup)
        choose_dirs = Button("Choose the romfs and exefs folders…", "link")
        choose_dirs.clicked.connect(self.pick_dirs)
        links.addWidget(choose_dirs)
        links.addStretch(1)
        s0.addLayout(links)

        s0.addWidget(hairline())

        # ---- 2. where ----
        s0.addWidget(label("INSTALL FOLDER", 10, T.W_SEMIBOLD, Staff.BONE_FAINT))
        row = QHBoxLayout()
        row.setSpacing(10)
        self.edit_out = PathEdit()
        self.edit_out.setReadOnly(True)
        self.edit_out.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.edit_out.setPlaceholderText("none chosen")
        row.addWidget(self.edit_out, 1)
        b = Button("Change…", "quiet")
        b.clicked.connect(self.pick_out)
        row.addWidget(b)
        s0.addLayout(row)
        self.space_note = label("", 12, QFont.Weight.Normal, Staff.BONE_FAINT, wrap=True)
        s0.addWidget(self.space_note)

        s0.addWidget(hairline())

        # ---- 3. language ----
        s0.addWidget(label("THE GAME'S LANGUAGE", 10, T.W_SEMIBOLD, Staff.BONE_FAINT))
        row = QHBoxLayout()
        row.setSpacing(10)
        self.lang = Choice()
        self.lang.addItems(["%s — %s" % (c, n) for c, n in LANGUAGES])
        self.lang.setCurrentIndex(2)
        self.lang.setFixedWidth(300)
        self.lang.currentIndexChanged.connect(self.refresh)
        row.addWidget(self.lang)
        row.addStretch(1)
        s0.addLayout(row)
        s0.addStretch(1)
        self.pages.addWidget(setup)

        # ---- page 1: the build, as the launcher's install page ----
        running = QWidget()
        s1 = QVBoxLayout(running)
        s1.setContentsMargins(0, 0, 0, 0)
        s1.setSpacing(0)
        self.build_title = QLabel("Installing the game")
        self.build_title.setFont(display(27))
        self.build_title.setStyleSheet("color: %s; background: transparent;" % css(C["Ink"]))
        s1.addWidget(self.build_title)
        self.build_sub = label("", 14, QFont.Weight.Normal, "InkSoft")
        self.build_sub.setContentsMargins(0, 6, 0, 14)
        s1.addWidget(self.build_sub)
        self.step_rows = {}
        for ident, text in (("read", "Read your game files"), ("lift", "Translate the game to PC code"),
                            ("compile", "Compile"), ("finish", "Put the game together")):
            step = StepRow(text)
            self.step_rows[ident] = step
            s1.addWidget(step)
        s1.addStretch(1)
        self.pages.addWidget(running)

        v.addWidget(self.pages, 0)

        # ---- the builder's own output, behind "Show details" while it runs ----
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(font(12, family=T.MONO))
        self.log.setStyleSheet(
            "QPlainTextEdit { color: %s; background: rgba(0,0,0,26); border: 1px solid rgba(255,255,255,18);"
            " border-radius: 8px; padding: 10px; selection-background-color: %s; }"
            "QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }"
            "QScrollBar::handle:vertical { background: rgba(255,255,255,40); border-radius: 3px; min-height: 24px; }"
            "QScrollBar::handle:vertical:hover { background: rgba(255,255,255,70); }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
            % (css(C["InkSoft"]), css(C["Brand"])))
        self.log.setMinimumHeight(150)
        self.log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        v.addWidget(self.log, 1)

        links = QHBoxLayout()
        links.setSpacing(22)
        self.details = Button("Show details", "link")
        self.details.clicked.connect(self.toggle_log)
        links.addWidget(self.details)
        self.cancel_link = Button("Cancel", "link")
        self.cancel_link.clicked.connect(self.cancel)
        links.addWidget(self.cancel_link)
        links.addStretch(1)
        v.addLayout(links)
        self.details.hide()
        self.cancel_link.hide()

        page.addWidget(panel, 1)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)   # (nothing is focused on open: no ring on a button nobody asked for)
        self.setFocus()
        self.load_choices()
        self.show_page(0)   # (the setup page's own state: output closed, Cancel absent)
        self.refresh()
        self.start_search()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(100)

        # the update offer: asked for once, in the background, and shown only if there is a newer release
        updates.check(HERE, self.offer_update)

    # ---- drawing ----
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        scene.draw(p, self.width(), self.height(), self.hour)
        # (a scrim on the left only: the title and the status rows sit on the sky, and at dawn the horizon is bright
        #  enough to swallow white text. The panel is opaque, so the right side needs nothing)
        g = QLinearGradient(0, 0, self.width() * 0.62, 0)
        g.setColorAt(0.0, QColor(8, 10, 14, 120))
        g.setColorAt(0.55, QColor(8, 10, 14, 55))
        g.setColorAt(1.0, QColor(8, 10, 14, 0))
        p.fillRect(self.rect(), g)
        p.end()

    # ---- the two pages ----
    def show_page(self, index):
        """0: what to build from. 1: the build."""
        self.staff.set_items([("read", "Read"), ("lift", "Translate"), ("compile", "Compile"),
                              ("finish", "Assemble")])
        self.staff.set(0.0)
        self.pages.setCurrentIndex(index)
        building = index == 1
        # (the three rows stay: they say what is being installed while it installs, as the launcher's build page does)
        self.idle_box.setVisible(not building)
        self.build_box.setVisible(building)
        self.details.setVisible(True)              # ("Show details" is offered on both pages)
        self.cancel_link.setVisible(building)      # (Cancel only means something while a build runs)
        self.log.setVisible(self.log_shown)        # (closed until asked for: it took the whole page)

    def toggle_log(self):
        self.log_shown = not self.log_shown
        self.log.setVisible(self.log_shown)
        self.details.setText("Hide details" if self.log_shown else "Show details")

    # ---- the progress ----
    def progress(self, v):
        """The build's progress, 0 to 1: the staff fills and the big percentage says where it is."""
        v = max(0.0, min(1.0, v))
        self.staff.set(v)
        self.percent.setText("%d %%" % round(v * 100))

    def set_stage(self, step):
        """A step begins: the one before it is done, on the page and on the staff (launcher/Install.cs: Stage)."""
        self.stage_id = step
        order = list(self.step_rows)
        for ident, row in self.step_rows.items():
            if ident == step:
                row.begin()
            elif ident in order and step in order and order.index(ident) < order.index(step):
                row.done()
            else:
                row.wait()
        self.staff.set_stage(step)

    def compile_small(self):
        row = self.step_rows.get("compile")
        if row is None or self.files_changed < 0:
            return
        if self.files_changed == 0:
            row.small_text("Everything is already built")
        elif self.files_changed >= self.files_of:
            row.small_text("%d of %d files" % (self.files_compiled, self.files_changed))
        else:
            row.small_text("%d of %d changed files" % (self.files_compiled, self.files_changed))

    # ---- what the player chose last time (launcher/Storage.cs) ----
    def load_choices(self):
        """The .nup, the folder and the language of the last run. A file that cannot be read is simply no memory."""
        try:
            with open(CHOICES, encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(saved, dict):
            return
        self.nup = saved.get("nup") or ""
        self.romfs = saved.get("romfs") or ""
        self.exefs = saved.get("exefs") or ""
        self.out = saved.get("out") or ""
        self.src = "folders" if (self.romfs and self.exefs and not self.nup) else "nup"
        code = saved.get("language") or ""
        for i, (lang, _name) in enumerate(LANGUAGES):
            if lang == code:
                self.lang.setCurrentIndex(i)
                break
        if self.out:
            self.edit_out.setText(self.out)
            self.edit_out.setCursorPosition(0)
        if self.romfs and self.exefs:
            self.folders_row.setText("The romfs and exefs folders: %s   +   %s" % (self.romfs, self.exefs))
            self.folders_row.show()

    def save_choices(self):
        try:
            os.makedirs(os.path.dirname(CHOICES), exist_ok=True)
            with open(CHOICES, "w", encoding="utf-8") as f:
                json.dump({"nup": self.nup, "romfs": self.romfs, "exefs": self.exefs, "out": self.out,
                           "language": self.lang.currentText().split(" ")[0]}, f)
        except OSError:
            pass

    # ---- the player's copy ----
    def start_search(self):
        """Look for .nup files in the background and check each one's build id as it turns up.

        Nothing here may fail in the player's face: a machine where the search cannot run just shows the hint and the
        two "choose" links."""
        if not finder.enabled():
            self.dumps_hint.setText("Choose your .nup below.")
            return
        threading.Thread(target=self._search, daemon=True).start()

    def _search(self):
        try:
            def found(dump):
                self.dump_q.put(dump)
            finder.find_dumps(on_found=found)
        except Exception:
            pass
        finally:
            self.dump_q.put(None)   # (the walk is over, whatever happened)

    def _check_one(self, path):
        """Ask make_game.py what build is inside one file: about two seconds, only its exefs is unpacked."""
        if not os.access(PY, os.X_OK) or not os.path.isfile(MK):
            return "unreadable", ""
        try:
            r = subprocess.run([PY, "-I", MK, "--check", "--nup", path, "--work", self.probe],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        except (OSError, subprocess.SubprocessError):
            return "unreadable", ""
        for line in (r.stdout or "").splitlines():
            if line.startswith("@@check "):
                _, _, rest = line.partition(" ")
                verdict, _, text = rest.partition(" ")
                if verdict == "ok":
                    return "ok", ""
                if verdict == "bad":
                    return "bad", _why(text)
        return "unreadable", ""

    def _identify_thread(self, dumps):
        """Which of the found files are this game, then which of those is the build ReLink can use.

        The title id comes from the .nup's own table of contents, so a file called anything at all is judged on what is
        inside it. Files of other games are counted, not listed."""
        for dump in dumps:
            ids = finder.title_ids(dump["path"])
            if ids is not None and OOT_TITLE not in ids:
                self.check_q.put(("other", None, "", ""))
                continue
            self.check_q.put(("add", dump, "", ""))
            state, why = self._check_one(dump["path"])
            self.check_q.put(("state", dump["path"], state, why))
        self.check_q.put(None)

    def _check_thread(self, paths):
        for path in paths:
            state, why = self._check_one(path)
            self.check_q.put(("state", path, state, why))
        self.check_q.put(None)

    def finish_search(self):
        """The list is complete: say what was found, and what was left out."""
        if self.rows_by_path:
            self.dumps_hint.hide()
        elif self.others:
            self.dumps_hint.setText("No copy of this game found: %d other .nup file%s here %s not it. Choose yours below."
                                    % (self.others, "" if self.others == 1 else "s",
                                       "is" if self.others == 1 else "are"))
        else:
            self.dumps_hint.setText("No .nup file found in Downloads, Desktop, Documents or the disks. "
                                    "Choose yours below.")
        if self.others and self.rows_by_path:
            self.others_note.setText("%d other .nup file%s found %s not this game."
                                     % (self.others, "" if self.others == 1 else "s",
                                        "is" if self.others == 1 else "are"))
            self.others_note.show()

    def add_dump(self, dump):
        row = FileRow(dump, self.select_row)
        self.rows_by_path[dump["path"]] = row
        self.dumps_list.addWidget(row)
        self.dumps_hint.hide()

    def select_row(self, row):
        self.nup = row.path
        self.romfs = self.exefs = ""
        self.folders_row.hide()
        self.src = "nup"
        self.mark_chosen()
        self.save_choices()
        self.refresh()

    def mark_chosen(self):
        for path, row in self.rows_by_path.items():
            row.set_chosen(self.src == "nup" and path == self.nup)

    def pick_nup(self):
        p, _ = QFileDialog.getOpenFileName(self, "Your .nup file", os.path.expanduser("~"),
                                          "Game dump (*.nup);;All files (*)")
        if not p:
            return
        self.nup, self.romfs, self.exefs, self.src = p, "", "", "nup"
        if p in self.rows_by_path:                 # (a file the search did not reach: give it a row of its own)
            self.mark_chosen()
        else:
            try:
                stat = os.stat(p)
                dump = {"path": p, "where": "Chosen", "size": stat.st_size, "modified": stat.st_mtime}
            except OSError:
                dump = {"path": p, "where": "Chosen", "size": 0, "modified": 0}
            self.add_dump(dump)
            self.rows_by_path[p].set_state("checking")
            threading.Thread(target=self._check_thread, args=([p],), daemon=True).start()
            self.rows_by_path[p].set_chosen(True)
        self.folders_row.hide()
        self.save_choices()
        self.refresh()

    def pick_dirs(self):
        p = QFileDialog.getExistingDirectory(self, "The romfs folder", os.path.expanduser("~"))
        if not p:
            return
        q = QFileDialog.getExistingDirectory(self, "The exefs folder", os.path.expanduser("~"))
        if not q:
            return
        self.romfs, self.exefs, self.src = p, q, "folders"
        self.folders_row.setText("The romfs and exefs folders: %s   +   %s" % (self.romfs, self.exefs))
        self.folders_row.show()
        self.mark_chosen()
        self.save_choices()
        self.refresh()

    def pick_out(self):
        p = QFileDialog.getExistingDirectory(self, "Where the game is built (a ReLink folder is made inside)",
                                             os.path.expanduser("~"))
        if p:
            self.out = os.path.join(p, "ReLink")
            self.edit_out.setText(self.out)
            self.edit_out.setCursorPosition(0)
            threading.Thread(target=self._free_space, daemon=True).start()
            self.save_choices()
            self.refresh()

    def _free_space(self):
        try:
            os.makedirs(self.out, exist_ok=True)
            free = shutil.disk_usage(self.out).free
            self.space_q.put("The install needs 6 GB free while it works; %s has %s."
                             % (self.out, finder.size_text(free)))
        except OSError:
            self.space_q.put("")

    def play_game(self):
        game = os.path.join(self.out or "", "relink")
        if not os.access(game, os.X_OK):
            QMessageBox.information(self, "ReLink", "There is no game in %s yet." % (self.out or "that folder"))
            return
        # The builder's own variables are dropped: the built game loads relink_vk.so and libSDL2-2.0.so.0 from beside
        # itself, and an LD_LIBRARY_PATH, APPDIR or PYTHON* left over from the AppImage can make it pick the image's
        # copies instead. The same list the Longshot builder's longshot-launch drops.
        env = {k: v for k, v in os.environ.items()
               if not (k.startswith(("RELINK_", "PYTHON", "APPDIR", "APPIMAGE", "ARGV0", "OWD")) or k == "LD_LIBRARY_PATH")}
        env["RELINK_NO_UPDATE_CHECK"] = "1"
        try:
            subprocess.Popen([game], cwd=self.out, env=env)
        except OSError as error:
            QMessageBox.critical(self, "ReLink", "Cannot start the game:\n\n%s" % error)

    def open_folder(self):
        if self.out and os.path.isdir(self.out):
            subprocess.Popen(["xdg-open", self.out])

    def game_version(self):
        """The version the game in the folder was built with (relink_version.txt, written by make_game.py)."""
        try:
            with open(os.path.join(self.out, "relink_version.txt"), encoding="utf-8") as f:
                for line in f:
                    if line.startswith("version="):
                        return line.split("=", 1)[1].strip()
        except OSError:
            pass
        return ""

    def up_to_date(self):
        """The game in the folder was built by THIS AppImage.

        A new AppImage carries a new version, so its game folder's relink_version.txt no longer matches: the button
        says Install again and the build updates the game. That is the whole point of comparing them."""
        mine = updates.version(HERE)
        return bool(mine) and mine != "dev" and self.game_version() == mine

    def go_clicked(self):
        if self.up_to_date():
            self.play_game()
        else:
            self.start()

    def ready(self):
        if self.up_to_date():
            return os.access(os.path.join(self.out, "relink"), os.X_OK)
        have = bool(self.nup) if self.src == "nup" else bool(self.romfs and self.exefs)
        return have and bool(self.out)

    def refresh(self):
        self.go.setText("Play" if self.up_to_date() else "Install")
        self.go.setEnabled(self.ready() and not self.proc)
        self.folder.setEnabled(bool(self.out) and os.path.isdir(self.out))
        self.rows["copy"].setText(os.path.basename(self.nup) if self.src == "nup" and self.nup
                                  else (os.path.basename(self.romfs) + " + " + os.path.basename(self.exefs)
                                        if self.src == "folders" and self.romfs and self.exefs else "—"))
        self.rows["out"].setText(self.out or "—")
        self.rows["lang"].setText(self.lang.currentText().split(" — ")[-1])
        if self.proc:
            return
        missing = []
        if self.src == "nup" and not self.nup:
            missing.append("your .nup")
        if self.src == "folders" and not (self.romfs and self.exefs):
            missing.append("the romfs and exefs folders")
        if not self.out:
            missing.append("where to build")
        if self.up_to_date():
            self.state.setText("Built with %s, this version." % self.game_version())
        elif missing:
            self.state.setText("Choose " + ", ".join(missing) + ".")
        elif self.game_version():
            self.state.setText("Built with %s; this is %s. Install to update it."
                               % (self.game_version(), updates.version(HERE)))
        else:
            self.state.setText("Ready.")

    # ---- the update offer ----
    def offer_update(self, tag, page):
        # (called from the check's thread: hand it to the window's own thread)
        QTimer.singleShot(0, lambda: self._show_update(tag, page))

    def _show_update(self, tag, page):
        if self.update_chip is not None:
            return
        self.update_chip = LinkChip("%s available" % tag, "Warn", "WarnSoft", page)
        self.update_chip.setToolTip("Open the release page")
        self.foot.insertWidget(1, self.update_chip)

    # ---- the build ----
    def start(self):
        # (Qt prints an exception from a slot and carries on, so a broken start left a window whose button did nothing
        #  at all: v0.7.6 did exactly that. Whatever goes wrong is now said out loud.)
        try:
            self._start()
        except Exception as error:
            QMessageBox.critical(self, "ReLink", "Cannot start the build:\n\n%s: %s" % (type(error).__name__, error))
            raise

    def _start(self):
        args = [PY, "-I", MK, "--out", self.out, "--language", self.lang.currentText().split(" ")[0]]
        if self.src == "nup":
            args += ["--nup", self.nup]
        else:
            args += ["--romfs", self.romfs, "--exefs", self.exefs]
        self.log_path = os.path.join(self.out, "build.log")
        os.makedirs(self.out, exist_ok=True)
        args += ["--log", self.log_path]
        self.write("$ " + " ".join(args) + "\n\n", "InkFaint")

        # (the launcher's build page: every step waiting, the log behind "Show details")
        self.stage_id = None
        self.files_changed, self.files_of, self.files_compiled = -1, 0, 0
        for row in self.step_rows.values():
            row.wait()
            row.small_text("")
        self.build_sub.setText(self.out)
        self.log_shown = False
        self.details.setText("Show details")
        self.progress(0)
        self.note.setText(time_left(-1))
        self.show_page(1)
        self.go.setEnabled(False)
        self.cancel_link.setEnabled(True)

        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace", bufsize=1, env=env, cwd=HERE)
        threading.Thread(target=self.read, args=(self.proc,), daemon=True).start()

    def read(self, proc):
        for line in proc.stdout:
            self.q.put(line)
        self.q.put(None)

    def write(self, text, color=None):
        cur = QTextCursor(self.log.document())
        cur.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(C[color] if color else C["InkSoft"])
        cur.insertText(text, fmt)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def on_tick(self):
        self.drain()
        self.drain_search()
        if self.proc:
            for row in self.step_rows.values():
                row.tick(0.1)

    def drain_search(self):
        """The search's finds, then each file's build id, then the free space: all from their own threads."""
        try:
            while True:
                dump = self.dump_q.get_nowait()
                if dump is None:
                    self.dumps_hint.setText("Looking inside them…")
                    threading.Thread(target=self._identify_thread, args=(self.pending,), daemon=True).start()
                    break
                self.pending.append(dump)
        except queue.Empty:
            pass
        try:
            while True:
                item = self.check_q.get_nowait()
                if item is None:
                    self.finish_search()
                    break
                kind, payload, state, why = item
                if kind == "other":
                    self.others += 1
                    continue
                if kind == "add":
                    self.add_dump(payload)
                    continue
                path = payload
                if path in self.rows_by_path:
                    self.rows_by_path[path].set_state(state, why)
                # (the first copy that checks out is the one chosen, as the launcher does: the player can click another)
                if state == "ok" and not self.nup and self.src == "nup":
                    self.select_row(self.rows_by_path[path])
        except queue.Empty:
            pass
        try:
            while True:
                note = self.space_q.get_nowait()
                self.space_note.setText(note)
        except queue.Empty:
            pass

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
                        # (a step's 0..1 mapped into its share of the whole build: the launcher does the same, so the
                        #  bar never jumps back to 0 when a step begins)
                        lo, size = STAGE_WEIGHT.get(self.stage_id or "", (0.0, 1.0))
                        try:
                            self.progress(lo + size * float(rest))
                        except ValueError:
                            pass
                    elif kind == "stage":
                        step, _, text = rest.partition(" ")
                        self.set_stage(step)
                        self.write("\n== " + text + " ==\n", "Go")
                    elif kind == "eta":
                        try:
                            self.note.setText(time_left(float(rest)))
                        except ValueError:
                            pass
                    elif kind == "plan":
                        parts = rest.split()
                        if len(parts) == 2:
                            self.files_changed, self.files_of = int(parts[0]), int(parts[1])
                            self.files_compiled = 0
                            self.compile_small()
                    elif kind == "file":
                        parts = rest.split()
                        if len(parts) == 3 and parts[2] in ("new", "again"):
                            self.files_compiled += 1
                            self.compile_small()
                    elif kind == "error":
                        self.staff.set_problem()
                        if self.stage_id in self.step_rows:
                            self.step_rows[self.stage_id].stopped()
                        self.write("\n!! " + rest + "\n", "Bad")
                else:
                    self.write(line + "\n")
        except queue.Empty:
            pass

    def cancel(self):
        if self.proc and self.proc.poll() is None:
            if QMessageBox.question(self, "ReLink", "Stop the build?") != QMessageBox.StandardButton.Yes:
                return
            self.proc.terminate()
            self.note.setText("Stopping…")

    def done(self):
        code = self.proc.poll() if self.proc else None
        self.proc = None
        self.cancel_link.setEnabled(False)
        self.go.setEnabled(True)
        self.refresh()
        if code == 0:
            self.progress(1)
            for row in self.step_rows.values():
                row.done()
        game = os.path.join(self.out, "relink")
        if code == 0 and os.access(game, os.X_OK):
            self.write("\n== done: %s ==\n" % game, "Go")
            self.log_shown = True
            self.details.setText("Hide details")
            self.show_page(0)
            self.refresh()          # (the button becomes Play: this AppImage built it)
            if QMessageBox.question(self, "ReLink", "The game is built in\n%s\n\nPlay it now?" % self.out) == QMessageBox.StandardButton.Yes:
                self.play_game()
        else:
            if self.stage_id in self.step_rows:
                self.step_rows[self.stage_id].stopped()
            self.log_shown = True
            self.details.setText("Hide details")
            self.show_page(0)
            self.state.setText("The build did not finish.")
            QMessageBox.critical(self, "ReLink", "The build did not finish. Its log is in\n%s/build.log" % self.out)


def main():
    app = QApplication(sys.argv)
    T.load_fonts()   # (after QApplication: QFontDatabase needs it)
    w = Window()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
