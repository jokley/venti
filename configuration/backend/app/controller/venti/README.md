# Venti Controller

Der Venti-Controller trennt Eingabedaten, Metriken, Entscheidungen und
Seiteneffekte:

- `controller.py` baut den `VentiContext`, ruft die Decision Engine auf, schaltet
  den Lüfter, persistiert Zustände und veröffentlicht Events.
- `context.py` hält die Rohdaten und Defaultwerte des aktuellen Regelzyklus.
- `drying/drying_metrics.py` berechnet Trocknungsmetriken für Logs,
  Debugging und den statischen Endphasencheck.
- `drying/drying_decision_engine.py` enthält die fachliche Lüfterlogik.
- `heating/heating_metrics.py` berechnet abgeleitete Heizungszustände.
- `heating/heating_decision_engine.py` enthält die fachliche Heizungslogik.

## Decision-Reihenfolge

Die `DryingDecisionEngine` entscheidet in fester Priorität:

1. Manuelle Lüftermodi (`VENTI_MANUAL_ON`, `VENTI_MANUAL_OFF`)
2. Heizung aktiv oder Nachlauf
3. Überhitzungsschutz
4. Stockaufbau
5. Trocknung mit SDef-/TS-Hysterese
6. Intervalllüftung
7. Auto-Idle
8. Auto-Disable als Postprocessing, wenn die Trocknung abgeschlossen ist
9. Start des Venti-Drying-Delays als Postprocessing nach Ende eines Trocknungslaufs

Frühere Treffer gewinnen. Sicherheits- und manuelle Zustände übersteuern die
normale Trocknungs- und Intervalllogik.

## Self-Learning entfernt

Der frühere Self-Learning-Modus wurde entfernt. Es gibt keine adaptive Schwelle,
kein Bad-Drying-Gedächtnis und kein Retry-Blocking mehr. Die Lüftersteuerung
arbeitet wieder deterministisch mit den konfigurierten Parametern.

Die Effizienz wird weiterhin berechnet, aber nicht gelernt. Sie dient für:

- Logs und Persistenzdetails
- Benachrichtigungen
- den statischen Endphasencheck

## Statischer Effizienz-Endphasencheck

Während einer laufenden Trocknung kann die Engine in der Endphase mit
`INEFFICIENT_DRYING` stoppen. Der Check greift nur, wenn alle Bedingungen erfüllt
sind:

- der Lüfter läuft bereits,
- Historie für die Effizienzberechnung ist vorhanden,
- `efficiency < base_min_efficiency_threshold`,
- `tsSoll` und `tsMin` sind vorhanden,
- `tsSoll - tsMin < efficiency_endphase_ts_margin`.

`base_min_efficiency_threshold <= 0` deaktiviert diesen Check vollständig.
`efficiency_endphase_ts_margin` steuert nur, ab welchem Abstand zum Ziel die
Endphase beginnt.

## Venti-Drying-Delay

Der Venti-Drying-Delay ist eine Restart-Sperre nach Ende eines Trocknungslaufs.
Er ist kein Minimum-On-Timer. Die Engine startet den Delay, wenn vorher
`DRYING_ACTIVE` aktiv war und die neue Entscheidung wegen fehlender
Trocknungsbedingungen auf `AUTO_IDLE` fällt.

Während der Delay aktiv ist, blockiert er nur neue Trocknungsstarts.
Intervalllüftung, Überhitzung und Stockaufbau behalten Vorrang.

## Auto-Disable

Wenn Auto lange nichts mehr sinnvoll tun kann und die Trocknung praktisch
abgeschlossen ist, erzeugt die Engine eine `MANUAL_MODE`-Decision mit
`details["mode_override"] = "off"` und `details["reason"] = "auto_disabled"`.

Der Seiteneffekt `venti_auto("off", ctx.tsSoll, "0")` bleibt bewusst im
Controller. Die Benutzer-/Logmeldung lautet:

`Trocknung abgeschlossen – Automatik deaktiviert`

## Relevante Parameter

Die Venti-Parameter sind in `services/influx_service.py` definiert. Für die
Effizienz bleiben relevant:

- `efficiency_window_hours`
- `base_min_efficiency_threshold`
- `efficiency_endphase_ts_margin`
- `ts_weight`

Entfernt wurden:

- `self_learning_enabled`
- `good_drying_level`
- `efficiency_learning_up`
- `efficiency_learning_down`
