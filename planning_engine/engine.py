"""
Planning Engine — Constraint-based daily task allocation algorithm.

Takes analyzed tasks + daily availability slots and produces a daily
plan allocating specific amounts of each task per day.

Algorithm:
  1. Sort tasks by DDL (earliest first)
  2. For each day, allocate available hours proportionally across active tasks
  3. Each task gets at least its min_daily amount to meet DDL
  4. Distribute remaining time evenly, favoring harder tasks earlier in the day
  5. Detect infeasibility: total demand > total supply → warn user
"""

from copy import deepcopy
from datetime import date, timedelta
from typing import Optional

from planning_engine.models import (
    DailyPlan,
    TaskAllocation,
    TaskProgress,
    PlanResult,
)
from task_analyzer.models import Task
from schedule_engine.models import DailySlot


class PlanningEngine:
    """Orchestrates daily task allocation.

    Usage:
        engine = PlanningEngine(tasks=analyzed_tasks, slots=daily_slots)
        result = engine.plan()
    """

    def __init__(
        self,
        tasks: list[Task],
        slots: dict[date, DailySlot],
        max_task_hours_per_day: float = 4.0,
        buffer_ratio: float = 0.10,
        max_tasks_per_day: int = 2,
    ):
        """
        Args:
            tasks: Analyzed tasks from module ②.
            slots: Daily availability slots from module ③.
            max_task_hours_per_day: Cap on hours per single task per day.
            buffer_ratio: Reserve this fraction of each day as buffer (0.0-0.3).
            max_tasks_per_day: Max distinct tasks allocated per day (2 = alternate).
                Set higher to allow more tasks on the same day; 0 = no limit.
        """
        if not tasks:
            raise ValueError("At least one task is required")
        if not slots:
            raise ValueError("At least one daily slot is required")

        self.tasks = tasks
        self.slots = dict(sorted(slots.items()))  # Sort by date
        self.max_task_hours_per_day = max_task_hours_per_day
        self.buffer_ratio = max(0.0, min(0.3, buffer_ratio))
        self.max_tasks_per_day = max_tasks_per_day
        self.warnings: list[str] = []

    def plan(self) -> PlanResult:
        """Run the full planning algorithm.

        Returns:
            PlanResult with daily plans and progress tracking.
        """
        self.warnings = []

        # 1. Feasibility check
        self._check_feasibility()

        # 2. Initialize tracking state
        progress: dict[str, TaskProgress] = {}
        remaining = self._init_task_state(progress)

        # 3. Sort tasks by DDL (earliest → highest priority)
        sorted_tasks = self._sort_by_priority(remaining)

        # 4. Generate daily plans
        days: list[DailyPlan] = []
        for slot_date, slot in self.slots.items():
            daily = self._plan_day(
                date=slot_date,
                day_of_week=slot.day_of_week,
                available_hours=slot.available_hours,
                remaining_tasks=sorted_tasks,
                progress=progress,
            )
            days.append(daily)

        return PlanResult(
            days=days,
            progress=progress,
            warnings=self.warnings,
        )

    # ── Internal methods ────────────────────────────────────────────

    def _check_feasibility(self):
        """Check if the plan is feasible given total demand and supply."""
        total_demand = sum(self._task_plan_hours(task) for task in self.tasks)
        total_supply = sum(s.available_hours for s in self.slots.values())

        if total_demand > total_supply * 1.1:
            self.warnings.append(
                f"Total demand ({total_demand:.1f}h) exceeds "
                f"total supply ({total_supply:.1f}h) by "
                f"{(total_demand - total_supply):.1f}h. "
                f"Not all tasks may be completed on time."
            )

        # Check each task's DDL feasibility
        today = date.today()
        for task in self.tasks:
            if task.is_daily_recurring:
                daily_hours = self._calc_recurring_daily_hours(task)
                average_supply = total_supply / max(1, len(self.slots))
                if daily_hours > average_supply * 0.7:
                    self.warnings.append(
                        f"Daily task '{task.description}' needs about {daily_hours:.1f}h/day, "
                        f"which may crowd out other tasks."
                    )
                continue
            if task.deadline is None:
                continue
            # Sum available hours until DDL
            hours_before_ddl = 0.0
            for d, slot in self.slots.items():
                if d <= task.deadline and d >= today:
                    hours_before_ddl += slot.available_hours
            # Each task can use at most ~60% of total time (others share too)
            if task.estimated_hours > hours_before_ddl * 0.7:
                self.warnings.append(
                    f"Task '{task.description}' needs {task.estimated_hours:.1f}h "
                    f"but only {hours_before_ddl:.1f}h total available before "
                    f"DDL ({task.deadline}). May not be feasible."
                )

    def _init_task_state(
        self, progress: dict[str, TaskProgress]
    ) -> list[Task]:
        """Initialize progress trackers and return mutable task copies."""
        remaining = []
        plan_days = max(1, len(self.slots))
        for t in self.tasks:
            total_amount = t.total_amount * plan_days if t.is_daily_recurring else t.total_amount
            progress[t.id] = TaskProgress(
                task_id=t.id,
                description=t.description,
                task_type=t.task_type,
                total_amount=total_amount,
                unit=t.unit,
            )
            # Shallow copy for mutation during planning
            remaining.append(deepcopy(t))
        return remaining

    @staticmethod
    def _sort_by_priority(tasks: list[Task]) -> list[Task]:
        """Sort tasks: DDL (earliest first) → difficulty (harder first)."""
        def key(t: Task):
            ddl = t.deadline or date(2099, 12, 31)  # No DDL → last
            return (ddl, -t.difficulty, t.id)
        return sorted(tasks, key=key)

    def _plan_day(
        self,
        date: date,
        day_of_week: str,
        available_hours: float,
        remaining_tasks: list[Task],
        progress: dict[str, TaskProgress],
    ) -> DailyPlan:
        """Allocate tasks for a single day.

        If max_tasks_per_day is set (>0) and active tasks exceed it,
        tasks are divided into alternating groups by day index to
        avoid piling too many tasks on the same day.
        Urgent tasks (DDL <= 3 days) are always allocated.
        """

        # Reserve buffer
        usable = available_hours * (1.0 - self.buffer_ratio)
        if usable <= 0:
            return DailyPlan(
                date=date,
                day_of_week=day_of_week,
                available_hours=available_hours,
            )

        # Filter: only tasks with remaining work
        active_all = [t for t in remaining_tasks if t.total_amount > 0]

        if not active_all:
            return DailyPlan(
                date=date,
                day_of_week=day_of_week,
                available_hours=available_hours,
            )

        # ── Task alternation: pick a subset for today ──────────────
        if self.max_tasks_per_day > 0 and len(active_all) > self.max_tasks_per_day:
            # Day index: 0-indexed from start of slots
            all_dates = list(self.slots.keys())
            day_index = all_dates.index(date) if date in all_dates else 0

            urgent = []   # DDL within 3 days — always allocated
            normal = []
            for t in active_all:
                if t.is_daily_recurring or (t.deadline and (t.deadline - date).days <= 3):
                    urgent.append(t)
                else:
                    normal.append(t)

            # Sort normal tasks so they get allocated on predictable days
            normal.sort(key=lambda t: t.id)

            # Pick normal tasks for today based on day_index. Urgent tasks may
            # exceed the cap, but normal tasks are held back when urgent work
            # already fills today's distinct-task budget.
            slots_per_group = self.max_tasks_per_day - len(urgent)
            if slots_per_group > 0 and normal:
                group_idx = (day_index // 1) % max(1, (len(normal) + slots_per_group - 1) // slots_per_group)
                start = group_idx * slots_per_group
                selected_normal = normal[start:start + slots_per_group]
            else:
                selected_normal = []

            active = urgent + selected_normal
        else:
            active = active_all

        # Calculate proportional allocation
        allocations = self._allocate_proportional(
            active=active,
            usable_hours=usable,
            planning_date=date,
        )

        # Apply allocations and update progress
        for alloc in allocations:
            for t in remaining_tasks:
                if t.id == alloc.task_id:
                    if not t.is_daily_recurring:
                        t.total_amount = max(0.0, t.total_amount - alloc.amount)
                    break
            if alloc.task_id in progress:
                p = progress[alloc.task_id]
                p.completed += alloc.amount
                p.total_hours += alloc.hours

        return DailyPlan(
            date=date,
            day_of_week=day_of_week,
            available_hours=available_hours,
            allocations=allocations,
        )

    def _allocate_proportional(
        self,
        active: list[Task],
        usable_hours: float,
        planning_date: date,
    ) -> list[TaskAllocation]:
        """Distribute usable_hours across active tasks proportionally.

        Strategy:
          1. Each task gets its minimum daily requirement first (guaranteed)
          2. Remaining time is split proportionally by remaining work
        """
        today = planning_date

        # ── Phase 1: Minimum allocation (to meet DDL) ───────────────
        min_allocations: list[tuple[str, float, float]] = []  # (id, hours, amount)
        total_min_hours = 0.0

        for t in active:
            min_h = self._calc_min_daily_hours(t, today)
            # Cap at max per task per day
            min_h = min(min_h, self.max_task_hours_per_day)
            # Convert hours to amount
            if t.unit_efficiency > 0:
                min_amount = min_h * t.unit_efficiency
            else:
                min_amount = 0.0
            # Don't exceed remaining
            min_amount = min(min_amount, t.total_amount)
            min_h = min_amount / t.unit_efficiency if t.unit_efficiency > 0 else 0.0

            min_allocations.append((t.id, min_h, min_amount))
            total_min_hours += min_h

        # If minimum exceeds usable, scale down proportionally
        if total_min_hours > usable_hours and total_min_hours > 0:
            scale = usable_hours / total_min_hours
            min_allocations = [
                (tid, h * scale, a * scale) for tid, h, a in min_allocations
            ]
            total_min_hours = usable_hours

        # ── Phase 2: Distribute remaining time ──────────────────────
        remaining_hours = usable_hours - total_min_hours
        allocations: list[TaskAllocation] = []

        # Find tasks that can take more (not at max, still have work left)
        for tid, min_h, min_amount in min_allocations:
            task = next(t for t in active if t.id == tid)
            extra_h = 0.0
            extra_amount = 0.0

            if remaining_hours > 0 and task.total_amount > min_amount and not task.is_daily_recurring:
                # Proportional to remaining work
                remaining_work_ratio = (
                    task.total_amount / sum(t.total_amount for t in active)
                    if sum(t.total_amount for t in active) > 0
                    else 1.0 / len(active)
                )
                extra_h = remaining_hours * remaining_work_ratio
                # Cap at max per task
                extra_h = min(extra_h, self.max_task_hours_per_day - min_h)
                extra_h = max(0.0, extra_h)

                if task.unit_efficiency > 0:
                    extra_amount = extra_h * task.unit_efficiency
                extra_amount = min(extra_amount, task.total_amount - min_amount)

            total_h = min_h + extra_h
            total_amount = min_amount + extra_amount

            allocations.append(TaskAllocation(
                task_id=tid,
                description=task.description,
                task_type=task.task_type,
                amount=total_amount,
                unit=task.unit,
                hours=total_h,
                difficulty=task.difficulty,
                is_catch_up=(min_h > task.suggested_daily_hours / task.unit_efficiency
                             if task.unit_efficiency > 0 else False),
            ))

        return allocations

    @staticmethod
    def _calc_min_daily_hours(task: Task, today: date) -> float:
        """Calculate minimum daily hours to meet DDL."""
        if task.is_daily_recurring:
            return PlanningEngine._calc_recurring_daily_hours(task)

        if task.deadline is None:
            return 0.0

        days_left = (task.deadline - today).days
        if days_left <= 0:
            return task.estimated_hours  # Overdue — allocate all remaining

        if task.unit_efficiency <= 0:
            return 0.0

        # Hours needed = remaining amount / efficiency / days_left
        daily_needed_hours = (task.total_amount / task.unit_efficiency) / days_left
        return max(0.0, daily_needed_hours)

    @staticmethod
    def _calc_recurring_daily_hours(task: Task) -> float:
        if task.suggested_daily_hours > 0:
            return task.suggested_daily_hours
        if task.unit_efficiency > 0:
            return task.total_amount / task.unit_efficiency
        return task.estimated_hours

    def _task_plan_hours(self, task: Task) -> float:
        if task.is_daily_recurring:
            return self._calc_recurring_daily_hours(task) * max(1, len(self.slots))
        return task.estimated_hours


# ── Convenience function ────────────────────────────────────────────

def generate_plan(
    tasks: list[Task],
    slots: dict[date, DailySlot],
    max_task_hours_per_day: float = 4.0,
    buffer_ratio: float = 0.10,
    max_tasks_per_day: int = 2,
) -> PlanResult:
    """One-liner: generate a daily plan from tasks and schedule slots."""
    engine = PlanningEngine(
        tasks=tasks,
        slots=slots,
        max_task_hours_per_day=max_task_hours_per_day,
        buffer_ratio=buffer_ratio,
        max_tasks_per_day=max_tasks_per_day,
    )
    return engine.plan()
