# Watchdog Service

Dieser Dienst überwacht Backend/Influx und startet Container kontrolliert neu.

## Image-Größe (Raspberry Pi)
- Das Image basiert auf `python:3.12-alpine`, um Build-Zeit und Größe zu reduzieren.
- Die genutzten Abhängigkeiten (`requests`, `docker`) sind reine Python-Pakete und laufen damit problemlos auf Alpine.

## Priorität
1. Backend-Health prüfen und bei Fehler zuerst Backend neu starten.
2. Wenn Backend verfügbar ist, `/watchdog/status` auswerten.
3. Fallback: Influx-Health prüfen, falls Status-Route nicht erreichbar ist.

## Erwartete Backend-Response
`GET /watchdog/status`

```json
{
  "influx_ok": true,
  "panstamp_mode": true,
  "panstamp_stream_ok": true,
  "panstamp_reason": "ok",
  "panstamp_threshold_sec": 300,
  "panstamp_sensor_count": 3,
  "panstamp_fresh_sensor_count": 2,
  "panstamp_oldest_age_sec": 420,
  "panstamp_youngest_age_sec": 24
}
```

## Schutz vor Restart-Loops
- Cooldown pro Container
- Max-Restarts pro Stunde
- Retry-Logik beim Backend

## Crash-Diagnose bei Backend-Ausfällen
- Bei fehlgeschlagenem Backend-Healthcheck protokolliert der Watchdog zusätzlich:
  - HTTP-Fehlergrund (Statuscode/Exception)
  - Container-State (`status`, `exit_code`, `oom_killed`, Zeitstempel, Docker-Error)
  - die letzten Backend-Logs (`tail=30`)
- Dadurch lässt sich besser unterscheiden, ob es ein echter Crash, OOM oder ein Hänger ist.
- Bei PANSTAMP-Stream-Fehlern werden zusätzlich konkrete Gründe mitgeloggt
  (z. B. `all_sensors_stale`, `no_sensor_age_data`, `sensor_age_fetch_failed`).
- Zusätzlich werden beim PANSTAMP-Fehlerfall auch Container-State und letzte
  PANSTAMP-Containerlogs (`tail=30`) ausgegeben, um Containerfehler von
  reinen Sensorausfällen besser zu trennen.

## Alert-Drosselung
- Wiederholte identische Alerts werden standardmäßig nur alle 15 Minuten geloggt
  (`ALERT_COOLDOWN_SEC=900`). Der normale Diagnose-Loop läuft weiter.

## Backend-Recheck vor Neustart
- Nach einem fehlgeschlagenen Backend-Healthcheck wartet der Watchdog standardmäßig
  2 Sekunden (`BACKEND_FAILURE_RECHECK_SEC=2`) und prüft erneut. Ein einzelner
  kurzzeitiger Timeout führt dadurch nicht sofort zu einem Backend-Neustart.
