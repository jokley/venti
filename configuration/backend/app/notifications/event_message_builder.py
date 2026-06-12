# =========================
# 🔧 FORMAT HELPERS
# =========================

def fmt_float(value, digits=1):
    if value is None:
        return "-"
    try:
        return round(float(value), digits)
    except Exception:
        return value


def fmt_temp(value):
    v = fmt_float(value)
    return f"{v}°C" if v != "-" else "-"


def fmt_percent(value):
    v = fmt_float(value)
    return f"{v}%" if v != "-" else "-"


def fmt_duration(seconds):
    try:
        if seconds is None:
            return "-"
        seconds = int(seconds)
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{round(seconds / 60)}min"
        else:
            h = seconds // 3600
            m = (seconds % 3600) // 60
            return f"{h}h {m}min"
    except Exception:
        return str(seconds)


# =========================
# 🧠 HUMAN READABLE TEXT
# =========================

def pretty_reason(reason):
    mapping = {
        "INTERVAL_ACTIVE":    "Intervalllüftung",
        "DRYING_ACTIVE":      "Trocknung",
        "STOCK_BUILDING":     "Stockaufbau",
        "OVERHEAT":           "Überhitzung",
        "AUTO_IDLE":          "Automatik pausiert",
        "MANUAL_MODE":        "Manueller Modus",
        "VENTI_MANUAL_ON":    "Lüfter Hand ein",
        "VENTI_MANUAL_OFF":   "Lüfter Hand aus",
        "INEFFICIENT_DRYING": "Ineffiziente Trocknung",
        "HEIZUNG_ACTIVE":     "Heizung aktiv",
        "HEIZUNG_MANUAL_ON":  "Heizung Hand ein",
        "HEIZUNG_MANUAL_OFF": "Heizung Hand aus",
        "HEIZUNG_NACHLAUF":   "Heizung Nachlauf",
        "HEIZUNG_SDEF_LIMIT": "Heizung SDEF Limit",
        "HEIZUNG_IDLE":       "Heizung inaktiv",
        "HEIZUNG_DISABLED":   "Heizung deaktiviert",
    }
    return mapping.get(reason, reason)


def pretty_detail_reason(reason):
    mapping = {
        "drying_conditions_not_met": "Trocknung nicht möglich",
        "inefficient_near_target":   "Trocknung ineffizient – Endphase",
        "auto_disabled":             "Trocknung abgeschlossen – Automatik deaktiviert",
        "drying_delay":              "Delay nach Trocknungs-Aus",
        "sdef_delay":                "Delay nach SDEF-Aus",
        "humidity_low":              "Feuchte zu niedrig",
        "ts_target_reached":         "TS Ziel erreicht",
        "interval_wait":             "Warte auf Intervall",
        None:                        "Kein spezieller Grund",
    }
    return mapping.get(reason, reason)


# States die keinen "gestartet"-Suffix brauchen (Stopp- oder Idle-Zustände)
_NO_STARTED_SUFFIX = {
    "AUTO_IDLE",
    "INEFFICIENT_DRYING",
    "HEIZUNG_IDLE",
    "HEIZUNG_DISABLED",
    "HEIZUNG_MANUAL_OFF",
    "VENTI_MANUAL_OFF",
}

# Übergänge die reine Mechanik abbilden und keinen Mehrwert für den User haben.
# Format: (old, new) → None unterdrückt die Meldung komplett.
_SUPPRESS_TRANSITIONS = {
    # Delay abgelaufen nach ineffizienter Trocknung – bereits bei
    # INEFFICIENT_DRYING mit Delay-Zeit kommuniziert.
    ("INEFFICIENT_DRYING", "AUTO_IDLE"),
    # Nachlauf-Ende → Heizung inaktiv ist reine Mechanik,
    # der User wurde bereits beim Nachlauf-Start informiert.
    ("HEIZUNG_NACHLAUF",   "HEIZUNG_IDLE"),
    ("HEIZUNG_NACHLAUF",   "HEIZUNG_DISABLED"),
}


# =========================
# 🔔 STATE MESSAGE (optional / debug)
# =========================

