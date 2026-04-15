BATTERY_WARNINGS = [30, 20, 10]


class BatteryAlertState:
    def __init__(self):
        self.last_level = {}   # device -> last bucket (30/20/10)


def check_battery_alerts(ctx, state):

    events = []

    for device, value in ctx.battery.items():

        if value is None:
            continue

        # determine bucket
        level = None
        if value <= 10:
            level = 10
        elif value <= 20:
            level = 20
        elif value <= 30:
            level = 30
        else:
            level = None

        last = state.last_level.get(device)

        # no repeated spam
        if level is None or level == last:
            continue

        state.last_level[device] = level

        events.append((
            "BATTERY_LOW",
            device,
            value,
            level
        ))

    return events