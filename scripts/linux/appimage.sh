#!/bin/bash
# The Linux AppImage: ProjectReLink's builder with everything it needs to build the game on the player's PC. No game
# data and nothing made from it is in it: the game is built from the player's own copy, as on Windows.
#
#   scripts/linux/deps.sh        (first: the compiler, Python, FFmpeg, SDL2, headers into build-linux/deps)
#   scripts/linux/appimage.sh    -> build-linux/ReLink-<version>-x86_64.AppImage
#
# Built on the oldest system it is for (CI: Ubuntu 22.04): the sysroot it carries is that system's C library, so the
# game it builds runs on glibc 2.35 and newer.
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT=$PWD
B=$ROOT/build-linux
DEPS=${DEPS:-$B/deps}
APPDIR=$B/AppDir
VERSION=${RELINK_VERSION:-$(git describe --tags --always --match "v[0-9]*" 2>/dev/null || echo dev)}
export EMSDK=$DEPS/emsdk RX_CPM=$DEPS/cpm
PY=$DEPS/python/bin/python3

# ---- the Vulkan back end, built here once (it needs no game) ----
VKW=$B/vk-work
rm -rf "$VKW/sa/build/relink_vk.so"
OOT_WORK=$VKW RX_MARCH=x86-64-v3 RX_VK_ONLY=1 RX_RELEASE=1 "$PY" -I nx2/build.py --standalone --jobs "${JOBS:-$(nproc)}"
VK=$VKW/sa/build/relink_vk.so
[ -f "$VK" ] || { echo "relink_vk.so was not built"; exit 1; }

# ---- the tools' native helpers, built now: the AppImage is read-only ----
E=third_party/a64-kit/lift
"$EMSDK/upstream/bin/clang++" -std=c++20 -O2 -shared -fPIC -static-libstdc++ -static-libgcc -Wno-everything \
    -o "$E/liba64emit.so" "$E/a64emit.cpp"
"$PY" -I -c "import hashlib; f = ['$E/a64emit.cpp', '$E/suyu/arm64_to_c.h']; open('$E/liba64emit.so.sha1', 'w').write(hashlib.sha1(b''.join(open(x, 'rb').read() for x in f)).hexdigest())"
"$PY" -I third_party/a64-kit/lift/build_emit.py
"$PY" -I -c "import sys; sys.path.insert(0, 'nx2'); import zbic; zbic.lib()"

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/share/relink" "$APPDIR/usr/lib/relink"
T=$APPDIR/usr/share/relink
L=$APPDIR/usr/lib/relink

# ---- the tools (the sources the player's build compiles, and the scripts) ----
cp -a nx2 host gpu third_party tools scripts LICENSE README.md "$T/"
printf '%s\n' "$VERSION" > "$T/VERSION"
find "$T" -name __pycache__ -prune -exec rm -rf {} +
chmod +x "$T/scripts/linux/gui.sh" 2>/dev/null || true
rm -f "$T/third_party/a64-kit/tools/lld-link.exe"

# ---- what it builds with ----
cp -a "$DEPS/python" "$APPDIR/usr/python"
mkdir -p "$L/emsdk"
cp -a "$DEPS/emsdk/upstream" "$L/emsdk/"
cp -a "$DEPS/ffmpeg" "$L/ffmpeg"
cp -a "$DEPS/cpm" "$T/cpm"
cp "$VK" "$L/relink_vk.so"
cp "$DEPS/sdl2/libSDL2-2.0.so.0" "$L/libSDL2-2.0.so.0"
cp -a "$DEPS/licenses" "$T/licenses"

