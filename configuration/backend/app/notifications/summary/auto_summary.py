def fmt_float(v):
    try:
        return round(float(v), 1)
    except:
        return "-"

def fmt_percent(v):
    return f"{fmt_float(v)}%" if v is not None else "-"

def fmt_temp(v):
    return f"{fmt_float(v)}°C" if v is not None else "-"

def fmt_duration(seconds):
    try:
        if seconds is None:
            return "-"
        seconds = int(seconds)

        if seconds < 3600:
            return f"{round(seconds/60)}min"
        else:
            h = seconds // 3600
            return f"{h}h"
    except:
        return "-"

def build_auto_summary(ctx):
    duration = None
    if ctx.auto_start:
        duration = int(ctx.now - ctx.auto_start.timestamp())

    msg = (
        f"📊 Auto Übersicht\n\n"
        f"⏱ Laufzeit: {fmt_duration(duration)}\n"
        f"🌀 Lüfterlaufzeit: {fmt_float(ctx.fan_runtime_auto)}h\n\n"
        f"🌾 TS min: {fmt_float(ctx.tsMin)}%\n"
        f"🎯 TS target: {fmt_float(ctx.tsSoll)}%\n"
    )

    return msg