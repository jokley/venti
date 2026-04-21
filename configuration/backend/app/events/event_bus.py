from enum import Enum
from dataclasses import dataclass
from typing import Callable, List, Dict
from app.utils.logger import logger

class EventType(Enum):
    TRANSITION = "transition"
    DECISION_LOG = "decision_log"
    SYSTEM_ALERT = "system_alert"
    DAILY_SUMMARY = "daily_summary"

@dataclass
class Event:
    type: EventType
    data: dict

class EventBus:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.handlers: Dict[EventType, List[Callable]] = {}
        return cls._instance
    
    def subscribe(self, event_type: EventType, handler: Callable):
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
        logger.debug(f"Handler subscribed to {event_type}")
    
    def publish(self, event: Event):
        logger.debug(f"Publishing event: {event.type}")
        handlers = self.handlers.get(event.type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in event handler: {e}")

event_bus = EventBus()