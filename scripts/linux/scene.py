"""ProjectReLink's own backdrop, carried over: the sky behind the launcher, keyed to the hour.

A port of `launcher/Scene.cs` from ProjectReLink (GPL-3.0-or-later, the same as this tree): the same eight keyframes of
sky colour, the same stars on a fixed seed, the same sun or moon on its arc, and the same three ridges, so a ReLink
window looks like a ReLink launcher at whatever time the player starts it.

    scene.draw(painter, width, height, hour)

`RELINK_HOUR=6.5` pins the hour, for tests and for comparing two renders.
"""
import datetime
import math
import os
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainterPath

# (hour, sky at the top, sky at the horizon) — Scene.cs's Keys
KEYS = [
    (0.0, "#0A1424", "#16303F"),
    (4.75, "#0A1424", "#16303F"),
    (6.25, "#26375A", "#D49A6A"),   # dawn
    (8.5, "#235A8E", "#9CCBD9"),    # day
    (16.5, "#235A8E", "#9CCBD9"),
    (18.5, "#2A2F57", "#DA8A52"),   # dusk
    (20.25, "#0A1424", "#16303F"),
    (24.0, "#0A1424", "#16303F"),
]

# the ridges, in Scene.cs's own 1120 x 700 coordinates
RIDGES = [
    ([("M", 0, 226), ("C", 120, 194, 230, 200, 330, 216), ("C", 430, 232, 520, 208, 640, 200),
      ("C", 780, 190, 900, 226, 1120, 204), ("L", 1120, 700), ("L", 0, 700), ("Z",)], "#1E3B30", 0.58, "low"),
    ([("M", 0, 262), ("C", 90, 246, 190, 234, 300, 250), ("C", 400, 264, 470, 274, 600, 262),
      ("C", 760, 246, 900, 272, 1120, 246), ("L", 1120, 700), ("L", 0, 700), ("Z",)], "#183226", 0.82, "low"),
    ([("M", 0, 292), ("C", 140, 274, 260, 284, 380, 298), ("C", 520, 314, 700, 288, 860, 294),
      ("C", 980, 298, 1060, 288, 1120, 284), ("L", 1120, 700), ("L", 0, 700), ("Z",)], "#11241B", 0.92, "top"),
]

W, H = 1120.0, 700.0   # (the launcher's own size: the ridges' numbers are in it)


def qc(hex_text):
    return QColor(hex_text)


def mix(a, b, t):
    """Scene.cs's Mix: channel by channel between two QColors."""
    return QColor(int(a.red() + (b.red() - a.red()) * t),
                  int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


def hour_now():
    """The hour this window shows the sky for: RELINK_HOUR when set, the wall clock otherwise."""
    forced = os.environ.get("RELINK_HOUR", "")
    if forced:
        try:
            return min(max(float(forced), 0.0), 23.99)
        except ValueError:
            pass
    now = datetime.datetime.now()
    return now.hour + now.minute / 60.0


def sky(hour):
    """The two colours of the sky at that hour, interpolated between the keyframes."""
    for i in range(1, len(KEYS)):
        h, top, low = KEYS[i]
        if hour <= h:
            ph, ptop, plow = KEYS[i - 1]
            t = (hour - ph) / (h - ph) if h > ph else 0.0
            return mix(qc(ptop), qc(top), t), mix(qc(plow), qc(low), t)
    return qc(KEYS[0][1]), qc(KEYS[0][2])


def _path(segments):
    p = QPainterPath()
    for seg in segments:
        op = seg[0]
        if op == "M":
            p.moveTo(QPointF(seg[1], seg[2]))
        elif op == "C":
            p.cubicTo(QPointF(seg[1], seg[2]), QPointF(seg[3], seg[4]), QPointF(seg[5], seg[6]))
        elif op == "L":
            p.lineTo(QPointF(seg[1], seg[2]))
        elif op == "Z":
            p.closeSubpath()
    return p


def draw(painter, width, height, hour=None):
    """Paint the backdrop: the sky, its stars, the sun or the moon, and the three ridges."""
    hour = hour_now() if hour is None else hour
    top, low = sky(hour)
    painter.save()
    # The whole scene is drawn in the launcher's own 1120 x 700 space, then scaled by ONE factor to this window and
    # centred: a window of another shape crops the edges rather than stretching the picture. Scaling x and y apart
    # would flatten the sun into an ellipse. At the launcher's own size the factor is 1 and nothing moves.
    k = max(width / W, height / H)
    painter.translate((width - W * k) / 2, (height - H * k) / 2)
    painter.scale(k, k)

    grad = QLinearGradient(0, 0, 0, H)
    grad.setColorAt(0.00, top)
    grad.setColorAt(0.17, top)
    grad.setColorAt(0.36, low)
    grad.setColorAt(1.00, low)
    painter.fillRect(QRectF(0, 0, W, H), QBrush(grad))

    # how much night is in this hour: the stars' light
    if hour < 5 or hour > 20.25:
        night = 1.0
    elif hour < 6.5:
        night = (6.5 - hour) / 1.5
    elif hour > 18.75:
        night = (hour - 18.75) / 1.5
    else:
        night = 0.0
    if night > 0.02:
        rnd = random.Random(1998)   # (Scene.cs's seed: the same stars every night)
        painter.setPen(Qt.PenStyle.NoPen)
        for _ in range(54):
            size = 1 + rnd.random() * 1.4
            painter.setBrush(QColor(255, 255, 255, int(255 * night * (0.3 + rnd.random() * 0.6))))
            painter.drawEllipse(QRectF(rnd.random() * W, 8 + rnd.random() * 200, size, size))

    # the sun by day, the moon by night, over the right of the left column, as high as the hour puts it
    x = 420.0
    if 5.5 < hour < 19.5:
        up = _arc((hour - 5.5) / 14.0)
        y = 206 - up * 136
        colour = mix(qc("#F2B56B"), qc("#FBF1CF"), up)
        _disc(painter, x, y, 46, colour, 0.10)
        _disc(painter, x, y, 21, colour, 1.0)
    else:
        since = hour - 19.5 if hour >= 19.5 else hour + 4.5
        up = _arc(since / 10.0)
        y = 206 - up * 136
        _disc(painter, x, y, 17, qc("#E9E6D8"), 1.0)
        _disc(painter, x + 7.5, y - 4, 15, top, 1.0)   # (the sky's own colour over it: a crescent)

    for segments, ink, t, base in RIDGES:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(mix(low if base == "low" else top, qc(ink), t))
        painter.drawPath(_path(segments))
    painter.restore()


def _arc(fraction):
    """How high the sun or the moon is on its arc, 0 at the horizon and 1 at the top (Scene.cs's Sin3)."""
    return math.sin(math.pi * max(0.0, min(1.0, fraction)))


def _disc(painter, x, y, r, colour, opacity):
    c = QColor(colour)
    c.setAlphaF(opacity)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(c)
    painter.drawEllipse(QRectF(x - r, y - r, 2 * r, 2 * r))
