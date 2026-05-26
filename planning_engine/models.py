"""Data models for the planning engine."""

from dataclasses import dataclass, field
from datetime import date


@dataclass
class TaskAllocation:
    """How much of a task is allocated on a specific day."""
    task_id: str
    description: str
    task_type: str
    amount: float                       # Amount to complete today
    unit: str                           # e.g. "words", "problems"
    hours: float                        # Hours allocated today
    difficulty: int = 1
    is_catch_up: bool = False           # True if extra allocation to meet DDL

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "task_type": self.task_type,
            "amount": round(self.amount, 1),
            "unit": self.unit,
            "hours": round(self.hours, 1),
            "difficulty": self.difficulty,
            "is_catch_up": self.is_catch_up,
        }


@dataclass
class DailyPlan:
    """Complete plan for a single day."""
    date: date
    day_of_week: str
    available_hours: float
    allocations: list[TaskAllocation] = field(default_factory=list)
    
    @property
    def total_allocated_hours(self) -> float:
        return sum(a.hours for a in self.allocations)

    @property
    def slack_hours(self) -> float:
        """Unallocated hours (buffer)."""
        return max(0.0, self.available_hours - self.total_allocated_hours)

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "day_of_week": self.day_of_week,
            "available_hours": self.available_hours,
            "total_allocated": round(self.total_allocated_hours, 1),
            "slack": round(self.slack_hours, 1),
            "allocations": [a.to_dict() for a in self.allocations],
        }


@dataclass
class TaskProgress:
    """Tracks progress of a single task through the plan."""
    task_id: str
    description: str
    task_type: str
    total_amount: float
    unit: str
    completed: float = 0.0              # Cumulative amount completed
    total_hours: float = 0.0            # Total hours allocated so far
    
    @property
    def remaining(self) -> float:
        return max(0.0, self.total_amount - self.completed)

    @property
    def progress_pct(self) -> float:
        if self.total_amount <= 0:
            return 1.0
        return min(1.0, self.completed / self.total_amount)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "task_type": self.task_type,
            "total_amount": self.total_amount,
            "unit": self.unit,
            "completed": round(self.completed, 1),
            "remaining": round(self.remaining, 1),
            "progress_pct": round(self.progress_pct, 2),
            "total_hours": round(self.total_hours, 1),
        }


@dataclass
class PlanResult:
    """Complete planning result."""
    days: list[DailyPlan] = field(default_factory=list)
    progress: dict[str, TaskProgress] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    rationale: str = ""                 # Natural-language explanation of the plan

    @property
    def total_planned_hours(self) -> float:
        return sum(d.total_allocated_hours for d in self.days)

    @property
    def day_count(self) -> int:
        return len(self.days)

    def to_dict(self) -> dict:
        return {
            "day_count": self.day_count,
            "total_planned_hours": round(self.total_planned_hours, 1),
            "days": [d.to_dict() for d in self.days],
            "progress": {k: v.to_dict() for k, v in self.progress.items()},
            "warnings": self.warnings,
            "rationale": self.rationale,
        }
