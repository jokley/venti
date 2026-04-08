# def build_message(decision):
#     reason = decision.reason

#     if reason == "OVERHEAT":
#         return "🔥 Überhitzung – Lüfter EIN"

#     elif reason == "STOCK_BUILD":
#         return "🌾 Stockaufbau aktiv"

#     elif reason == "AUTO_DISABLED":
#         return "🛑 Automatik beendet"

#     elif reason == "DRYING":
#         return "💨 Trocknung läuft"

#     elif reason == "DRYING_STOP":
#         return "✅ Trocknung fertig"

#     elif reason == "INTERVAL":
#         return "⏱ Intervalllüftung"
    
#     elif reason == "DEFAULT_OFF":
#         return "😴 Lüfter aus"

#     return f"ℹ️ Status: {reason}"

def fmt_float(value, digits=1):
    try:
        return round(float(value), digits)
    except:
        return value

def fmt_temp(value):
    return f"{fmt_float(value)}°C"

def fmt_percent(value):
    return f"{fmt_float(value)}%"

def fmt_duration(seconds):
    try:
        seconds = int(seconds)

        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{round(seconds / 60)}min"
        else:
            h = seconds // 3600
            m = (seconds % 3600) // 60
            return f"{h}h {m}min"
    except:
        return str(seconds)

def build_message(decision):
    reason = decision.reason
    d = decision.details or {}

    if reason == "OVERHEAT":
        return (
            f"🔥 Überhitzung – Lüfter EIN\n"
            f"🌡 Temp: {fmt_temp(d.get('tempMax'))} "
            f"(Limit: {fmt_temp(d.get('threshold'))}, Δ {fmt_float(d.get('diff'))})"
        )

    elif reason == "STOCK_BUILD":
        return (
            f"🌾 Stockaufbau aktiv\n"
            f"⏳ Restzeit: {fmt_duration(d.get('restzeit'))} | "
            f"Remaining: {d.get('remaining')} / {d.get('stock')}"
        )

    elif reason == "AUTO_DISABLED":
        return (
            f"🛑 Automatik beendet\n"
            f"⏱ Runtime: {fmt_duration(d.get('runtime'))}\n"
            f"📉 TS Diff: {fmt_float(d.get('tsDiff'))}"
        )

    elif reason == "INTERVAL":
        return (
            f"⏱ Intervalllüftung\n"
            f"💧 Hum: {fmt_percent(d.get('humMax'))} (Limit: {fmt_percent(d.get('threshold'))})\n"
            f"🕒 Seit letztem ON: {fmt_duration(d.get('since_last_on'))}"
        )

    elif reason == "DRYING":
        return (
            f"💨 Trocknung läuft\n"
            f"🌡 SDefOut: {fmt_float(d.get('sDefOut'))} | "
            f"Min: {fmt_float(d.get('sDefMin'))} (Δ {fmt_float(d.get('sDefDiff'))})\n"
            f"🌡 TS Diff: {fmt_float(d.get('tsDiff'))}"
        )

    elif reason == "DRYING_STOP":
        return (
            f"✅ Trocknung beendet\n"
            f"🌡 SDefOut: {fmt_float(d.get('sDefOut'))} (Threshold: {fmt_float(d.get('threshold'))})\n"
            f"🌡 TS Diff: {fmt_float(d.get('tsDiff'))}"
        )

    elif reason == "DEFAULT_OFF":
        return "😴 Lüfter aus (Default)"

    return f"ℹ️ Status: {reason}"