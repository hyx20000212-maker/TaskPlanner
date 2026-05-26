"""
Daily Tracker Module — Two-phase daily check-in, progress tracking,
settlement, and dynamic re-planning with a sticky-note style UI.

Usage:
    from daily_tracker import DailyTracker

    tracker = DailyTracker("data/tracker.db")
    state = tracker.get_today_state()
"""

from daily_tracker.tracker import DailyTracker
from daily_tracker.models import CheckinState, TaskCheckItem, DayRecord

__all__ = ["DailyTracker", "CheckinState", "TaskCheckItem", "DayRecord"]
