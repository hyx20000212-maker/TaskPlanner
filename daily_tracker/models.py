"""Data models for daily tracking and check-in system."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class TaskCheckItem:
    """A single task's check-in state for today."""
    task_id: str
    description: str
    task_type: str
    unit: str
    tier_min: float              # Min tier amount
    tier_ideal: float            # Ideal tier amount
    tier_challenge: float        # Challenge tier amount
    tier_min_hours: float = 0.0
    tier_ideal_hours: float = 0.0
    tier_challenge_hours: float = 0.0
    selected_tier: Optional[str] = None  # "min" / "ideal" / "challenge" / None

    @property
    def is_chore(self) -> bool:
        return self.task_type == "chore"

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "task_type": self.task_type,
            "unit": self.unit,
            "tier_min": self.tier_min,
            "tier_ideal": self.tier_ideal,
            "tier_challenge": self.tier_challenge,
            "tier_min_hours": self.tier_min_hours,
            "tier_ideal_hours": self.tier_ideal_hours,
            "tier_challenge_hours": self.tier_challenge_hours,
            "selected_tier": self.selected_tier,
        }


@dataclass
class CheckinState:
    """Snapshot of today's check-in progress."""
    date: date
    phase1_done: bool = False               # First open greeting viewed
    phase2_done: bool = False               # All tasks checked
    greeting_shown: bool = False            # Has greeting been displayed
    tasks: list[TaskCheckItem] = field(default_factory=list)
    phase1_time: Optional[datetime] = None
    phase2_time: Optional[datetime] = None

    @property
    def all_min_selected(self) -> bool:
        """Check if every task has at least the min tier selected."""
        if not self.tasks:
            return False
        return all(t.selected_tier is not None for t in self.tasks)

    @property
    def all_max_selected(self) -> bool:
        """Check if every task has challenge tier selected."""
        if not self.tasks:
            return False
        return all(t.selected_tier == "challenge" for t in self.tasks)

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "phase1_done": self.phase1_done,
            "phase2_done": self.phase2_done,
            "greeting_shown": self.greeting_shown,
            "tasks": [t.to_dict() for t in self.tasks],
            "phase1_time": self.phase1_time.isoformat() if self.phase1_time else None,
            "phase2_time": self.phase2_time.isoformat() if self.phase2_time else None,
        }


@dataclass
class DayRecord:
    """Historical record of a completed day."""
    date: date
    tasks_completed: list[dict] = field(default_factory=list)
    # [{"task_id": "...", "tier": "ideal", "amount": 72, "unit": "words"}, ...]
    total_hours_completed: float = 0.0
    settled: bool = False
    settled_at: Optional[datetime] = None

    @property
    def all_challenge(self) -> bool:
        return all(t.get("tier") == "challenge" for t in self.tasks_completed)

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "tasks_completed": self.tasks_completed,
            "total_hours_completed": self.total_hours_completed,
            "settled": self.settled,
            "settled_at": self.settled_at.isoformat() if self.settled_at else None,
        }
