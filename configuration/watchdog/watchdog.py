import os
import time
from datetime import datetime, timezone

import docker
import requests


def now_ts() -> int:
    return int(time.time())


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(msg: str) -> None:
    print(f"[{iso_now()}] {msg}", flush=True)


CHECK_INTERVAL_SEC = int(os.getenv("CHECK_INTERVAL_SEC", "30"))
BACKEND_RECOVERY_WAIT_SEC = int(os.getenv("BACKEND_RECOVERY_WAIT_SEC", "30"))
COOLDOWN_SEC = int(os.getenv("COOLDOWN_SEC", "120"))
MAX_RESTARTS_PER_HOUR = int(os.getenv("MAX_RESTARTS_PER_HOUR", "4"))
BACKEND_MAX_RETRIES = int(os.getenv("BACKEND_MAX_RETRIES", "3"))

BACKEND_HEALTH_URL = os.getenv("BACKEND_HEALTH_URL", "http://backend:5000/healthz")
WATCHDOG_STATUS_URL = os.getenv("WATCHDOG_STATUS_URL", "http://backend:5000/watchdog/status")
INFLUX_HEALTH_URL = os.getenv("INFLUX_HEALTH_URL", "http://influxdb:8086/health")

PANSTAMP_SERVICE = os.getenv("PANSTAMP_SERVICE", "panstamp-i2c")
INFLUX_SERVICE = os.getenv("INFLUX_SERVICE", "influxdb")
BACKEND_SERVICE = os.getenv("BACKEND_SERVICE", "flask-backend")

last_restart_ts = {}
restart_events = []


def http_ok(url: str, timeout: float = 4.0) -> bool:
    try:
        response = requests.get(url, timeout=timeout)
        return 200 <= response.status_code < 300
    except Exception:
        return False


def get_watchdog_status() -> dict | None:
    try:
        response = requests.get(WATCHDOG_STATUS_URL, timeout=4.0)
        if response.status_code != 200:
            return None
        data = response.json()
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def in_cooldown(service: str) -> bool:
    return now_ts() - last_restart_ts.get(service, 0) < COOLDOWN_SEC


def restart_budget_ok() -> bool:
    one_hour_ago = now_ts() - 3600
    restart_events[:] = [e for e in restart_events if e["ts"] >= one_hour_ago]
    return len(restart_events) < MAX_RESTARTS_PER_HOUR


def safe_restart(client: docker.DockerClient, service: str, reason: str) -> tuple[bool, str]:
    if in_cooldown(service):
        return False, "cooldown"
    if not restart_budget_ok():
        return False, "budget_exceeded"

    try:
        container = client.containers.get(service)
        container.restart(timeout=10)
        last_restart_ts[service] = now_ts()
        restart_events.append({"ts": now_ts(), "service": service, "reason": reason})
        log(f"Restarted {service}: {reason}")
        return True, "restarted"
    except Exception as exc:
        log(f"Restart failed for {service}: {exc}")
        return False, "restart_failed"


def alert(message: str) -> None:
    log(f"ALERT: {message}")


def main() -> None:
    client = docker.from_env()
    log("watchdog started")

    while True:
        if not http_ok(BACKEND_HEALTH_URL):
            ok, why = safe_restart(client, BACKEND_SERVICE, "backend health down")
            if not ok and why == "budget_exceeded":
                alert("restart budget exceeded while backend is down")

            time.sleep(BACKEND_RECOVERY_WAIT_SEC)

            backend_up = False
            for _ in range(BACKEND_MAX_RETRIES):
                if http_ok(BACKEND_HEALTH_URL):
                    backend_up = True
                    break
                time.sleep(10)

            if not backend_up:
                alert("backend still down after retries")
                time.sleep(CHECK_INTERVAL_SEC)
                continue

        status = get_watchdog_status()
        if status is None:
            if not http_ok(INFLUX_HEALTH_URL):
                ok, why = safe_restart(client, INFLUX_SERVICE, "influx health down (fallback)")
                if not ok and why == "budget_exceeded":
                    alert("restart budget exceeded for influx fallback")
            time.sleep(CHECK_INTERVAL_SEC)
            continue

        if not status.get("influx_ok", True):
            ok, why = safe_restart(client, INFLUX_SERVICE, "influx not ok")
            if not ok and why == "budget_exceeded":
                alert("restart budget exceeded for influx")

        elif not status.get("panstamp_stream_ok", True):
            ok, why = safe_restart(client, PANSTAMP_SERVICE, "panstamp stream not ok")
            if not ok and why == "budget_exceeded":
                alert("restart budget exceeded for panstamp")

        time.sleep(CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    main()
