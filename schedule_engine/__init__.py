"""
Schedule Engine Module — Computes daily available hours based on user
settings, Chinese holidays, and (future) calendar events.

Usage:
    from schedule_engine import ScheduleEngine, DailySlot

    engine = ScheduleEngine(workday_hours=2.0, weekend_hours=6.0)
    slots = engine.generate("2026-05-20", "2026-06-01")
    for date, slot in slots.items():
        print(date, slot.available_hours, slot.is_holiday)
"""

from schedule_engine.engine import ScheduleEngine
from schedule_engine.models import DailySlot, UserSettings

__all__ = ["ScheduleEngine", "DailySlot", "UserSettings"]