def build_message(decision):
    """Optional: only for debugging / logs. Main system uses build_event_message."""
    state = decision.reason
    d = decision.details or {}

    if state == "OVERHEAT":
        return (
            f"🔥 Überhitzung aktiv\n"
            f"🌡 Temp: {fmt_temp(d.get('tempMax'))} "
            f"(Limit: {fmt_temp(d.get('threshold'))}, Δ {fmt_float(d.get('diff'))})"
        )
    elif state == "STOCK_BUILDING":
        return (
            f"🌾 Stockaufbau aktiv\n"
            f"⏳ Restzeit: {fmt_duration(d.get('restzeit'))}\n"
            f"📦 {d.get('remaining')} / {d.get('stock')}"
        )
    elif state == "INTERVAL_ACTIVE":
        return (
            f"⏱ Intervall aktiv\n"
            f"💧 Feuchte: {fmt_percent(d.get('humMax'))}\n"
            f"📉 Limit: {fmt_percent(d.get('threshold'))}"
        )
    elif state == "DRYING_ACTIVE":
        return (
            f"💨 Trocknung läuft\n"
            f"🌬 SDef: {fmt_float(d.get('sDefOut'))} (Δ {fmt_float(d.get('sDefDiff'))})\n"
            f"📉 TS Diff: {fmt_float(d.get('tsDiff'))}"
        )
    elif state in ("HEIZUNG_ACTIVE", "HEIZUNG_MANUAL_ON"):
        return (
            f"🔥 Heizung läuft\n"
            f"⏳ Restzeit: {fmt_duration(d.get('remaining'))}"
        )
    elif state == "HEIZUNG_NACHLAUF":
        return (
            f"🌡 Heizung Nachlauf\n"
            f"⏳ Noch: {fmt_duration(d.get('nachlauf_remaining'))}"
        )
    elif state == "HEIZUNG_SDEF_LIMIT":
        msg = (
            f"🔥 Heizung SDEF Limit\n"
            f"🌬 SDef: {fmt_float(d.get('sDefOut'))}\n"
            f"📈 Limit: {fmt_float(d.get('heizung_sdef_limit'))}"
        )
        if d.get("delay_remaining") is not None:
            msg += f"\n⏳ Delay: {fmt_duration(d.get('delay_remaining'))}"
        return msg
    elif state in ("HEIZUNG_IDLE", "HEIZUNG_DISABLED", "HEIZUNG_MANUAL_OFF"):
        return "Heizung inaktiv"
    elif state == "AUTO_IDLE":
        return "😴 Automatik pausiert"
    elif state == "VENTI_MANUAL_ON":
        return "Lüfter Hand ein"
    elif state == "VENTI_MANUAL_OFF":
        return "Lüfter Hand aus"
    elif state == "MANUAL_MODE":
        if d.get("reason") == "auto_disabled":
            return (
                "🛑 Trocknung abgeschlossen – Automatik deaktiviert\n"
                f"📌 Grund: {pretty_detail_reason(d.get('reason'))}\n"
                f"📉 TS Diff: {fmt_float(d.get('tsDiff'))}"
            )
        return "🛑 Manueller Modus"
    return f"ℹ️ Status: {state}"


# =========================
# 🔄 EVENT MESSAGE (MAIN)
# =========================

def build_event_message(event):
    etype = event[0]
    if etype != "STATE_CHANGE":
        return None

    old, new, duration, data = event[1], event[2], event[3], event[4]

    # Mechanische Folge-Übergänge unterdrücken – kein Mehrwert für den User.
    if (old, new) in _SUPPRESS_TRANSITIONS:
        return None

    old_d = data.get("old_details") or {}
    new_d = data.get("new_details") or {}

    msg = _build_old_block(old, new, old_d, duration)
    msg += _build_new_block(new, new_d)
    return msg


