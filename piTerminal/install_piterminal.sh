#!/usr/bin/env bash
set -Eeuo pipefail

VENTI_USER="${VENTI_USER:-pi}"
AUTOSTART_MODE="auto"
KIOSK_CONFIG_FILE="/etc/venti-kiosk.conf"

log() {
  printf '%s %s\n' "$(date --iso-8601=seconds)" "$*"
}

fail() {
  log "FEHLER: $*" >&2
  exit 1
}

usage() {
  cat <<'USAGE'
Verwendung: sudo ./piTerminal/install_piterminal.sh [--autostart auto|labwc|lxde|xdg]

Installiert den Venti-Kiosk-Autostart für den Benutzer aus VENTI_USER (Standard: pi).
USAGE
}

while (($# > 0)); do
  case "$1" in
    --autostart)
      (($# >= 2)) || fail "Für --autostart fehlt ein Wert."
      AUTOSTART_MODE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unbekanntes Argument: $1"
      ;;
  esac
done

[[ "$EUID" -eq 0 ]] || fail "Dieses Script muss mit sudo ausgeführt werden."

case "$AUTOSTART_MODE" in
  auto|labwc|lxde|xdg) ;;
  *) fail "Ungültiger Autostart-Modus: $AUTOSTART_MODE (erlaubt: auto, labwc, lxde, xdg)" ;;
esac

VENTI_PASSWD_ENTRY="$(getent passwd "$VENTI_USER" || true)"
[[ -n "$VENTI_PASSWD_ENTRY" ]] || fail "Benutzer existiert nicht: $VENTI_USER"
VENTI_HOME="$(cut -d: -f6 <<<"$VENTI_PASSWD_ENTRY")"
VENTI_GROUP="$(id -gn "$VENTI_USER")"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
START_SCRIPT="$PROJECT_DIR/start.sh"
LOOP_SCRIPT="$PROJECT_DIR/start-kiosk-loop.sh"
ICON_FILE="$PROJECT_DIR/venti.png"
BACKGROUND_IMAGE="$PROJECT_DIR/logo.jpg"
DESKTOP_DIR="$VENTI_HOME/Desktop"
DESKTOP_FILE="$DESKTOP_DIR/venti.desktop"
LABWC_AUTOSTART_FILE="$VENTI_HOME/.config/labwc/autostart"
LXDE_AUTOSTART_FILE="$VENTI_HOME/.config/lxsession/LXDE-pi/autostart"
XDG_AUTOSTART_FILE="$VENTI_HOME/.config/autostart/venti-kiosk.desktop"
PCMANFM_CONF_DIR="$VENTI_HOME/.config/pcmanfm/LXDE-pi"
PCMANFM_CONF_FILE="$PCMANFM_CONF_DIR/desktop-items-0.conf"

for file in "$START_SCRIPT" "$LOOP_SCRIPT" "$ICON_FILE" "$BACKGROUND_IMAGE"; do
  [[ -f "$file" ]] || fail "Benötigte Datei nicht gefunden: $file"
done

chown "$VENTI_USER:$VENTI_GROUP" "$START_SCRIPT" "$LOOP_SCRIPT"
chmod 0755 "$START_SCRIPT" "$LOOP_SCRIPT"

if [[ ! -e "$KIOSK_CONFIG_FILE" ]]; then
  log "Erzeuge $KIOSK_CONFIG_FILE."
  cat > "$KIOSK_CONFIG_FILE" <<'CONFIG'
KIOSK_URL="http://127.0.0.1/?kiosk=1"
KIOSK_HEALTH_URL="http://127.0.0.1/"
KIOSK_WAIT_TIMEOUT_SEC="300"
CONFIG
  chown root:root "$KIOSK_CONFIG_FILE"
  chmod 0644 "$KIOSK_CONFIG_FILE"
else
  log "Behalte vorhandene Konfiguration: $KIOSK_CONFIG_FILE"
fi

# Die Datei gehört root und wird bewusst als lokale Kiosk-Konfiguration geladen.
# shellcheck source=/dev/null
source "$KIOSK_CONFIG_FILE"
: "${KIOSK_URL:?KIOSK_URL fehlt in $KIOSK_CONFIG_FILE}"

if [[ "$AUTOSTART_MODE" == "auto" ]]; then
  if command -v labwc >/dev/null 2>&1 \
    || [[ -x /usr/bin/labwc ]] \
    || compgen -G '/usr/share/wayland-sessions/*labwc*.desktop' >/dev/null \
    || [[ -e "$VENTI_HOME/.config/labwc" ]]; then
    AUTOSTART_MODE="labwc"
  elif [[ -e /usr/share/xsessions/LXDE-pi.desktop ]] \
    || [[ -d /etc/xdg/lxsession/LXDE-pi ]] \
    || [[ -e "$VENTI_HOME/.config/lxsession/LXDE-pi" ]]; then
    AUTOSTART_MODE="lxde"
  else
    AUTOSTART_MODE="xdg"
    log "WARNUNG: Keine bekannte labwc- oder LXDE-Sitzung erkannt. Verwende XDG-Autostart als Fallback."
  fi
fi

remove_venti_lines() {
  local file="$1"
  local temporary_file

  [[ -f "$file" ]] || return 0
  temporary_file="$(mktemp)"
  awk '
    /# Venti kiosk start/ { next }
    /piTerminal\/start\.sh/ { next }
    /piTerminal\/start-kiosk-loop\.sh/ { next }
    { print }
  ' "$file" > "$temporary_file"
  cat "$temporary_file" > "$file"
  rm -f "$temporary_file"
}

remove_venti_lines "$LABWC_AUTOSTART_FILE"
remove_venti_lines "$LXDE_AUTOSTART_FILE"
rm -f "$XDG_AUTOSTART_FILE"

case "$AUTOSTART_MODE" in
  labwc)
    AUTOSTART_FILE="$LABWC_AUTOSTART_FILE"
    mkdir -p "$(dirname "$AUTOSTART_FILE")"
    cat >> "$AUTOSTART_FILE" <<EOF_AUTOSTART
