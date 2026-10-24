#!/bin/sh
# DISO kurulumu (Linux, yalnızca bu kullanıcı için; yönetici şifresi gerekmez)
# DISO setup (Linux, for this user only; no administrator password needed)
#
#   ./install.sh            asks the language, installs, offers to start DISO
#   ./install.sh --yes      no questions (the language comes from $LANG)
#   ./install.sh --yes --no-start     ... and do not start DISO at the end
#
# The program goes to ~/.local/opt/DISO, a "diso" command to ~/.local/bin, DISO to the applications menu
# (with "Uninstall DISO" beside it). DISO's own data (settings, lists) stays in ~/.local/share/DISO.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
yes=""
lang=""
start=1
for a in "$@"; do
    case "$a" in
        --yes|-y) yes=1 ;;
        --no-start) start="" ;;
        --lang=tr|--tr) lang=tr ;;
        --lang=en|--en) lang=en ;;
    esac
done
if [ -z "$lang" ]; then
    case "${LANGUAGE:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}" in tr*|TR*) lang=tr ;; *) lang=en ;; esac
    if [ -z "$yes" ] && [ -t 0 ]; then
        printf 'Dil / Language:  1) Türkçe   2) English   [%s] ' "$([ "$lang" = tr ] && echo 1 || echo 2)"
        read -r pick || pick=""
        case "$pick" in 1) lang=tr ;; 2) lang=en ;; esac
    fi
fi

say() { if [ "$lang" = tr ]; then printf '%s\n' "$1"; else printf '%s\n' "$2"; fi; }
ask() {   # ask "Türkçe soru" "English question" default(y/n) -> 0 for yes
    if [ -n "$yes" ] || [ ! -t 0 ]; then [ "$3" = y ]; return; fi
    if [ "$lang" = tr ]; then hint=$([ "$3" = y ] && echo "E/h" || echo "e/H"); q=$1; else hint=$([ "$3" = y ] && echo "Y/n" || echo "y/N"); q=$2; fi
    printf '%s [%s] ' "$q" "$hint"
    read -r answer || answer=""
    case "$answer" in [EeYy]*) return 0 ;; [HhNn]*) return 1 ;; *) [ "$3" = y ] ;; esac
}

if [ ! -x "$here/DISO/DISO" ]; then
    say "DISO klasörü bulunamadı: arşivi tamamen çıkarıp install.sh'yi onun içinden çalıştır." \
        "The DISO folder is missing: unpack the whole archive and run install.sh from inside it."
    exit 1
fi

data_home=${XDG_DATA_HOME:-$HOME/.local/share}
dest="$HOME/.local/opt/DISO"
bin="$HOME/.local/bin"
apps="$data_home/applications"
icons="$data_home/icons/hicolor/256x256/apps"

say "" ""
say "DISO kurulumu" "DISO setup"
say "Kurulacağı yer: $dest" "It goes to: $dest"
if ! ask "Kurayım mı?" "Install it?" y; then
    say "Vazgeçildi." "Cancelled."
    exit 0
fi

if pgrep -f "$dest/DISO" >/dev/null 2>&1; then
    say "DISO açık; kapatıyorum…" "DISO is running; closing it…"
    pkill -f "$dest/DISO" || true
    sleep 2
fi

mkdir -p "$HOME/.local/opt" "$bin" "$apps" "$icons"
rm -rf "$dest.new"
cp -a "$here/DISO" "$dest.new"
rm -rf "$dest"
mv "$dest.new" "$dest"
chmod +x "$dest/DISO" "$dest/uninstall.sh"
ln -sf "$dest/DISO" "$bin/diso"
cp "$dest/diso.png" "$icons/diso.png"

cat > "$apps/diso.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=DISO
GenericName=Download manager
GenericName[tr]=İndirme yöneticisi
Comment=Download files, videos and music
Comment[tr]=Dosya, video ve müzik indir
Exec="$dest/DISO" %U
Icon=diso
Terminal=false
Categories=Network;FileTransfer;AudioVideo;
StartupWMClass=DISO
EOF
cat > "$apps/diso-uninstall.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Uninstall DISO
Name[tr]=DISO'yu Kaldır
Exec="$dest/uninstall.sh"
Icon=diso
Terminal=true
Categories=Settings;
EOF
printf '%s\n' "$lang" > "$dest/.language"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$apps" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$data_home/icons/hicolor" 2>/dev/null || true

# the language for DISO's first start (an existing choice is kept)
settings="$data_home/DISO/settings.json"
if [ ! -f "$settings" ]; then
    mkdir -p "$data_home/DISO"
    if [ "$lang" = tr ]; then echo '{"language": "Türkçe"}' > "$settings"; else echo '{"language": "English"}' > "$settings"; fi
fi

say "" ""
say "✓ DISO kuruldu. Uygulamalar menüsünde “DISO”; terminalde: diso" \
    "✓ DISO is installed. It is in the applications menu as “DISO”; in a terminal: diso"
say "  Kaldırmak için: menüde “DISO'yu Kaldır” ya da $dest/uninstall.sh" \
    "  To remove it: “Uninstall DISO” in the menu, or $dest/uninstall.sh"
case ":$PATH:" in *":$bin:"*) ;; *) say "  (Not: $bin PATH'te değil; “diso” komutu yeni oturumda çalışır.)" \
                                      "  (Note: $bin is not on PATH; the “diso” command works in a new session.)" ;; esac
if [ -n "$start" ] && ask "DISO'yu şimdi açayım mı?" "Start DISO now?" y; then
    nohup "$dest/DISO" >/dev/null 2>&1 &
fi
