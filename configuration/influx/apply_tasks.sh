#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/venti.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing env file: ${ENV_FILE}" >&2
  exit 1
fi

env_file_value() {
  local key="$1"
  local line

  line="$(grep -E "^${key}=" "${ENV_FILE}" | tail -n 1 || true)"
  if [[ -n "${line}" ]]; then
    printf '%s' "${line#*=}"
  fi
}

env_or_file() {
  local key="$1"
  local default="${2:-}"
  local value="${!key:-}"

  if [[ -n "${value}" ]]; then
    printf '%s' "${value}"
    return
  fi

  value="$(env_file_value "${key}")"
  if [[ -n "${value}" ]]; then
    printf '%s' "${value}"
    return
  fi

  printf '%s' "${default}"
}

INFLUX_ORG="$(env_or_file DOCKER_INFLUXDB_INIT_ORG)"
INFLUX_TOKEN="$(env_or_file DOCKER_INFLUXDB_INIT_ADMIN_TOKEN)"
SOURCE_BUCKET="$(env_or_file DOCKER_INFLUXDB_INIT_BUCKET jokley_bucket)"
if [[ -z "${INFLUX_ORG}" ]]; then
  echo "DOCKER_INFLUXDB_INIT_ORG missing" >&2
  exit 1
fi
if [[ -z "${INFLUX_TOKEN}" ]]; then
  echo "DOCKER_INFLUXDB_INIT_ADMIN_TOKEN missing" >&2
  exit 1
fi
INFLUX_HOST="${INFLUX_HOST:-http://localhost:8086}"
DOCKER_COMPOSE="${DOCKER_COMPOSE:-docker compose}"
MODE="${1:-apply}"
TASK_DIR="${SCRIPT_DIR}/tasks"
BUCKET_1H="$(env_or_file INFLUX_DOWNSAMPLE_1H_BUCKET jokley_1h)"
BUCKET_1D="$(env_or_file INFLUX_DOWNSAMPLE_1D_BUCKET jokley_1d)"
RETENTION_1H="$(env_or_file INFLUX_DOWNSAMPLE_1H_RETENTION 4320h)"
RETENTION_1D="$(env_or_file INFLUX_DOWNSAMPLE_1D_RETENTION 0)"
CONTAINER_TASK_DIR="/tmp/influx-provisioning"
BACKFILL_START="${BACKFILL_START:-}"
BACKFILL_STOP="${BACKFILL_STOP:-}"
BACKFILL_CHUNK_DAYS="${BACKFILL_CHUNK_DAYS:-31}"

TASKS=(
  "jokley_sensor_1h_downsample:sensor_1h.flux"
  "jokley_sensor_1d_downsample:sensor_1d.flux"
  "jokley_relay_1h_downsample:relay_1h.flux"
  "jokley_relay_1d_downsample:relay_1d.flux"
)

BACKFILL_QUERIES=(
  "backfill_sensor_1h.flux"
  "backfill_sensor_1d.flux"
  "backfill_relay_1h.flux"
  "backfill_relay_1d.flux"
)

case "${MODE}" in
  apply|--check|check|backfill|backfill-sensor-1h|backfill-sensor-1d|backfill-relay-1h|backfill-relay-1d) ;;
  *)
    echo "Usage: $0 [apply|--check|check|backfill|backfill-sensor-1h|backfill-sensor-1d|backfill-relay-1h|backfill-relay-1d]" >&2
    exit 1
    ;;
esac

run_influx() {
  ${DOCKER_COMPOSE} exec -T \
    -e INFLUX_HOST="${INFLUX_HOST}" \
    -e INFLUX_ORG="${INFLUX_ORG}" \
    -e INFLUX_TOKEN="${INFLUX_TOKEN}" \
    influxdb influx "$@"
}

