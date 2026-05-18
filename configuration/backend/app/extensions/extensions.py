from flask_cors import CORS
from flask_mqtt import Mqtt
from apscheduler.schedulers.background import BackgroundScheduler

cors = CORS()
mqtt = Mqtt()

scheduler = BackgroundScheduler({
    "apscheduler.timezone": "Europe/Berlin",
    "apscheduler.job_defaults.coalesce": True,
    "apscheduler.job_defaults.max_instances": 1,
})