def _build_old_block(old, new, old_d, duration):
    """Beschreibt den beendeten Zustand."""

    if old == "DRYING_ACTIVE":
        return (
            f"✅ Trocknung beendet\n"
            f"⏱ Dauer: {fmt_duration(duration)}\n"
            f"🌬 SDef: {fmt_float(old_d.get('sDefOut'))}\n"
            f"📉 TS Diff: {fmt_float(old_d.get('tsDiff'))}\n\n"
        )

    elif old == "INEFFICIENT_DRYING":
        # Werte kommen aus old_d – nicht new_d!
        msg = (
            f"⚠️ Ineffiziente Trocknung beendet\n"
            f"⏱ Laufzeit: {fmt_duration(old_d.get('runtime'))}\n"
            f"🌬 SDef Δ 2h: {fmt_float(old_d.get('sdef_change_2h'))}\n"
            f"📉 TS Δ 2h: {fmt_float(old_d.get('ts_change_2h'))}\n"
        )
        if old_d.get("weighted_gain") is not None:
            msg += f"⚖️ Gewichtet: {fmt_float(old_d.get('weighted_gain'), 3)}\n"
        msg += (
            f"📊 Effizienz: {fmt_float(old_d.get('efficiency'), 3)} "
            f"(Limit: {fmt_float(old_d.get('min_efficiency_threshold'), 3)})\n\n"
        )
        return msg

    elif old == "INTERVAL_ACTIVE":
        return (
            f"⏱ Intervall beendet\n"
            f"⏱ Dauer: {fmt_duration(duration)}\n"
            f"💧 Feuchte: {fmt_percent(old_d.get('humMax'))}\n\n"
        )

    elif old == "STOCK_BUILDING":
        return (
            f"🌾 Stockaufbau beendet\n"
            f"⏱ Dauer: {fmt_duration(duration)}\n"
            f"⏳ Restzeit: {fmt_duration(old_d.get('restzeit'))}\n\n"
        )

    elif old == "OVERHEAT":
        return (
            f"🔥 Überhitzung beendet\n"
            f"⏱ Dauer: {fmt_duration(duration)}\n\n"
        )

    elif old in ("HEIZUNG_ACTIVE", "HEIZUNG_MANUAL_ON"):
        if new == "HEIZUNG_NACHLAUF":
            # Heizung → Nachlauf: Dauer in die Nachlauf-Meldung integrieren,
            # kein separater "Heizung beendet"-Block nötig.
            return f"🔥 Heizung beendet (Dauer: {fmt_duration(duration)})\n"
        return (
            f"🔥 Heizung beendet\n"
            f"⏱ Dauer: {fmt_duration(duration)}\n\n"
        )

    elif old == "HEIZUNG_NACHLAUF":
        # HEIZUNG_NACHLAUF → HEIZUNG_IDLE/DISABLED wird via _SUPPRESS_TRANSITIONS
        # bereits unterdrückt. Dieser Block greift nur bei unerwarteten Folge-States.
        return (
            f"🌡 Heizung Nachlauf beendet\n"
            f"⏱ Dauer: {fmt_duration(duration)}\n\n"
        )

    return ""


