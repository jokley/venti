#!/bin/bash

# Define volume name pairs
declare -A VOLUMES=(
  ["chirpstack_postgresqldata"]="venti_postgresqldata"
  ["chirpstack_redisdata"]="venti_redisdata"
  ["chirpstack_influxdbv2"]="venti_influxdbv2"
)

echo "🚀 Starting ChirpStack → Venti volume migration..."

for OLD_VOL in "${!VOLUMES[@]}"; do
  NEW_VOL="${VOLUMES[$OLD_VOL]}"

  echo "🔍 Checking volume: $OLD_VOL → $NEW_VOL"

  # Create new volume if it doesn't exist
  if ! docker volume inspect "$NEW_VOL" > /dev/null 2>&1; then
    echo "📦 Creating new volume: $NEW_VOL"
    docker volume create "$NEW_VOL"
  else
    echo "✅ Volume $NEW_VOL already exists"
  fi

  # Copy data from old to new
  echo "📁 Copying data from $OLD_VOL to $NEW_VOL..."
  docker run --rm \
    -v "$OLD_VOL:/from" \
    -v "$NEW_VOL:/to" \
    alpine sh -c "cd /from && cp -a . /to"

  echo "✅ Done copying $OLD_VOL → $NEW_VOL"
  echo "-------------------------------------------"
done

echo "🎉 All volumes migrated successfully!"
echo "📝 You can now start your Venti Docker Compose setup."
