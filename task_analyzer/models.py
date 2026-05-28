"""Data models for the task analyzer module."""

from dataclasses import dataclass, field
from datetime import date
import re
from typing import Optional


def _to_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return float(text)
        except ValueError:
            match = re.search(r"-?\d+(?:\.\d+)?", text)
            return float(match.group(0)) if match else default
    return default


def _to_int(value, default: int = 0) -> int:
    return int(round(_to_float(value, float(default))))


def _normalize_efficiency(data: dict) -> tuple[float, str]:
    raw_efficiency = data.get("unit_efficiency", 0)
    raw_unit = data.get("efficiency_unit", "")
    unit = str(data.get("unit", "items") or "items")

    if isinstance(raw_efficiency, str) and "per_hour" in raw_efficiency and _to_float(raw_efficiency, -1.0) < 0:
        efficiency_unit = raw_efficiency
        unit_efficiency = _to_float(raw_unit, 0.0)
    else:
        unit_efficiency = _to_float(raw_efficiency, 0.0)
        efficiency_unit = str(raw_unit or "")

    total_amount = _to_float(data.get("total_amount", 0), 0.0)
    estimated_hours = _to_float(data.get("estimated_hours", 0), 0.0)
    if unit_efficiency <= 0 and total_amount > 0 and estimated_hours > 0:
        unit_efficiency = total_amount / estimated_hours

    if not efficiency_unit:
        clean_unit = re.sub(r"\W+", "_", unit.strip().lower()).strip("_") or "items"
        efficiency_unit = f"{clean_unit}_per_hour"

    return unit_efficiency, efficiency_unit


@dataclass
class Task:
    """A single analyzed task with structured metadata.

    Supports three paradigms:
      - quantified:   total_amount=500, unit="words" → progress = completed/total
      - chore:        task_type="chore", total_amount=estimated_hours, unit="hours" → progress = completed/total
      - milestone:    task_type="milestone", subtasks=[...] → progress = done_steps/total_steps
      - daily:        recurrence="daily" → repeats every day
    """
    id: str                              # Unique task ID (e.g. "task_001")
    description: str                     # Short description of the task
    task_type: str                       # memorize / exercise / reading / writing / project / chore / milestone / other
    total_amount: float                  # Total quantity (e.g. 500), 0 for chores
    unit: str                            # Unit of measure (e.g. "words", "problems", "pages", "steps", "time")
    difficulty: int                      # Difficulty level 1-5
    estimated_hours: float               # Estimated total hours to complete
    unit_efficiency: float               # Amount completed per hour, 0 for chores
    efficiency_unit: str                 # e.g. "words_per_hour", "problems_per_hour"
    deadline: Optional[date] = None      # Deadline date
    start_date: Optional[date] = None    # Don't schedule before this date
    suggested_daily_hours: float = 0.0   # Suggested hours per day
    confidence: float = 0.5              # LLM confidence 0.0 - 1.0
    notes: str = ""                      # Additional notes or warnings
    recurrence: str = "none"             # none / daily
    prerequisites: list = field(default_factory=list)   # Task IDs that must complete before this one
    subtasks: list = field(default_factory=list)        # Milestone subtasks: [{"id":"s1","description":"...","estimated_hours":5,"order":1}]

    @property
    def is_daily_recurring(self) -> bool:
        return self.recurrence == "daily"

    @property
    def is_milestone(self) -> bool:
        return self.task_type == "milestone"

    @property
    def is_chore(self) -> bool:
        """Non-quantified one-off task (e.g. brushing teeth, grocery shopping)."""
        return self.task_type == "chore"

    @property
    def days_until_deadline(self) -> Optional[int]:
        """Calculate remaining days until deadline from today."""
        if self.deadline is None:
            return None
        return (self.deadline - date.today()).days

    @property
    def min_daily_amount(self) -> Optional[float]:
        """Minimum daily amount needed to meet the deadline."""
        days = self.days_until_deadline
        if days is None or days <= 0:
            return None
        return round(self.total_amount / days, 1)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "task_type": self.task_type,
            "total_amount": self.total_amount,
            "unit": self.unit,
            "difficulty": self.difficulty,
            "estimated_hours": self.estimated_hours,
            "unit_efficiency": self.unit_efficiency,
            "efficiency_unit": self.efficiency_unit,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "suggested_daily_hours": self.suggested_daily_hours,
            "confidence": self.confidence,
            "notes": self.notes,
            "recurrence": self.recurrence,
            "prerequisites": self.prerequisites,
            "subtasks": self.subtasks,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        deadline = data.get("deadline")
        if deadline and isinstance(deadline, str):
            deadline = date.fromisoformat(deadline)
        start_date = data.get("start_date")
        if start_date and isinstance(start_date, str):
            start_date = date.fromisoformat(start_date)
        unit_efficiency, efficiency_unit = _normalize_efficiency(data)
        recurrence = data.get("recurrence", "none")
        recurrence = recurrence if recurrence in ("none", "daily") else "none"
        return cls(
            id=data.get("id", ""),
            description=data.get("description", ""),
            task_type=data.get("task_type", "other"),
            total_amount=_to_float(data.get("total_amount", 0)),
            unit=data.get("unit", ""),
            difficulty=_to_int(data.get("difficulty", 3), 3),
            estimated_hours=_to_float(data.get("estimated_hours", 0)),
            unit_efficiency=unit_efficiency,
            efficiency_unit=efficiency_unit,
            deadline=deadline,
            start_date=start_date,
            suggested_daily_hours=_to_float(data.get("suggested_daily_hours", 0)),
            confidence=_to_float(data.get("confidence", 0.5), 0.5),
            notes=data.get("notes", ""),
            recurrence=recurrence,
            prerequisites=data.get("prerequisites", []),
            subtasks=data.get("subtasks", []),
        )


@dataclass
class TaskAnalysisResult:
    """Container for all tasks extracted from a single analysis run."""
    tasks: list[Task] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_response: str = ""              # Raw LLM response for debugging
    model_used: str = ""                # Which model was used
    tokens_used: int = 0                # Total tokens consumed

    @property
    def total_hours(self) -> float:
        return sum(t.estimated_hours for t in self.tasks)

    @property
    def task_count(self) -> int:
        return len(self.tasks)

    def to_dict(self) -> dict:
        return {
            "tasks": [t.to_dict() for t in self.tasks],
            "warnings": self.warnings,
            "model_used": self.model_used,
            "tokens_used": self.tokens_used,
        }

    def __repr__(self) -> str:
        return (f"TaskAnalysisResult(tasks={self.task_count}, "
                f"total_hours={self.total_hours:.1f}h, "
                f"warnings={len(self.warnings)})")
