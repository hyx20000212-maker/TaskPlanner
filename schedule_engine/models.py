"""Data models for the schedule engine."""

from dataclasses import dataclass, field
from datetime import date


@dataclass
class DailySlot:
    """Available time slot for a single day."""
    date: date                          # The date
    day_of_week: str                    # "Mon" / "Tue" / ... / "Sun"
    is_workday: bool                    # True = workday, False = rest day
    is_holiday: bool                    # True = statutory holiday
    holiday_name: str = ""              # e.g. "Spring Festival" if holiday
    base_hours: float = 0.0             # Base hours from user settings
    manual_busy_hours: float = 0.0      # User-marked busy hours for this day
    available_hours: float = 0.0        # Final available study hours

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "day_of_week": self.day_of_week,
            "is_workday": self.is_workday,
            "is_holiday": self.is_holiday,
            "holiday_name": self.holiday_name,
            "base_hours": self.base_hours,
            "manual_busy_hours": self.manual_busy_hours,
            "available_hours": round(self.available_hours, 1),
        }

    def __repr__(self) -> str:
        flag = "🎌" if self.is_holiday else ("💼" if self.is_workday else "🏠")
        return (f"DailySlot({self.date} {self.day_of_week} {flag} "
                f"available={self.available_hours:.1f}h)")


@dataclass
class UserSettings:
    """User-configured availability settings."""
    workday_hours: float = 2.0          # Default daily hours on workdays
    weekend_hours: float = 6.0          # Default daily hours on weekends
    holiday_hours: float = 4.0          # Default daily hours on holidays
    sleep_start: int = 23               # Sleep start hour (24h)
    sleep_end: int = 7                  # Sleep end hour (24h)
    manual_busy: dict[str, float] = field(default_factory=dict)
    # manual_busy: {"2026-05-22": 3.0} means 3h blocked on that date

    def get_base_hours(self, is_workday: bool, is_holiday: bool) -> float:
        """Get base hours without calendar deductions."""
        if is_holiday:
            return self.holiday_hours
        elif is_workday:
            return self.workday_hours
        else:
            return self.weekend_hours
