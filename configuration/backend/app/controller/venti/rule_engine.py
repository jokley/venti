rules = []

def rule(priority=100):
    def decorator(func):
        rules.append((priority, func))
        rules.sort(key=lambda r: r[0])
        return func
    return decorator