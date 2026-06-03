#!/usr/bin/env bash
set -Eeuo pipefail

CONFIG_FILE="/etc/venti-internet-check.conf"
RUNTIME_SCRIPT="/usr/local/sbin/venti-check-internet"
SERVICE_FILE="/etc/systemd/system/venti-internet-check.service"
TIMER_FILE="/etc/systemd/system/venti-internet-check.timer"

log() {
  printf '%s %s\n' "$(date --iso-8601=seconds)" "$*"
}

fail() {
  log "FEHLER: $*" >&2
  exit 1
}

[[ "$EUID" -eq 0 ]] || fail "Dieses Script muss mit sudo ausgeführt werden."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR/internet-check"

for file in \
  "$SOURCE_DIR/check-internet" \
  "$SOURCE_DIR/venti-internet-check.service" \
  "$SOURCE_DIR/venti-internet-check.timer"
do
  [[ -f "$file" ]] || fail "Benötigte Datei nicht gefunden: $file"
done

log "Installiere optionalen Internet- und USB-Modem-Recovery-Job."
install -o root -g root -m 0755 "$SOURCE_DIR/check-internet" "$RUNTIME_SCRIPT"
install -o root -g root -m 0644 "$SOURCE_DIR/venti-internet-check.service" "$SERVICE_FILE"
install -o root -g root -m 0644 "$SOURCE_DIR/venti-internet-check.timer" "$TIMER_FILE"

if [[ ! -e "$CONFIG_FILE" ]]; then
  cat > "$CONFIG_FILE" <<'CONFIG'
PING_ADDRESS="8.8.8.8"
PING_COUNT="4"
USB_VENDOR_ID="12d1"
USB_PRODUCT_ID="14db"
WIREGUARD_UNIT="wg-quick@wg0.service"
CONFIG
  chown root:root "$CONFIG_FILE"
  chmod 0644 "$CONFIG_FILE"
  log "Erzeuge lokale Konfiguration: $CONFIG_FILE"
else
  log "Behalte vorhandene Konfiguration: $CONFIG_FILE"
fi

# Entferne die frühere Cron- und Logrotate-Variante bei einem Upgrade.
if command -v crontab >/dev/null 2>&1 \
  && crontab -l 2>/dev/null | grep -q '/usr/local/bin/check_internet.sh'; then
  log "Entferne veralteten Internet-Check-Cronjob."
  CRONTAB_FILE="$(mktemp)"
  crontab -l 2>/dev/null \
    | grep -v '/usr/local/bin/check_internet.sh' \
    > "$CRONTAB_FILE" || true
  crontab "$CRONTAB_FILE"
  rm -f "$CRONTAB_FILE"
fi
rm -f /usr/local/bin/check_internet.sh /etc/logrotate.d/internet_check

systemctl daemon-reload
systemctl enable --now venti-internet-check.timer

log "Internet-Check-Timer wurde aktiviert."
log "Status: systemctl list-timers venti-internet-check.timer"
log "Logs: journalctl -u venti-internet-check.service --since today"
