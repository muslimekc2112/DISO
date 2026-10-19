#!/bin/sh
# DISO'yu kaldırır (Linux; install.sh ile kurulanı). Removes DISO (Linux; the copy install.sh put in).
#
#   uninstall.sh                 asks: remove DISO? and DISO's data too?
#   uninstall.sh --yes           no questions: removes the program, keeps the data
#   uninstall.sh --yes --data    no questions: removes the program and the data
set -u

dest=$(cd "$(dirname "$0")" && pwd)
yes=""
data=""
lang=""
for a in "$@"; do
    case "$a" in
        --yes|-y) yes=1 ;;
        --data) data=1 ;;
        --lang=tr|--tr) lang=tr ;;
        --lang=en|--en) lang=en ;;
    esac
done
if [ -z "$lang" ]; then
    lang=$(cat "$dest/.language" 2>/dev/null || true)                   # the language setup was done in
    case "$lang" in tr|en) ;; *) case "${LANGUAGE:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}" in tr*|TR*) lang=tr ;; *) lang=en ;; esac ;; esac
    if [ -z "$yes" ] && [ -t 0 ]; then
        printf 'Dil / Language:  1) Türkçe   2) English   [%s] ' "$([ "$lang" = tr ] && echo 1 || echo 2)"
        read -r pick || pick=""
        case "$pick" in 1) lang=tr ;; 2) lang=en ;; esac
    fi
fi

say() { if [ "$lang" = tr ]; then printf '%s\n' "$1"; else printf '%s\n' "$2"; fi; }
ask() {
    if [ -n "$yes" ] || [ ! -t 0 ]; then [ "$3" = y ]; return; fi
    if [ "$lang" = tr ]; then hint=$([ "$3" = y ] && echo "E/h" || echo "e/H"); q=$1; else hint=$([ "$3" = y ] && echo "Y/n" || echo "y/N"); q=$2; fi
    printf '%s [%s] ' "$q" "$hint"
    read -r answer || answer=""
    case "$answer" in [EeYy]*) return 0 ;; [HhNn]*) return 1 ;; *) [ "$3" = y ] ;; esac
}
pause() { if [ -z "$yes" ] && [ -t 0 ]; then say "Kapatmak için Enter'a bas." "Press Enter to close."; read -r _ || true; fi; }

data_home=${XDG_DATA_HOME:-$HOME/.local/share}
config_home=${XDG_CONFIG_HOME:-$HOME/.config}
data_dir="$data_home/DISO"

say "DISO'yu kaldırma" "Uninstall DISO"
say "Program: $dest" "Program: $dest"
if ! ask "DISO'yu bu bilgisayardan kaldırayım mı?" "Remove DISO from this computer?" n; then
    say "Vazgeçildi; hiçbir şey silinmedi." "Cancelled; nothing was removed."
    pause
    exit 0
fi
if [ -z "$data" ] && [ -d "$data_dir" ]; then
    say "" ""
    say "DISO'nun kayıtları: ayarlar, çalma listeleri, indirme listesi ve geçmiş, DISO'nun indirdiği araçlar" \
        "DISO's records: settings, playlists, the download list and history, the tools DISO downloaded"
    say "($data_dir). İndirdiğin dosyalara dokunulmaz." "($data_dir). The files you downloaded are not touched."
    if ask "Kayıtlar da silinsin mi?" "Delete these records too?" n; then data=1; fi
fi

pkill -f "$dest/DISO" 2>/dev/null && sleep 2 || true

rm -f "$data_home/applications/diso.desktop" "$data_home/applications/diso-uninstall.desktop" \
      "$data_home/icons/hicolor/256x256/apps/diso.png" "$config_home/autostart/DISO.desktop"
[ "$(readlink "$HOME/.local/bin/diso" 2>/dev/null)" = "$dest/DISO" ] && rm -f "$HOME/.local/bin/diso"
# the browsers' doors to DISO (only the ones that lead to this copy)
for f in "$config_home"/*/NativeMessagingHosts/com.iso.diso.json "$config_home"/*/*/NativeMessagingHosts/com.iso.diso.json \
         "$HOME/.mozilla/native-messaging-hosts/com.iso.diso.json"; do
    [ -f "$f" ] && grep -q "$dest/DISO" "$f" && rm -f "$f"
done
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$data_home/applications" 2>/dev/null || true
if [ -n "$data" ]; then
    rm -rf "$data_dir"
fi
rm -rf "$dest"
say "" ""
if [ -n "$data" ]; then
    say "✓ DISO ve kayıtları kaldırıldı." "✓ DISO and its records are removed."
else
    say "✓ DISO kaldırıldı. Kayıtların duruyor: $data_dir" "✓ DISO is removed. Your records are kept: $data_dir"
fi
pause
exit 0