render_task_to_container() {
  local source_file="$1"
  local container_file="$2"
  local rendered_file

  rendered_file="$(mktemp)"
  sed \
    -e "s/__SOURCE_BUCKET__/${SOURCE_BUCKET}/g" \
    -e "s/__BUCKET_1H__/${BUCKET_1H}/g" \
    -e "s/__BUCKET_1D__/${BUCKET_1D}/g" \
    -e "s/__BACKFILL_START__/${BACKFILL_START}/g" \
    -e "s/__BACKFILL_STOP__/${BACKFILL_STOP}/g" \
    "${source_file}" > "${rendered_file}"

  ${DOCKER_COMPOSE} exec -T influxdb sh -c "mkdir -p '${CONTAINER_TASK_DIR}' && cat > '${container_file}'" < "${rendered_file}"
  rm -f "${rendered_file}"
}

bucket_exists() {
  local bucket_name="$1"
  local output

  if ! output="$(run_influx bucket list --name "${bucket_name}" 2>/dev/null)"; then
    return 1
  fi

  echo "${output}" | awk 'NR > 1 {print $2}' | grep -Fxq "${bucket_name}"
}

bucket_id_by_name() {
  local bucket_name="$1"
  local output

  output="$(run_influx bucket list --name "${bucket_name}" 2>/dev/null || true)"
  echo "${output}" | awk -v name="${bucket_name}" 'NR > 1 && $2 == name {print $1; exit}'
}

ensure_bucket() {
  local bucket_name="$1"
  local retention="$2"
  local bucket_id

  if bucket_exists "${bucket_name}"; then
    echo "Bucket exists: ${bucket_name}; updating retention=${retention}"
    bucket_id="$(bucket_id_by_name "${bucket_name}")"
    if [[ -z "${bucket_id}" ]]; then
      echo "Could not find bucket ID for ${bucket_name}" >&2
      exit 1
    fi
    run_influx bucket update --id "${bucket_id}" --retention "${retention}" >/dev/null
    return
  fi

  echo "Creating bucket: ${bucket_name} (retention=${retention})"
  run_influx bucket create --name "${bucket_name}" --retention "${retention}"
}

task_id_by_name() {
  local task_name="$1"
  local output

  output="$(run_influx task list 2>/dev/null || true)"
  echo "${output}" | awk -v name="${task_name}" 'NR > 1 && $2 == name {print $1; exit}'
}

print_task_by_name() {
  local task_name="$1"
  run_influx task list \
    | awk -v name="${task_name}" 'NR == 1 || $2 == name {print}'
}

apply_task() {
  local task_name="$1"
  local task_file="$2"
  local task_id

  task_id="$(task_id_by_name "${task_name}")"

  if [[ -n "${task_id}" ]]; then
    echo "Updating task: ${task_name} (${task_id})"
    run_influx task update --id "${task_id}" --file "${task_file}"
  else
    echo "Creating task: ${task_name}"
    run_influx task create --file "${task_file}"
  fi
}

render_named_file() {
  local file_name="$1"
  render_task_to_container "${TASK_DIR}/${file_name}" "${CONTAINER_TASK_DIR}/${file_name}"
}

apply_named_task() {
  local task_spec="$1"
  local task_name="${task_spec%%:*}"
  local file_name="${task_spec#*:}"

  render_named_file "${file_name}"
  apply_task "${task_name}" "${CONTAINER_TASK_DIR}/${file_name}"
}

run_query_file() {
  local file_name="$1"

  render_named_file "${file_name}"
  echo "Running backfill query: ${file_name}"
  run_influx query --file "${CONTAINER_TASK_DIR}/${file_name}"
}

iso_utc() {
  date -u -d "@$1" +"%Y-%m-%dT%H:%M:%SZ"
}

date_to_epoch() {
  date -u -d "$1" +"%s"
}

init_backfill_window() {
  if [[ -z "${BACKFILL_START}" ]]; then
    BACKFILL_START="$(date -u -d "180 days ago" +"%Y-%m-%dT00:00:00Z")"
  fi

  if [[ -z "${BACKFILL_STOP}" ]]; then
    BACKFILL_STOP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  fi
}

