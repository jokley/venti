#!/usr/bin/env bash
set -Eeuo pipefail

WIREGUARD_CONFIG=""
REPLACE_CONFIG=false
TARGET_CONFIG="/etc/wireguard/wg0.conf"

log() {
  printf '%s %s\n' "$(date --iso-8601=seconds)" "$*"
}

fail() {
  log "FEHLER: $*" >&2
  exit 1
}

usage() {
  cat <<'USAGE'
Verwendung: sudo ./piTerminal/setup_wireguard.sh --config /pfad/zur/wg0.conf [--replace-config]

Installiert WireGuard und aktiviert wg-quick@wg0. Eine vorhandene Konfiguration
wird nur mit --replace-config überschrieben.
USAGE
}

while (($# > 0)); do
  case "$1" in
    --config)
      (($# >= 2)) || fail "Für --config fehlt ein Wert."
      WIREGUARD_CONFIG="$2"
      shift 2
      ;;
    --replace-config)
      REPLACE_CONFIG=true
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
[[ -n "$WIREGUARD_CONFIG" ]] || fail "--config /pfad/zur/wg0.conf ist erforderlich."
[[ -s "$WIREGUARD_CONFIG" ]] || fail "WireGuard-Konfiguration fehlt oder ist leer: $WIREGUARD_CONFIG"
command -v apt-get >/dev/null 2>&1 || fail "apt-get wurde nicht gefunden."

if ! command -v wg >/dev/null 2>&1 || ! command -v wg-quick >/dev/null 2>&1; then
  log "Installiere WireGuard."
  apt-get update
  apt-get install -y wireguard
fi

install -d -o root -g root -m 0700 /etc/wireguard

if [[ -e "$TARGET_CONFIG" ]] && cmp -s "$WIREGUARD_CONFIG" "$TARGET_CONFIG"; then
  log "WireGuard-Konfiguration ist bereits aktuell: $TARGET_CONFIG"
elif [[ -e "$TARGET_CONFIG" && "$REPLACE_CONFIG" != true ]]; then
  fail "$TARGET_CONFIG existiert bereits. Verwende --replace-config zum bewussten Überschreiben."
else
  log "Installiere WireGuard-Konfiguration nach $TARGET_CONFIG."
  install -o root -g root -m 0600 "$WIREGUARD_CONFIG" "$TARGET_CONFIG"
fi

log "Aktiviere WireGuard-Tunnel wg0."
if ! systemctl enable --now wg-quick@wg0; then
  log "WireGuard konnte nicht gestartet werden. Diagnose: systemctl status wg-quick@wg0" >&2
  exit 1
fi

systemctl is-active --quiet wg-quick@wg0 \
  || fail "wg-quick@wg0 ist nicht aktiv. Diagnose: journalctl -u wg-quick@wg0"

log "WireGuard wg0 ist aktiv."
