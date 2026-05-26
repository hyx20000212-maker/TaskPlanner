"""
Planning Engine Module — Allocates daily tasks based on DDL, difficulty,
and user availability schedule.

Usage:
    from planning_engine import PlanningEngine, DailyPlan, TaskAllocation

    engine = PlanningEngine(tasks=[...], slots={...})
    plan = engine.plan()
    for daily in plan.days:
        print(daily.date, daily.allocations)
"""

from planning_engine.engine import PlanningEngine
from planning_engine.models import DailyPlan, TaskAllocation, PlanResult

__all__ = ["PlanningEngine", "DailyPlan", "TaskAllocation", "PlanResult"]