run_chunked_backfill() {
  local query_file="$1"
  local original_start="${BACKFILL_START}"
  local original_stop="${BACKFILL_STOP}"
  local start_epoch stop_epoch chunk_seconds current_epoch next_epoch

  init_backfill_window

  start_epoch="$(date_to_epoch "${BACKFILL_START}")"
  stop_epoch="$(date_to_epoch "${BACKFILL_STOP}")"
  chunk_seconds=$((BACKFILL_CHUNK_DAYS * 24 * 60 * 60))

  if (( start_epoch >= stop_epoch )); then
    echo "Invalid backfill window: BACKFILL_START must be before BACKFILL_STOP" >&2
    exit 1
  fi

  current_epoch="${start_epoch}"
  while (( current_epoch < stop_epoch )); do
    next_epoch=$((current_epoch + chunk_seconds))
    if (( next_epoch > stop_epoch )); then
      next_epoch="${stop_epoch}"
    fi

    BACKFILL_START="$(iso_utc "${current_epoch}")"
    BACKFILL_STOP="$(iso_utc "${next_epoch}")"
    echo "Backfill chunk: ${query_file} ${BACKFILL_START} -> ${BACKFILL_STOP}"
    run_query_file "${query_file}"

    current_epoch="${next_epoch}"
  done

  BACKFILL_START="${original_start}"
  BACKFILL_STOP="${original_stop}"
}

backfill_query_files_for_mode() {
  case "$1" in
    backfill-sensor-1h) echo "backfill_sensor_1h.flux" ;;
    backfill-sensor-1d) echo "backfill_sensor_1d.flux" ;;
    backfill-relay-1h) echo "backfill_relay_1h.flux" ;;
    backfill-relay-1d) echo "backfill_relay_1d.flux" ;;
    backfill) printf "%s\n" "${BACKFILL_QUERIES[@]}" ;;
  esac
}

echo "Checking Influx CLI connectivity..."
run_influx ping >/dev/null

if [[ "${MODE}" == "--check" || "${MODE}" == "check" ]]; then
  echo "Influx CLI connectivity OK"
  echo
  echo "Bucket status:"
  for bucket in "${BUCKET_1H}" "${BUCKET_1D}"; do
    if bucket_exists "${bucket}"; then
      echo "OK      ${bucket}"
    else
      echo "MISSING ${bucket}"
    fi
  done
  echo
  echo "Task status:"
  for task_spec in "${TASKS[@]}"; do
    task_name="${task_spec%%:*}"
    task_id="$(task_id_by_name "${task_name}")"
    if [[ -n "${task_id}" ]]; then
      echo "OK      ${task_name} (${task_id})"
    else
      echo "MISSING ${task_name}"
    fi
  done
  exit 0
fi

ensure_bucket "${BUCKET_1H}" "${RETENTION_1H}"
ensure_bucket "${BUCKET_1D}" "${RETENTION_1D}"

if [[ "${MODE}" == backfill* ]]; then
  init_backfill_window
  echo "Backfilling downsample buckets from ${BACKFILL_START} to ${BACKFILL_STOP} in ${BACKFILL_CHUNK_DAYS}-day chunks"
  while IFS= read -r query_file; do
    [[ -n "${query_file}" ]] || continue
    run_chunked_backfill "${query_file}"
  done < <(backfill_query_files_for_mode "${MODE}")
  echo "Backfill complete"
  exit 0
fi

for task_spec in "${TASKS[@]}"; do
  apply_named_task "${task_spec}"
done

echo
echo "Provisioned buckets:"
run_influx bucket list --name "${BUCKET_1H}"
run_influx bucket list --name "${BUCKET_1D}"

echo
echo "Provisioned tasks:"
for task_spec in "${TASKS[@]}"; do
  print_task_by_name "${task_spec%%:*}"
done
