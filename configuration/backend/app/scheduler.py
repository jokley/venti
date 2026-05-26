from .extensions.extensions import scheduler
# from .services.venti_service import venti_control
from .controller.venti.controller import venti_control
from .controller.venti.controller_Heizung import heizung_control


VENTI_CONTROL_INTERVAL_MINUTES = 4
HEIZUNG_CONTROL_INTERVAL_MINUTES = 1


def start_scheduler():

    if not scheduler.running:
        scheduler.add_job(
            venti_control,
            "interval",
            minutes=VENTI_CONTROL_INTERVAL_MINUTES,
            id="venti_control",
            replace_existing=True
        )
        scheduler.add_job(
            heizung_control,
            "interval",
            minutes=HEIZUNG_CONTROL_INTERVAL_MINUTES,
            id="heizung_control",
            replace_existing=True
        )

        scheduler.start()
