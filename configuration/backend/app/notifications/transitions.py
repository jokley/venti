last_state = {
    "command": None,
    "reason": None
}

def detect_transition(decision):
    global last_state

    changed = (
        decision.command != last_state.get("command") or
        decision.reason != last_state.get("reason")
    )

    if changed:
        prev = last_state.copy()

        last_state["command"] = decision.command
        last_state["reason"] = decision.reason

        return True, prev

    # ✅ ALWAYS return something
    return False, None