# Venti kiosk start
bash "$LOOP_SCRIPT" &
EOF_AUTOSTART
    ;;
  lxde)
    AUTOSTART_FILE="$LXDE_AUTOSTART_FILE"
    mkdir -p "$(dirname "$AUTOSTART_FILE")"
    cat >> "$AUTOSTART_FILE" <<EOF_AUTOSTART
# Venti kiosk start
@bash "$LOOP_SCRIPT"
EOF_AUTOSTART
    ;;
  xdg)
    AUTOSTART_FILE="$XDG_AUTOSTART_FILE"
    mkdir -p "$(dirname "$AUTOSTART_FILE")"
    cat > "$AUTOSTART_FILE" <<EOF_AUTOSTART
[Desktop Entry]
Type=Application
Name=Venti Kiosk
Comment=Start Venti dashboard in Chromium kiosk mode
Exec=$LOOP_SCRIPT
Terminal=false
X-GNOME-Autostart-enabled=true
EOF_AUTOSTART
    ;;
esac

chown "$VENTI_USER:$VENTI_GROUP" "$(dirname "$AUTOSTART_FILE")" "$AUTOSTART_FILE"

log "Erzeuge Desktop-Verknüpfung: $DESKTOP_FILE"
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_FILE" <<EOF_DESKTOP
[Desktop Entry]
Type=Link
Name=Heulüfter
Comment=Heulüfter Steuerung
Icon=$ICON_FILE
URL=$KIOSK_URL
EOF_DESKTOP
chown "$VENTI_USER:$VENTI_GROUP" "$DESKTOP_DIR" "$DESKTOP_FILE"
chmod 0755 "$DESKTOP_FILE"

log "Konfiguriere Desktop-Hintergrund, falls PCManFM verwendet wird."
mkdir -p "$PCMANFM_CONF_DIR"
if [[ -f "$PCMANFM_CONF_FILE" ]]; then
  if grep -q '^wallpaper=' "$PCMANFM_CONF_FILE"; then
    sed -i "s|^wallpaper=.*|wallpaper=$BACKGROUND_IMAGE|" "$PCMANFM_CONF_FILE"
  else
    printf '\nwallpaper=%s\n' "$BACKGROUND_IMAGE" >> "$PCMANFM_CONF_FILE"
  fi
else
  cat > "$PCMANFM_CONF_FILE" <<EOF_PCMANFM
[*]
wallpaper=$BACKGROUND_IMAGE
wallpaper_mode=stretch
desktop_bg=#000000
desktop_fg=#ffffff
desktop_shadow=false
desktop_font=Sans 10
show_wm_menu=false
sort=mtime;ascending;
space_between_icons=32
EOF_PCMANFM
fi
chown -R "$VENTI_USER:$VENTI_GROUP" "$PCMANFM_CONF_DIR"

if systemctl is-enabled kiosk.service >/dev/null 2>&1 \
  || systemctl is-active kiosk.service >/dev/null 2>&1 \
  || [[ -e /etc/systemd/system/kiosk.service ]]; then
  log "Entferne veralteten systemweiten kiosk.service."
  systemctl disable --now kiosk.service >/dev/null 2>&1 || true
  rm -f /etc/systemd/system/kiosk.service
  systemctl daemon-reload
fi

log "Pi-Terminal-Setup abgeschlossen. Autostart-Modus: $AUTOSTART_MODE"
log "Aktiver Autostart: $AUTOSTART_FILE"
log "Bitte den Raspberry Pi neu starten und prüfen, ob das Dashboard automatisch geöffnet wird."
