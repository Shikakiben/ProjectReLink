#!/usr/bin/env python3
"""Cuts a PySide6 install down to what the window uses: QtCore, QtGui, QtWidgets, the xcb and wayland platform plugins,
and the libraries they load (ldd, followed to a fixed point). 245 MB becomes 111 MB; ICU's data (31 MB) is among what
stays, Qt's core links it. The QML stack, the designer and linguist tools, the type stubs and the translations go.

    trim_pyside.py <site-packages>/PySide6
"""
import os
import re
import subprocess
import sys

ROOTS = ("QtCore.abi3.so", "QtGui.abi3.so", "QtWidgets.abi3.so",
         "Qt/plugins/platforms/libqxcb.so", "Qt/plugins/platforms/libqwayland.so",
         "Qt/plugins/platforms/libqwayland-egl.so")

DROP = ("Qt/qml", "Qt/translations", "Qt/libexec", "Qt/metatypes", "assistant", "designer", "linguist",
        "lupdate", "qmlls", "qmlformat", "balsam", "shiboken6-genpyi")


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    for name in DROP:
        path = os.path.join(root, name)
        if os.path.isdir(path):
            subprocess.run(["rm", "-rf", path], check=False)
        elif os.path.exists(path):
            os.remove(path)
    for f in os.listdir(root):
        if f.endswith(".pyi"):
            os.remove(os.path.join(root, f))

    keep, todo = set(), [os.path.join(root, r) for r in ROOTS if os.path.exists(os.path.join(root, r))]
    while todo:
        f = todo.pop()
        if f in keep or not os.path.exists(f):
            continue
        keep.add(f)
        try:
            # (LD_LIBRARY_PATH first: without it ldd answers with the distro's own Qt, whose paths are outside the tree,
            # and the bundled libraries the plugins really load are then deleted as unreferenced)
            out = subprocess.run(["ldd", f], capture_output=True, text=True,
                                 env=dict(os.environ, LD_LIBRARY_PATH=os.path.join(root, "Qt", "lib"))).stdout
        except OSError:
            continue
        for _name, path in re.findall(r"(\S+\.so[\w.]*)\s*=>\s*(/\S+)", out):
            if path.startswith(root) and os.path.exists(path):
                todo.append(path)
    removed = 0
    lib = os.path.join(root, "Qt", "lib")
    for name in os.listdir(lib):
        path = os.path.join(lib, name)
        if path not in keep:
            os.remove(path)
            removed += 1
    total = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(root) for f in fs)
    print("trim_pyside: %d libraries left out, %.0f MB kept" % (removed, total / 1e6))


if __name__ == "__main__":
    main()
