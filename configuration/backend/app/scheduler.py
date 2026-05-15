from .extensions.extensions import scheduler
# from .services.venti_service import venti_control
from .controller.venti.controller import venti_control
from .controller.venti.controller_Heizung import heizung_control






def start_scheduler():

    if not scheduler.running:
        scheduler.add_job(
            venti_control,
            "interval",
            minutes=4,
            id="venti_control",
            replace_existing=True
        )
        scheduler.add_job(
            heizung_control,
            "interval",
            minutes=1,
            id="heizung_control",
            replace_existing=True
        )

        scheduler.start()