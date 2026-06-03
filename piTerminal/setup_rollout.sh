#!/usr/bin/env bash
set -Eeuo pipefail

VENTI_USER="${VENTI_USER:-pi}"
DEPLOY_BRANCH="main"
COMPOSE_FILE="docker-compose.yml"
CONFIG_FILE="/etc/venti-update.conf"
RUNTIME_SCRIPT="/usr/local/sbin/venti-update"
SERVICE_FILE="/etc/systemd/system/venti-update.service"
TIMER_FILE="/etc/systemd/system/venti-update.timer"

log() {
  printf '%s %s\n' "$(date --iso-8601=seconds)" "$*"
}

fail() {
  log "FEHLER: $*" >&2
  exit 1
}

usage() {
  cat <<'USAGE'
Verwendung: sudo ./piTerminal/setup_rollout.sh [Optionen]

Optionen:
  --branch qa|main                  Git-Branch fuer diesen Client (Standard: main)
  --compose docker-compose.yml|docker-compose-panstamp.yml
                                    Compose-Datei fuer diesen Client (Standard: docker-compose.yml)
  --replace-config                  Vorhandene /etc/venti-update.conf bewusst ersetzen
  -h, --help                        Diese Hilfe anzeigen
USAGE
}

REPLACE_CONFIG=false
while (($# > 0)); do
  case "$1" in
    --branch)
      (($# >= 2)) || fail "Für --branch fehlt ein Wert."
      DEPLOY_BRANCH="$2"
      shift 2
      ;;
    --compose)
      (($# >= 2)) || fail "Für --compose fehlt ein Wert."
      COMPOSE_FILE="$2"
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

case "$DEPLOY_BRANCH" in
  qa|main) ;;
  *) fail "Nicht erlaubter Branch: $DEPLOY_BRANCH (erlaubt: qa, main)" ;;
esac

case "$COMPOSE_FILE" in
  docker-compose.yml|docker-compose-panstamp.yml) ;;
  *) fail "Nicht erlaubte Compose-Datei: $COMPOSE_FILE" ;;
esac

id "$VENTI_USER" >/dev/null 2>&1 || fail "Benutzer existiert nicht: $VENTI_USER"
VENTI_GROUP="$(id -gn "$VENTI_USER")"
VENTI_HOME="$(getent passwd "$VENTI_USER" | cut -d: -f6)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_DIR="$SCRIPT_DIR/rollout"

for file in \
  "$SOURCE_DIR/venti-update" \
  "$SOURCE_DIR/venti-update.service" \
  "$SOURCE_DIR/venti-update.timer"
do
  [[ -f "$file" ]] || fail "Benötigte Datei nicht gefunden: $file"
done

for command_name in git docker curl flock; do
  command -v "$command_name" >/dev/null 2>&1 \
    || fail "Benötigtes Kommando fehlt: $command_name"
done
docker compose version >/dev/null \
  || fail "Docker Compose Plugin ist nicht verfügbar."

log "Installiere Rollout-Laufzeitscript und systemd Units."
install -o root -g root -m 0755 "$SOURCE_DIR/venti-update" "$RUNTIME_SCRIPT"
install -o root -g root -m 0644 "$SOURCE_DIR/venti-update.service" "$SERVICE_FILE"
install -o root -g root -m 0644 "$SOURCE_DIR/venti-update.timer" "$TIMER_FILE"

sed -i \
  -e "s/^User=.*/User=$VENTI_USER/" \
  -e "s/^Group=.*/Group=$VENTI_GROUP/" \
  "$SERVICE_FILE"

if [[ ! -e "$CONFIG_FILE" || "$REPLACE_CONFIG" == true ]]; then
  cat > "$CONFIG_FILE" <<EOF_CONFIG
VENTI_DIR="$REPO_DIR"
DEPLOY_BRANCH="$DEPLOY_BRANCH"
COMPOSE_FILE="$COMPOSE_FILE"
HEALTH_URL="http://127.0.0.1:5000/healthz"
HEALTH_RETRIES="12"
HEALTH_SLEEP_SEC="10"
COMPOSE_WAIT_TIMEOUT_SEC="180"
EOF_CONFIG
  chown root:root "$CONFIG_FILE"
  chmod 0644 "$CONFIG_FILE"
  log "Erzeuge Konfiguration: $CONFIG_FILE"
else
  log "Behalte vorhandene Konfiguration: $CONFIG_FILE"
fi

if [[ "$REPO_DIR" != "$VENTI_HOME"* ]]; then
  log "WARNUNG: Repository liegt nicht unter dem Home-Verzeichnis von $VENTI_USER: $REPO_DIR"
fi

systemctl daemon-reload
systemctl enable --now venti-update.timer

log "Rollout-Timer wurde aktiviert."
log "Konfiguration: $CONFIG_FILE"
log "Manueller Test: sudo -u $VENTI_USER /usr/local/sbin/venti-update"
log "Timer-Status: systemctl list-timers venti-update.timer"
log "Logs: journalctl -u venti-update.service --since today"
