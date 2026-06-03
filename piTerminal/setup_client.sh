#!/usr/bin/env bash
set -Eeuo pipefail

VENTI_USER="${VENTI_USER:-pi}"
WIREGUARD_CONFIG=""
REPLACE_WIREGUARD_CONFIG=false
SKIP_WIREGUARD=false
INSTALL_KIOSK=true
KIOSK_AUTOSTART="auto"
INSTALL_USB_MODEM_RECOVERY=false
SKIP_DOCKER=false
INSTALL_ROLLOUT=true
ROLLOUT_BRANCH="main"
ROLLOUT_COMPOSE_FILE="docker-compose.yml"
REPLACE_ROLLOUT_CONFIG=false

log() {
  printf '%s %s\n' "$(date --iso-8601=seconds)" "$*"
}

fail() {
  log "FEHLER: $*" >&2
  exit 1
}

usage() {
  cat <<'USAGE'
Verwendung:
  sudo ./piTerminal/setup_client.sh [Optionen]

Optionen:
  --wireguard-config PFAD           WireGuard-Konfiguration (Standard: piTerminal/client-configs/wg0.conf)
  --replace-wireguard-config        Vorhandene /etc/wireguard/wg0.conf bewusst ersetzen
  --skip-wireguard                  WireGuard-Installation und -Aktivierung überspringen
  --no-kiosk                        Pi-Terminal-Kiosk nicht installieren (Standard: Kiosk wird installiert)
  --kiosk                           Legacy-Alias; Kiosk ist bereits Standard
  --kiosk-autostart MODE            auto, labwc, lxde oder xdg (Standard: auto)
  --usb-modem-recovery              Optionalen Huawei-USB-Modem-Recovery-Timer installieren
  --skip-docker                     Docker-Installation überspringen, falls bereits vorbereitet
  --no-rollout                      Git-/Docker-Compose-Rollout nicht installieren (Standard: Rollout wird installiert)
  --rollout                         Legacy-Alias; Rollout ist bereits Standard
  --rollout-branch qa|main          Git-Branch fuer diesen Client (Standard: main)
  --rollout-compose DATEI           docker-compose.yml oder docker-compose-panstamp.yml
  --replace-rollout-config          Vorhandene /etc/venti-update.conf bewusst ersetzen
  -h, --help                        Diese Hilfe anzeigen
USAGE
}

while (($# > 0)); do
  case "$1" in
    --wireguard-config)
      (($# >= 2)) || fail "Für --wireguard-config fehlt ein Wert."
      WIREGUARD_CONFIG="$2"
      shift 2
      ;;
    --replace-wireguard-config)
      REPLACE_WIREGUARD_CONFIG=true
      shift
      ;;
    --skip-wireguard)
      SKIP_WIREGUARD=true
      shift
      ;;
    --no-kiosk)
      INSTALL_KIOSK=false
      shift
      ;;
    --kiosk)
      # Legacy-Alias: Kiosk ist fuer aktuelle Venti-Clients bereits Standard.
      INSTALL_KIOSK=true
      shift
      ;;
    --kiosk-autostart)
      (($# >= 2)) || fail "Für --kiosk-autostart fehlt ein Wert."
      KIOSK_AUTOSTART="$2"
      shift 2
      ;;
    --usb-modem-recovery)
      INSTALL_USB_MODEM_RECOVERY=true
      shift
      ;;
    --skip-docker)
      SKIP_DOCKER=true
      shift
      ;;
    --no-rollout)
      INSTALL_ROLLOUT=false
      shift
      ;;
    --rollout)
      # Legacy-Alias: Rollout ist fuer Standard-Clients bereits aktiv.
      INSTALL_ROLLOUT=true
      shift
      ;;
    --rollout-branch)
      (($# >= 2)) || fail "Für --rollout-branch fehlt ein Wert."
      ROLLOUT_BRANCH="$2"
      shift 2
      ;;
    --rollout-compose)
      (($# >= 2)) || fail "Für --rollout-compose fehlt ein Wert."
      ROLLOUT_COMPOSE_FILE="$2"
      shift 2
      ;;
    --replace-rollout-config)
      REPLACE_ROLLOUT_CONFIG=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *) fail "Unbekanntes Argument: $1" ;;
  esac
done

[[ "$EUID" -eq 0 ]] || fail "Dieses Script muss mit sudo ausgeführt werden."
case "$KIOSK_AUTOSTART" in
  auto|labwc|lxde|xdg) ;;
  *) fail "Ungültiger --kiosk-autostart Wert: $KIOSK_AUTOSTART" ;;
