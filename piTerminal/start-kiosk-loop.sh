#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
START_SCRIPT="$SCRIPT_DIR/start.sh"

log() {
  printf '%s %s\n' "$(date --iso-8601=seconds)" "$*"
}

while true; do
  log "Starte Venti-Kiosk."

  if "$START_SCRIPT"; then
    log "Venti-Kiosk wurde beendet. Neuer Startversuch in 10 Sekunden."
  else
    status=$?
    log "Venti-Kiosk ist mit Status $status fehlgeschlagen. Neuer Startversuch in 10 Sekunden."
  fi

  sleep 10
done