# the sysroot: this system's C library (headers, start files, the libraries to link against) and GCC's runtime pieces
S=$L/sysroot
mkdir -p "$S/usr/lib/x86_64-linux-gnu" "$S/usr/lib/gcc/x86_64-linux-gnu" "$S/lib64"
ln -s usr/lib "$S/lib"
cp -a /usr/include "$S/usr/"
# (the C++ headers and the static C++ runtime stay: gpu/vk's C++ is compiled on the player's PC with this sysroot)
rm -rf "$S/usr/include/llvm"* "$S/usr/include/clang"*
M=/usr/lib/x86_64-linux-gnu
for f in crt1.o crti.o crtn.o Scrt1.o rcrt1.o libc.so libc.so.6 libc_nonshared.a libm.so libm.so.6 libm.a libmvec.so libmvec.so.1 \
         libmvec.a libpthread.so.0 libpthread.a libdl.so.2 libdl.a librt.so.1 librt.a libutil.a libgcc_s.so.1 ld-linux-x86-64.so.2; do
    [ -e "$M/$f" ] && cp -aL "$M/$f" "$S/usr/lib/x86_64-linux-gnu/" || true
done
cp -aL /lib64/ld-linux-x86-64.so.2 "$S/lib64/"
GCC=$(ls -d /usr/lib/gcc/x86_64-linux-gnu/*/ | sort -V | tail -1)
G=$S/usr/lib/gcc/x86_64-linux-gnu/$(basename "$GCC")
mkdir -p "$G"
for f in crtbegin.o crtbeginS.o crtbeginT.o crtend.o crtendS.o libgcc.a libgcc_eh.a libgcc_s.so libstdc++.a libstdc++.so; do
    [ -e "$GCC/$f" ] && cp -aL "$GCC/$f" "$G/" || true
done

# ---- check: the bundled compiler builds and links a program against the sysroot, and it runs ----
cat > "$B/t.c" <<'CEOF'
#include <pthread.h>
#include <stdio.h>
#include <math.h>
static void *f(void *p) { return p; }
int main(void) { pthread_t t; pthread_create(&t, 0, f, 0); pthread_join(t, 0); printf("ok %g\n", sqrt(2.0)); return 0; }
CEOF
"$L/emsdk/upstream/bin/clang" --sysroot="$S" -fuse-ld=lld -O2 -march=x86-64-v3 "$B/t.c" -o "$B/t" -lpthread -lm
"$B/t"

# ---- the AppDir's own files ----
cat > "$APPDIR/AppRun" <<'AEOF'
#!/bin/bash
HERE=$(dirname "$(readlink -f "$0")")
export EMSDK="$HERE/usr/lib/relink/emsdk"
export RELINK_SYSROOT="$HERE/usr/lib/relink/sysroot"
export RX_CPM="$HERE/usr/share/relink/cpm"
export RELINK_FFMPEG="$HERE/usr/lib/relink/ffmpeg"
export RELINK_SDL2="$HERE/usr/lib/relink/libSDL2-2.0.so.0"
export RELINK_VK_PREBUILT="$HERE/usr/lib/relink/relink_vk.so"
export PATH="$EMSDK/upstream/bin:$PATH"
# (no argument: the window, scripts/linux/gui.sh; any argument: make_game.py as it is)
if [ $# -eq 0 ]; then
    exec "$HERE/usr/share/relink/scripts/linux/gui.sh"
fi
exec "$HERE/usr/python/bin/python3" -I "$HERE/usr/share/relink/nx2/make_game.py" "$@"
AEOF
chmod +x "$APPDIR/AppRun"
cat > "$APPDIR/relink.desktop" <<'DEOF'
[Desktop Entry]
Type=Application
Name=ReLink
Comment=Build The Legend of Zelda: Ocarina of Time (Switch 2) from your own copy
Exec=AppRun
Icon=relink
Categories=Game;
Terminal=false
DEOF
cp assets/relink.png "$APPDIR/relink.png"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp assets/relink.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/relink.png"

OUT=$B/ReLink-$VERSION-x86_64.AppImage
rm -f "$OUT"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$DEPS/appimagetool" --runtime-file "$DEPS/runtime-x86_64" --comp zstd "$APPDIR" "$OUT"
echo "$OUT: $(du -h "$OUT" | cut -f1)"
