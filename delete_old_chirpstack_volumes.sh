#!/bin/bash

echo "🧹 Cleaning up old 'chirpstack_*' Docker volumes..."

VOLUMES_TO_REMOVE=(
  chirpstack_postgresqldata
  chirpstack_redisdata
  chirpstack_influxdbv2
)

for volume in "${VOLUMES_TO_REMOVE[@]}"; do
  if docker volume inspect "$volume" > /dev/null 2>&1; then
    echo "🔻 Removing volume: $volume"
    docker volume rm "$volume"
  else
    echo "⚠️  Volume not found: $volume"
  fi
done

echo "✅ Old chirpstack volumes removed (if they existed)."