def _build_new_block(new, new_d):
    """Beschreibt den neu gestarteten Zustand."""
    suffix = "" if new in _NO_STARTED_SUFFIX else " gestartet"
    msg = f"➡️ {pretty_reason(new)}{suffix}\n"

    if new == "DRYING_ACTIVE":
        msg += (
            f"🌬 SDef Δ: {fmt_float(new_d.get('sDefDiff'))}\n"
            f"🌬 SDef: {fmt_float(new_d.get('sDefOut'))} "
            f"(Min: {fmt_float(new_d.get('sDefMin'))})\n"
            f"📉 TS Diff: {fmt_float(new_d.get('tsDiff'))}\n"
            f"📊 Effizienz: {fmt_float(new_d.get('efficiency'), 3)} "
            f"(Limit: {fmt_float(new_d.get('min_efficiency_threshold'), 3)})"
        )

    elif new == "INEFFICIENT_DRYING":
        msg += (
            f"⏱ Laufzeit: {fmt_duration(new_d.get('runtime'))}\n"
            f"🌬 SDef Δ 2h: {fmt_float(new_d.get('sdef_change_2h'))}\n"
            f"📉 TS Δ 2h: {fmt_float(new_d.get('ts_change_2h'))}\n"
        )
        if new_d.get("weighted_gain") is not None:
            msg += f"⚖️ Gewichtet: {fmt_float(new_d.get('weighted_gain'), 3)}\n"
        msg += (
            f"📊 Effizienz: {fmt_float(new_d.get('efficiency'), 3)} "
            f"(Limit: {fmt_float(new_d.get('min_efficiency_threshold'), 3)})\n"
            f"⏳ Pause: {fmt_duration(new_d.get('delay_remaining'))}"
        )

    elif new == "INTERVAL_ACTIVE":
        msg += (
            f"💧 Feuchte: {fmt_percent(new_d.get('humMax'))}\n"
            f"📉 Limit: {fmt_percent(new_d.get('threshold'))}\n"
            f"🕒 Pause: {fmt_duration(new_d.get('remaining_off_time'))}"
        )
        if new_d.get("remaining") is not None:
            msg += f"\n⏳ Restzeit: {fmt_duration(new_d.get('remaining'))}"

    elif new == "STOCK_BUILDING":
        msg += (
            f"🌾 Ziel: {fmt_duration(new_d.get('stock'))}\n"
            f"⏳ Restzeit: {fmt_duration(new_d.get('restzeit'))}"
        )

    elif new == "AUTO_IDLE":
        msg += f"📌 Grund: {pretty_detail_reason(new_d.get('reason'))}\n"
        if new_d.get("sDefOut") is not None:
            msg += f"🌬 SDef: {fmt_float(new_d.get('sDefOut'))}\n"
        if new_d.get("tsDiff") is not None:
            msg += f"📉 TS Diff: {fmt_float(new_d.get('tsDiff'))}\n"
        if new_d.get("efficiency") is not None:
            msg += (
                f"📊 Effizienz: {fmt_float(new_d.get('efficiency'), 3)} "
                f"(Limit: {fmt_float(new_d.get('min_efficiency_threshold'), 3)})\n"
            )
        if new_d.get("delay_remaining") is not None:
            label = "Delay gestartet" if new_d.get("delay_started") else "Delay"
            msg += f"⏳ {label}: {fmt_duration(new_d.get('delay_remaining'))}\n"

    elif new == "MANUAL_MODE":
        detail_reason = new_d.get("reason")
        if detail_reason == "auto_disabled":
            msg += (
                f"📌 Grund: {pretty_detail_reason(detail_reason)}\n"
                f"⏱ Auto AUS seit: {fmt_duration(new_d.get('auto_off_after_seconds'))}\n"
                f"📉 TS Diff: {fmt_float(new_d.get('tsDiff'))}"
            )
            if new_d.get("previous_decision_reason") is not None:
                msg += f"\n↩ Vorherige Entscheidung: {pretty_reason(new_d.get('previous_decision_reason'))}"
        else:
            msg += (
                f"⏱ Laufzeit: {fmt_duration(new_d.get('runtime'))}\n"
                f"📉 TS Diff: {fmt_float(new_d.get('tsDiff'))}"
            )

    elif new in ("VENTI_MANUAL_ON", "VENTI_MANUAL_OFF"):
        msg += (
            f"⏱ Laufzeit: {fmt_duration(new_d.get('runtime'))}\n"
            f"📉 TS Diff: {fmt_float(new_d.get('tsDiff'))}"
        )

    elif new == "OVERHEAT":
        msg += (
            f"🌡 Temp: {fmt_temp(new_d.get('tempMax'))}\n"
            f"📈 Limit: {fmt_temp(new_d.get('threshold'))}\n"
            f"Δ {fmt_float(new_d.get('diff'))}"
        )

    elif new in ("HEIZUNG_ACTIVE", "HEIZUNG_MANUAL_ON"):
        msg += (
            f"⚙️ Modus: {new_d.get('heizung_mode', '-')}\n"
            f"⏳ Restzeit: {fmt_duration(new_d.get('remaining'))}"
        )

    elif new == "HEIZUNG_NACHLAUF":
        msg += (
            f"⏳ Noch: {fmt_duration(new_d.get('nachlauf_remaining'))}\n"
            f"⏱ Gesamt: {fmt_duration(new_d.get('heizung_nachlauf'))}"
        )

    elif new == "HEIZUNG_SDEF_LIMIT":
        msg += (
            f"🌬 SDef: {fmt_float(new_d.get('sDefOut'))}\n"
            f"📈 Limit: {fmt_float(new_d.get('heizung_sdef_limit'))}\n"
            f"↩ Hysterese: {fmt_float(new_d.get('heizung_sdef_hys'))}"
        )
        if new_d.get("delay_remaining") is not None:
            msg += f"\n⏳ Delay: {fmt_duration(new_d.get('delay_remaining'))}"

    elif new in ("HEIZUNG_IDLE", "HEIZUNG_DISABLED", "HEIZUNG_MANUAL_OFF"):
        msg += f"⚙️ Modus: {new_d.get('heizung_mode', '-')}"

    else:
        msg += (
            f"🌡 Temp: {fmt_temp(new_d.get('tempMax'))}\n"
            f"💧 Feuchte: {fmt_percent(new_d.get('humMax'))}"
        )

    return msg
