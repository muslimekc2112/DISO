#!/bin/sh
# DISO'yu kaldırır (macOS). Çift tıkla: Terminal'de açılır ve sorar.
# Removes DISO (macOS). Double-click it: it opens in Terminal and asks.
set -u

first=$(defaults read -g AppleLanguages 2>/dev/null | tr -d ' "(),' | grep -v '^$' | head -n 1)
case "$first" in tr*) lang=tr ;; *) lang=en ;; esac
printf 'Dil / Language:  1) Türkçe   2) English   [%s] ' "$([ "$lang" = tr ] && echo 1 || echo 2)"
read -r pick || pick=""
case "$pick" in 1) lang=tr ;; 2) lang=en ;; esac

say() { if [ "$lang" = tr ]; then printf '%s\n' "$1"; else printf '%s\n' "$2"; fi; }
ask() {
    if [ "$lang" = tr ]; then hint=$([ "$3" = y ] && echo "E/h" || echo "e/H"); q=$1; else hint=$([ "$3" = y ] && echo "Y/n" || echo "y/N"); q=$2; fi
    printf '%s [%s] ' "$q" "$hint"
    read -r answer || answer=""
    case "$answer" in [EeYy]*) return 0 ;; [HhNn]*) return 1 ;; *) [ "$3" = y ] ;; esac
}

support="$HOME/Library/Application Support"
data_dir="$support/DISO"
apps=""
for a in "/Applications/DISO.app" "$HOME/Applications/DISO.app"; do [ -d "$a" ] && apps="$apps$a
"; done

say "DISO'yu kaldırma" "Uninstall DISO"
if [ -z "$apps" ] && [ ! -d "$data_dir" ]; then
    say "DISO bu Mac'te kurulu görünmüyor." "DISO does not seem to be installed on this Mac."
    exit 0
fi
[ -n "$apps" ] && printf '%s' "$apps"
if ! ask "DISO'yu bu Mac'ten kaldırayım mı?" "Remove DISO from this Mac?" n; then
    say "Vazgeçildi; hiçbir şey silinmedi." "Cancelled; nothing was removed."
    exit 0
fi
data=""
if [ -d "$data_dir" ]; then
    say "" ""
    say "DISO'nun kayıtları: ayarlar, çalma listeleri, indirme listesi ve geçmiş, DISO'nun indirdiği araçlar" \
        "DISO's records: settings, playlists, the download list and history, the tools DISO downloaded"
    say "($data_dir). İndirdiğin dosyalara dokunulmaz." "($data_dir). The files you downloaded are not touched."
    if ask "Kayıtlar da silinsin mi?" "Delete these records too?" n; then data=1; fi
fi

osascript -e 'tell application "DISO" to quit' >/dev/null 2>&1 || true
sleep 1
pkill -f "DISO.app/Contents/MacOS/DISO" 2>/dev/null || true

agent="$HOME/Library/LaunchAgents/com.iso.diso.plist"
if [ -f "$agent" ]; then
    launchctl unload "$agent" >/dev/null 2>&1 || true
    rm -f "$agent"
fi
for f in "$support"/*/NativeMessagingHosts/com.iso.diso.json "$support"/*/*/NativeMessagingHosts/com.iso.diso.json; do
    [ -f "$f" ] && rm -f "$f"
done
printf '%s' "$apps" | while IFS= read -r a; do
    [ -n "$a" ] || continue
    rm -rf "$a" 2>/dev/null || {
        say "$a silinemedi; yönetici şifren isteniyor." "$a could not be removed; your administrator password is needed."
        sudo rm -rf "$a"
    }
done
[ -n "$data" ] && rm -rf "$data_dir"
say "" ""
if [ -n "$data" ]; then
    say "✓ DISO ve kayıtları kaldırıldı." "✓ DISO and its records are removed."
else
    say "✓ DISO kaldırıldı. Kayıtların duruyor: $data_dir" "✓ DISO is removed. Your records are kept: $data_dir"
fi
say "Bu pencereyi kapatabilirsin." "You can close this window."
