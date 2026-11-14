#!/bin/bash
# The AppImage's window: pick the game, the folder and the language, then build with a progress bar.
# Called by AppRun when it is given no argument; any argument goes to make_game.py as it is (the command line).
# zenity draws it: a desktop without zenity gets the command line's usage instead.
set -u
HERE="${RELINK_APPDIR:-$(dirname "$(readlink -f "$0")")/../../../../..}"   # (the AppRun exports it; run by hand, five levels up)
PY="$HERE/usr/python/bin/python3"
MK="$HERE/usr/share/relink/nx2/make_game.py"

if ! command -v zenity >/dev/null 2>&1; then
    echo "ReLink: zenity is not installed, so there is no window. Run it with --help for the command line." >&2
    exec "$PY" -I "$MK" --help
fi

say() { zenity --info --title="ReLink" --width=560 --text="$1" 2>/dev/null; }
ask() { zenity --question --title="ReLink" --width=560 --text="$1" 2>/dev/null; }

# ---- 1. the game: a .nup, or the romfs and exefs folders ----
src=$(zenity --list --title="ReLink — step 1 of 4: your copy of the game" --width=600 --height=280 \
    --text="Where is your own copy of the game?" \
    --column="Pick" --column="What it is" \
    "nup" "A .nup file (ReLink unpacks it itself)" \
    "folders" "The romfs and exefs folders, already unpacked" 2>/dev/null) || exit 0
[ -n "$src" ] || exit 0

nup="" romfs="" exefs=""
if [ "$src" = "nup" ]; then
    nup=$(zenity --file-selection --title="ReLink — step 1 of 4: choose your .nup file" \
        --file-filter="Game dump (*.nup) | *.nup" --file-filter="All files | *" 2>/dev/null) || exit 0
    [ -n "$nup" ] || exit 0
    say "Your copy:
$nup

Next: where the game will be built."
else
    romfs=$(zenity --file-selection --directory --title="ReLink — step 1 of 4: choose the romfs folder" 2>/dev/null) || exit 0
    [ -n "$romfs" ] || exit 0
    exefs=$(zenity --file-selection --directory --title="ReLink — step 1 of 4: choose the exefs folder" 2>/dev/null) || exit 0
    [ -n "$exefs" ] || exit 0
    say "Your copy:
romfs: $romfs
exefs: $exefs

Next: where the game will be built."
fi

# ---- 2. where the game goes (a folder, not a file: the title says so) ----
say "Step 2 of 4: choose the folder where the game will be built.

ReLink makes a folder named ReLink inside it. About 25 GB are needed while it unpacks your copy."
out=$(zenity --file-selection --directory --title="ReLink — step 2 of 4: choose the FOLDER where the game will be built" \
    --filename="$HOME/" 2>/dev/null) || exit 0
[ -n "$out" ] || exit 0
out="$out/ReLink"

# ---- 3. the language ----
lang=$(zenity --list --title="ReLink — step 3 of 4: the game's language" --width=460 --height=340 \
    --text="The language the game will speak and write in" --column="Code" --column="Language" \
    "en-US" "English (US)" "en-GB" "English (UK)" "fr" "Français" "fr-CA" "Français (Canada)" \
    "de" "Deutsch" "es" "Español" "es-419" "Español (Latinoamérica)" "it" "Italiano" \
    "ja" "日本語" "ko" "한국어" "nl" "Nederlands" "pt-BR" "Português (Brasil)" \
    "pt-PT" "Português (Portugal)" "ru" "Русский" "zh-CN" "简体中文" "zh-TW" "繁體中文" 2>/dev/null) || exit 0
[ -n "$lang" ] || exit 0

# ---- 4. a last look, then the build ----
if [ -n "$nup" ]; then from="your .nup: $nup"; else from="romfs: $romfs
exefs: $exefs"; fi
ask "Step 4 of 4: build the game?

From: $from
Into: $out
Language: $lang

It takes 10 to 45 minutes. The window shows the progress." || exit 0

log="$out/build.log"
args=(--out "$out" --language "$lang" --log "$log")
if [ -n "$nup" ]; then args+=(--nup "$nup"); else args+=(--romfs "$romfs" --exefs "$exefs"); fi

mkdir -p "$out" 2>/dev/null
(
    stage="starting"; file=""; eta=""
    "$PY" -I "$MK" "${args[@]}" 2>&1 | while IFS= read -r line; do
        case "$line" in
            @@stage\ *)    stage="${line#@@stage }"; stage="${stage#* }"; echo "# $stage" ;;
            @@file\ *)     file="${line#@@file }"; file="${file%% *}"; echo "# $stage — $file" ;;
            @@eta\ *)      eta="${line#@@eta }"
                           if [ -n "$file" ]; then echo "# $stage — $file — about ${eta}s left"
                           else echo "# $stage — about ${eta}s left"; fi ;;
            @@progress\ *) awk -v p="${line#@@progress }" 'BEGIN { printf "%d\n", p * 100 }' ;;
            @@error\ *)    echo "# ${line#@@error }" ;;
        esac
    done
) | zenity --progress --title="ReLink — building the game" --width=640 --auto-close --no-cancel \
        --text="Building the game from your own copy…" 2>/dev/null

# ---- 5. what happened ----
if [ -x "$out/relink" ]; then
    if ask "The game is built in
$out

Play it now?"; then
        cd "$out" && exec ./relink
    fi
else
    if [ -f "$log" ]; then
        zenity --text-info --title="ReLink — the build did not finish" --width=900 --height=600 \
            --filename="$log" --text="The build did not finish. Its log:" 2>/dev/null
    else
        say "The build did not finish, and it wrote no log."
    fi
fi
