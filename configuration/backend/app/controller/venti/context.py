class VentiContext:

    def __init__(self, d):
        self.mode = d["mode"]

        self.tempMax = d["tempMax"]

        self.sDefOut = d["sDefOut"]
        self.sDefMin = d["sDefMin"]

        self.tsMin = d["tsMin"]
        self.tsSoll = d["tsSoll"]

        self.remainingTimeStock = d["remainingTimeStock"]
        self.stock = d["stock"]

        self.humMax = d["humMax"]

        self.sdef_on = d["sdef_on"]
        self.sdef_hys_half = d["sdef_hys_half"]
        self.sdefMinThreshold = d["sdefMinThreshold"]

        self.ts_hys_half = d["ts_hys_half"]

        self.intervall_on = d["intervall_on"]
        self.remainingTimeInterval = d["remainingTimeInterval"]
        self.remainingTimeIntervalOn = d["remainingTimeIntervalOn"]
        self.remainingTimeIntervalDiff = d["remainingTimeIntervalDiff"]

        self.intervall_time = d["intervall_time"]
        self.intervall_duration = d["intervall_duration"]

        self.uschutz_on = d["uschutz_on"]
        self.uschutz_hys = d["uschutz_hys"]