esac
case "$ROLLOUT_BRANCH" in
  qa|main) ;;
  *) fail "Ungültiger --rollout-branch Wert: $ROLLOUT_BRANCH" ;;
esac
case "$ROLLOUT_COMPOSE_FILE" in
  docker-compose.yml|docker-compose-panstamp.yml) ;;
  *) fail "Ungültiger --rollout-compose Wert: $ROLLOUT_COMPOSE_FILE" ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_WIREGUARD_CONFIG="$SCRIPT_DIR/client-configs/wg0.conf"
if [[ -z "$WIREGUARD_CONFIG" ]]; then
  WIREGUARD_CONFIG="$DEFAULT_WIREGUARD_CONFIG"
fi

if [[ "$SKIP_WIREGUARD" == true && "$REPLACE_WIREGUARD_CONFIG" == true ]]; then
  fail "--skip-wireguard und --replace-wireguard-config können nicht kombiniert werden."
fi
export VENTI_USER

if [[ "$SKIP_DOCKER" == true ]]; then
  log "Überspringe Docker-Installation auf ausdrücklichen Wunsch."
else
  "$SCRIPT_DIR/install-docker.sh"
fi

if [[ "$SKIP_WIREGUARD" == true ]]; then
  log "Überspringe WireGuard-Installation auf ausdrücklichen Wunsch."
else
  [[ -s "$WIREGUARD_CONFIG" ]] \
    || fail "WireGuard-Konfiguration fehlt oder ist leer: $WIREGUARD_CONFIG. Alternativ --skip-wireguard für bestehende Clients verwenden."

  WIREGUARD_ARGS=(--config "$WIREGUARD_CONFIG")
  if [[ "$REPLACE_WIREGUARD_CONFIG" == true ]]; then
    WIREGUARD_ARGS+=(--replace-config)
  fi
  "$SCRIPT_DIR/setup_wireguard.sh" "${WIREGUARD_ARGS[@]}"
fi

if [[ "$INSTALL_KIOSK" == true ]]; then
  "$SCRIPT_DIR/install_piterminal.sh" --autostart "$KIOSK_AUTOSTART"
else
  log "Kiosk-Setup wurde nicht angefordert."
fi

if [[ "$INSTALL_USB_MODEM_RECOVERY" == true ]]; then
  "$SCRIPT_DIR/setup_internet_check.sh"
else
  log "USB-Modem-Recovery wurde nicht angefordert."
fi

if [[ "$INSTALL_ROLLOUT" == true ]]; then
  ROLLOUT_ARGS=(--branch "$ROLLOUT_BRANCH" --compose "$ROLLOUT_COMPOSE_FILE")
  if [[ "$REPLACE_ROLLOUT_CONFIG" == true ]]; then
    ROLLOUT_ARGS+=(--replace-config)
  fi
  "$SCRIPT_DIR/setup_rollout.sh" "${ROLLOUT_ARGS[@]}"
else
  log "Rollout-Setup wurde nicht angefordert."
fi

log "Client-Bootstrap abgeschlossen."
if [[ "$SKIP_WIREGUARD" != true ]]; then
  log "Prüfe WireGuard mit: systemctl status wg-quick@wg0"
fi
log "Prüfe Docker mit: systemctl status docker"
if [[ "$INSTALL_KIOSK" == true ]]; then
  log "Bitte neu starten und den automatischen Dashboard-Start prüfen."
fi
if [[ "$INSTALL_USB_MODEM_RECOVERY" == true ]]; then
  log "Prüfe den Internet-Timer mit: systemctl list-timers venti-internet-check.timer"
fi
if [[ "$INSTALL_ROLLOUT" == true ]]; then
  log "Prüfe den Rollout-Timer mit: systemctl list-timers venti-update.timer"
fi
