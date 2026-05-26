"""
Schedule Engine — Orchestrates user settings + holidays → daily available hours.
"""

from datetime import date, timedelta
from typing import Optional

from schedule_engine.models import DailySlot, UserSettings
from schedule_engine.holiday_api import (
    is_workday,
    is_holiday,
    get_holiday_name,
    warmup_cache,
)

# Day-of-week abbreviations
_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class ScheduleEngine:
    """Computes daily available study hours for a date range.

    Layers (bottom to top):
        1. User base settings (workday/weekend/holiday hours)
        2. Holiday override (statutory holidays adjust base hours)
        3. Manual busy hours (user marks specific busy times per date)
        (Future: 4. Calendar events)

    Usage:
        engine = ScheduleEngine(
            UserSettings(workday_hours=2.0, weekend_hours=6.0)
        )
        slots = engine.generate("2026-05-20", "2026-06-01")
    """

    def __init__(self, settings: Optional[UserSettings] = None):
        self.settings = settings or UserSettings()

    def generate(
        self,
        start: str | date,
        end: str | date,
    ) -> dict[date, DailySlot]:
        """
        Generate daily slots for the given date range (inclusive).

        Args:
            start: Start date (ISO string "YYYY-MM-DD" or date object).
            end:   End date (ISO string or date object).

        Returns:
            Dict mapping date → DailySlot.
        """
        start_d = self._parse_date(start)
        end_d = self._parse_date(end)

        if start_d > end_d:
            raise ValueError(f"start ({start_d}) must be <= end ({end_d})")

        # Pre-fetch holiday data for the years in range
        warmup_cache(start_d, end_d)

        slots: dict[date, DailySlot] = {}
        current = start_d
        while current <= end_d:
            slots[current] = self._compute_slot(current)
            current += timedelta(days=1)

        return slots

    def _compute_slot(self, d: date) -> DailySlot:
        """Compute the DailySlot for a single date."""
        holiday = is_holiday(d)
        workday = is_workday(d)
        name = get_holiday_name(d) if holiday else ""

        # Layer 1: Base hours from user settings
        base = self.settings.get_base_hours(
            is_workday=workday,
            is_holiday=holiday,
        )

        # Layer 3: Manual busy hours
        date_key = d.isoformat()
        manual_busy = self.settings.manual_busy.get(date_key, 0.0)

        # Final available hours
        available = max(0.0, base - manual_busy)

        return DailySlot(
            date=d,
            day_of_week=_DAY_NAMES[d.weekday()],
            is_workday=workday,
            is_holiday=holiday,
            holiday_name=name,
            base_hours=base,
            manual_busy_hours=manual_busy,
            available_hours=available,
        )

    @staticmethod
    def _parse_date(d: str | date) -> date:
        if isinstance(d, date):
            return d
        return date.fromisoformat(d)


# ── Convenience function ────────────────────────────────────────────

def generate_schedule(
    start: str | date,
    end: str | date,
    workday_hours: float = 2.0,
    weekend_hours: float = 6.0,
    holiday_hours: float = 4.0,
    manual_busy: Optional[dict[str, float]] = None,
) -> dict[date, DailySlot]:
    """One-liner: generate daily schedule for a date range."""
    settings = UserSettings(
        workday_hours=workday_hours,
        weekend_hours=weekend_hours,
        holiday_hours=holiday_hours,
        manual_busy=manual_busy or {},
    )
    engine = ScheduleEngine(settings)
    return engine.generate(start, end)
