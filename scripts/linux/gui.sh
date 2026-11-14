#!/bin/bash
# The AppImage's window: pick the game, the folder and the language, then build with a progress bar.
# Called by AppRun when it is given no argument; any argument goes to make_game.py as it is (the command line).
# zenity draws it: a desktop without zenity gets the command line's usage instead.
set -u
HERE=$(dirname "$(readlink -f "$0")")
PY="$HERE/usr/python/bin/python3"
MK="$HERE/usr/share/relink/nx2/make_game.py"

if ! command -v zenity >/dev/null 2>&1; then
    echo "ReLink: zenity is not installed, so there is no window. Run it with --help for the command line." >&2
    exec "$PY" -I "$MK" --help
fi

say() { zenity --info --title="ReLink" --width=520 --text="$1" 2>/dev/null; }
ask() { zenity --question --title="ReLink" --width=520 --text="$1" 2>/dev/null; }

# ---- 1. the game: a .nup, or the romfs and exefs folders ----
src=$(zenity --list --title="ReLink" --width=560 --height=260 \
    --text="Where is your own copy of the game?" \
    --column="Pick" --column="What it is" \
    "nup" "A .nup file" \
    "folders" "The romfs and exefs folders" 2>/dev/null) || exit 0
[ -n "$src" ] || exit 0

nup="" romfs="" exefs=""
if [ "$src" = "nup" ]; then
    nup=$(zenity --file-selection --title="ReLink: your .nup" --file-filter="*.nup" 2>/dev/null) || exit 0
    [ -n "$nup" ] || exit 0
else
    romfs=$(zenity --file-selection --directory --title="ReLink: the romfs folder" 2>/dev/null) || exit 0
    [ -n "$romfs" ] || exit 0
    exefs=$(zenity --file-selection --directory --title="ReLink: the exefs folder" 2>/dev/null) || exit 0
    [ -n "$exefs" ] || exit 0
fi

# ---- 2. where the game goes ----
out=$(zenity --file-selection --directory --title="ReLink: where to build the game" \
    --filename="$HOME/" 2>/dev/null) || exit 0
[ -n "$out" ] || exit 0
out="$out/ReLink"

# ---- 3. the language ----
lang=$(zenity --list --title="ReLink" --width=420 --height=300 \
    --text="The game's language" --column="Code" --column="Language" \
    "en-US" "English (US)" "en-GB" "English (UK)" "fr" "Français" "fr-CA" "Français (Canada)" \
    "de" "Deutsch" "es" "Español" "es-419" "Español (Latinoamérica)" "it" "Italiano" \
    "ja" "日本語" "ko" "한국어" "nl" "Nederlands" "pt-BR" "Português (Brasil)" \
    "pt-PT" "Português (Portugal)" "ru" "Русский" "zh-CN" "简体中文" "zh-TW" "繁體中文" 2>/dev/null) || exit 0
[ -n "$lang" ] || exit 0

# ---- 4. the build, with its progress ----
args=(--out "$out" --language "$lang")
if [ -n "$nup" ]; then args+=(--nup "$nup"); else args+=(--romfs "$romfs" --exefs "$exefs"); fi

log="$out/build.log"
mkdir -p "$out" 2>/dev/null
(
    "$PY" -I "$MK" "${args[@]}" 2>&1 | while IFS= read -r line; do
        case "$line" in
            @@progress\ *) echo "${line#@@progress }" ;;
            @@stage\ *)    echo "# ${line#@@stage }" ;;
            @@error\ *)    echo "# ${line#@@error }" ;;
            @@eta\ *)      echo "# about ${line#@@eta } s left" ;;
        esac
    done
) | zenity --progress --title="ReLink" --width=560 --auto-close --no-cancel \
        --text="Building the game from your own copy…" 2>/dev/null

# ---- 5. what happened ----
if [ -x "$out/relink" ]; then
    if ask "The game is built in
$out

Play it now?"; then
        cd "$out" && exec ./relink
    fi
else
    say "The build did not finish. Its log is in
$out/build.log"
fi
