#!/usr/bin/env bash
set -Eeuo pipefail

VENTI_USER="${VENTI_USER:-pi}"

log() {
  printf '%s %s\n' "$(date --iso-8601=seconds)" "$*"
}

fail() {
  log "FEHLER: $*" >&2
  exit 1
}

[[ "$EUID" -eq 0 ]] || fail "Dieses Script muss mit sudo ausgeführt werden."
id "$VENTI_USER" >/dev/null 2>&1 || fail "Benutzer existiert nicht: $VENTI_USER"
command -v apt-get >/dev/null 2>&1 || fail "apt-get wurde nicht gefunden. Unterstützt wird Raspberry Pi OS beziehungsweise Debian."

log "Aktualisiere Paketlisten."
apt-get update

log "Installiere Voraussetzungen für das Docker-Repository."
apt-get install -y ca-certificates curl gnupg

install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg \
  | gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

. /etc/os-release
DOCKER_CODENAME="${VERSION_CODENAME:-}"
[[ -n "$DOCKER_CODENAME" ]] || fail "VERSION_CODENAME fehlt in /etc/os-release."

cat > /etc/apt/sources.list.d/docker.list <<EOF_REPOSITORY
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $DOCKER_CODENAME stable
EOF_REPOSITORY

log "Installiere Docker Engine und Docker Compose Plugin."
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

log "Füge $VENTI_USER zur Docker-Gruppe hinzu."
usermod -aG docker "$VENTI_USER"

systemctl enable --now docker

docker version >/dev/null
docker compose version >/dev/null

log "Docker und Docker Compose wurden installiert."
log "Die neue Docker-Gruppenmitgliedschaft gilt für $VENTI_USER nach einer erneuten Anmeldung oder einem Neustart."
