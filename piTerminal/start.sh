#!/usr/bin/env bash
set -Eeuo pipefail

CONFIG_FILE="/etc/venti-kiosk.conf"

log() {
  printf '%s %s\n' "$(date --iso-8601=seconds)" "$*"
}

fail() {
  log "FEHLER: $*" >&2
  exit 1
}

if [[ -r "$CONFIG_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
fi

KIOSK_URL="${KIOSK_URL:-http://127.0.0.1/?kiosk=1}"
KIOSK_HEALTH_URL="${KIOSK_HEALTH_URL:-http://127.0.0.1/}"
KIOSK_WAIT_TIMEOUT_SEC="${KIOSK_WAIT_TIMEOUT_SEC:-300}"

[[ "$KIOSK_WAIT_TIMEOUT_SEC" =~ ^[0-9]+$ ]] \
  || fail "KIOSK_WAIT_TIMEOUT_SEC muss eine nicht-negative Ganzzahl sein."

if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  fail "Keine grafische Sitzung gefunden: DISPLAY und WAYLAND_DISPLAY fehlen."
fi

LOCK_DIR="${XDG_RUNTIME_DIR:-/tmp}"
[[ -d "$LOCK_DIR" ]] || fail "Lock-Verzeichnis existiert nicht: $LOCK_DIR"
exec 9>"$LOCK_DIR/venti-kiosk.lock"

if ! flock -n 9; then
  log "Venti-Kiosk läuft bereits. Beende diesen zusätzlichen Startversuch."
  exit 0
fi

if command -v chromium >/dev/null 2>&1; then
  BROWSER="$(command -v chromium)"
elif command -v chromium-browser >/dev/null 2>&1; then
  BROWSER="$(command -v chromium-browser)"
else
  fail "Chromium ist nicht installiert (chromium oder chromium-browser benötigt)."
fi

dashboard_ready() {
  curl \
    --fail \
    --location \
    --silent \
    --show-error \
    --connect-timeout 3 \
    --max-time 10 \
    "$KIOSK_HEALTH_URL" \
    >/dev/null
}

log "Grafische Sitzung erkannt: XDG_CURRENT_DESKTOP=${XDG_CURRENT_DESKTOP:-nicht gesetzt}, XDG_SESSION_TYPE=${XDG_SESSION_TYPE:-nicht gesetzt}, DISPLAY=${DISPLAY:-nicht gesetzt}, WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-nicht gesetzt}."
log "Warte bis zu ${KIOSK_WAIT_TIMEOUT_SEC}s auf das Dashboard unter $KIOSK_HEALTH_URL."

SECONDS=0
next_log_sec=10
while ! dashboard_ready; do
  if (( SECONDS >= KIOSK_WAIT_TIMEOUT_SEC )); then
    fail "Dashboard ist nach ${KIOSK_WAIT_TIMEOUT_SEC}s nicht erreichbar: $KIOSK_HEALTH_URL"
  fi

  if (( SECONDS >= next_log_sec )); then
    log "Dashboard noch nicht erreichbar (${SECONDS}s vergangen)."
    next_log_sec=$((next_log_sec + 10))
  fi

  sleep 1
done

log "Dashboard ist erreichbar. Starte Chromium im Kiosk-Modus: $KIOSK_URL"
exec "$BROWSER" \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --no-first-run \
  --start-maximized \
  "$KIOSK_URL"
