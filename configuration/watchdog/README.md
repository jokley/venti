# Watchdog Service

Dieser Dienst überwacht Backend/Influx und startet Container kontrolliert neu.

## Priorität
1. Backend-Health prüfen und bei Fehler zuerst Backend neu starten.
2. Wenn Backend verfügbar ist, `/watchdog/status` auswerten.
3. Fallback: Influx-Health prüfen, falls Status-Route nicht erreichbar ist.

## Erwartete Backend-Response
`GET /watchdog/status`

```json
{
  "influx_ok": true,
  "panstamp_stream_ok": true
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
