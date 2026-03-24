def build_message(decision):
    reason = decision.reason

    if reason == "OVERHEAT":
        return "🔥 Überhitzung – Lüfter EIN"

    elif reason == "STOCK_BUILD":
        return "🌾 Stockaufbau aktiv"

    elif reason == "DRYING":
        return "💨 Trocknung läuft"

    elif reason == "DRYING_STOP":
        return "✅ Trocknung fertig"

    elif reason == "INTERVAL":
        return "⏱ Intervalllüftung"

    elif reason == "AUTO_DISABLED":
        return "🛑 Automatik beendet"

    elif reason == "DEFAULT_OFF":
        return "😴 Lüfter aus"

    return f"ℹ️ Status: {reason}"