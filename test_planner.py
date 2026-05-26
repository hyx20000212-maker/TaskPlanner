"""
Planning Engine Module — Unit Tests.

Tests:
  1. TaskAllocation / DailyPlan / TaskProgress / PlanResult dataclasses
  2. PlanningEngine basic plan generation
  3. DDL-based priority sorting
  4. Buffer ratio allocation
  5. Single task plan
  6. Infeasibility warnings
    7. PlanResult serialization
    8. Daily recurring tasks
"""

from datetime import date, timedelta

from task_analyzer.models import Task
from schedule_engine.models import DailySlot


def make_task(**overrides) -> Task:
    defaults = {
        "id": "task_001", "description": "Test task",
        "task_type": "memorize", "total_amount": 100.0, "unit": "words",
        "difficulty": 3, "estimated_hours": 5.0, "unit_efficiency": 20.0,
        "efficiency_unit": "words_per_hour",
        "deadline": date.today() + timedelta(days=7),
    }
    defaults.update(overrides)
    return Task(**defaults)


def make_slot(d: date, hours: float = 2.0) -> DailySlot:
    return DailySlot(
        date=d, day_of_week=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][d.weekday()],
        is_workday=d.weekday()<5, is_holiday=False,
        base_hours=hours, available_hours=hours,
    )


# ── Test 1: Models ──────────────────────────────────────────────────
def test_models():
    from planning_engine.models import (
        TaskAllocation, DailyPlan, TaskProgress, PlanResult,
    )

    print("=" * 50)
    print("Test 1: Planning models")

    a = TaskAllocation(task_id="t1", description="Test", task_type="memorize",
                       amount=50, unit="words", hours=2.5, difficulty=3)
    assert a.to_dict()["amount"] == 50.0

    d = DailyPlan(date=date(2026,5,20), day_of_week="Wed", available_hours=4.0,
                  allocations=[a])
    assert d.total_allocated_hours == 2.5
    assert d.slack_hours == 1.5
    assert d.to_dict()["total_allocated"] == 2.5

    p = TaskProgress(task_id="t1", description="Test", task_type="memorize",
                     total_amount=100, unit="words", completed=60)
    assert p.remaining == 40
    assert p.progress_pct == 0.6

    r = PlanResult(days=[d], progress={"t1": p})
    assert r.day_count == 1
    assert r.total_planned_hours == 2.5
    assert r.to_dict()["day_count"] == 1

    print("  PASS — all models OK")


# ── Test 2: Basic planning ──────────────────────────────────────────
def test_basic_plan():
    from planning_engine.engine import PlanningEngine

    print("=" * 50)
    print("Test 2: Basic plan generation")

    today = date.today()
    tasks = [
        make_task(id="t1", description="Memorize words", total_amount=500,
                  estimated_hours=25, deadline=today+timedelta(days=7)),
    ]
    slots = {}
    for i in range(7):
        d = today + timedelta(days=i)
        h = 6.0 if d.weekday() >= 5 else 2.0
        slots[d] = make_slot(d, h)

    engine = PlanningEngine(tasks=tasks, slots=slots)
    result = engine.plan()

    assert result.day_count == 7
    assert len(result.progress) == 1
    p = result.progress["t1"]
    print(f"  Completed: {p.completed:.1f}/{p.total_amount} ({p.progress_pct:.0%})")
    print(f"  Total hours: {p.total_hours:.1f}/{tasks[0].estimated_hours}")
    print(f"  Days with allocations: {sum(1 for d in result.days if d.allocations)}")
    print("  PASS — basic plan generated")


# ── Test 3: DDL priority ────────────────────────────────────────────
def test_ddl_priority():
    from planning_engine.engine import PlanningEngine

    print("=" * 50)
    print("Test 3: DDL-based priority")

    today = date.today()
    tasks = [
        make_task(id="urgent", description="Urgent task", total_amount=100,
                  estimated_hours=5, deadline=today+timedelta(days=3)),
        make_task(id="relaxed", description="Relaxed task", total_amount=100,
                  estimated_hours=5, deadline=today+timedelta(days=10)),
    ]
    slots = {}
    for i in range(10):
        d = today + timedelta(days=i)
        slots[d] = make_slot(d, 2.0)

    engine = PlanningEngine(tasks=tasks, slots=slots)
    result = engine.plan()

    # Urgent task should have more progress by day 3
    p_urgent = result.progress["urgent"]
    p_relaxed = result.progress["relaxed"]
    print(f"  Urgent progress: {p_urgent.progress_pct:.0%}")
    print(f"  Relaxed progress: {p_relaxed.progress_pct:.0%}")
    # Urgent should be at or near 100%
    assert p_urgent.progress_pct >= 0.9, f"Urgent only {p_urgent.progress_pct:.0%}"
    print("  PASS — urgent task prioritized")

    # Check that early days favor the urgent task
    early_days = [d for d in result.days[:4] if d.allocations]
    urgent_early = sum(
        sum(a.hours for a in d.allocations if a.task_id == "urgent")
        for d in early_days
    )
    relaxed_early = sum(
        sum(a.hours for a in d.allocations if a.task_id == "relaxed")
        for d in early_days
    )
    print(f"  Early days — urgent: {urgent_early:.1f}h, relaxed: {relaxed_early:.1f}h")


# ── Test 4: Buffer ratio ────────────────────────────────────────────
def test_buffer():
    from planning_engine.engine import PlanningEngine

    print("=" * 50)
    print("Test 4: Buffer ratio")

    today = date.today()
    tasks = [make_task()]
    slots = {today: make_slot(today, 4.0)}

    # 10% buffer
    engine = PlanningEngine(tasks=tasks, slots=slots, buffer_ratio=0.10)
    result = engine.plan()
    day = result.days[0]
    assert day.total_allocated_hours <= 3.6  # 4.0 * 0.9
    print(f"  10% buffer: allocated {day.total_allocated_hours:.1f}/{day.available_hours}h")

    # 0% buffer
    engine2 = PlanningEngine(tasks=tasks, slots=slots, buffer_ratio=0.0)
    result2 = engine2.plan()
    day2 = result2.days[0]
    print(f"  0% buffer: allocated {day2.total_allocated_hours:.1f}/{day2.available_hours}h")
    # 0% buffer should allocate more
    assert day2.total_allocated_hours >= day.total_allocated_hours - 0.01
    print("  PASS — buffer ratio works")


# ── Test 5: Single task complete ────────────────────────────────────
def test_single_task_complete():
    from planning_engine.engine import PlanningEngine

    print("=" * 50)
    print("Test 5: Single task completes")

    today = date.today()
    tasks = [make_task(id="t1", total_amount=50, unit_efficiency=10, estimated_hours=5)]
    slots = {}
    for i in range(5):
        slots[today + timedelta(days=i)] = make_slot(today+timedelta(days=i), 4.0)

    engine = PlanningEngine(tasks=tasks, slots=slots)
    result = engine.plan()

    p = result.progress["t1"]
    print(f"  Completed: {p.completed:.1f}/{p.total_amount} ({p.progress_pct:.0%})")
    assert p.progress_pct >= 0.99
    print("  PASS — task fully completed")


# ── Test 6: Infeasibility detection ─────────────────────────────────
def test_infeasibility():
    from planning_engine.engine import PlanningEngine

    print("=" * 50)
    print("Test 6: Infeasibility warnings")

    today = date.today()
    tasks = [
        make_task(id="big", description="Huge task", total_amount=1000,
                  estimated_hours=100, deadline=today+timedelta(days=1)),
    ]
    slots = {today: make_slot(today, 1.0)}

    engine = PlanningEngine(tasks=tasks, slots=slots)
    result = engine.plan()

    print(f"  Warnings: {result.warnings}")
    assert len(result.warnings) >= 1
    print("  PASS — infeasibility detected")


# ── Test 7: Plan serialization ──────────────────────────────────────
def test_plan_serialization():
    from planning_engine.engine import PlanningEngine

    print("=" * 50)
    print("Test 7: PlanResult serialization")

    today = date.today()
    tasks = [make_task()]
    slots = {today: make_slot(today, 4.0)}
    engine = PlanningEngine(tasks=tasks, slots=slots)
    result = engine.plan()

    d = result.to_dict()
    assert d["day_count"] == 1
    assert "days" in d
    assert "progress" in d
    assert "warnings" in d
    assert len(d["days"]) == 1
    assert "allocations" in d["days"][0]

    print("  PASS — serialization OK")


# ── Test 8: Daily recurring tasks ──────────────────────────────────
def test_daily_recurring_task():
    from planning_engine.engine import PlanningEngine

    print("=" * 50)
    print("Test 8: Daily recurring tasks")

    today = date.today()
    task = make_task(
        id="daily_words",
        description="每天背 100 个单词",
        total_amount=100,
        estimated_hours=2,
        unit_efficiency=50,
        suggested_daily_hours=2,
        deadline=None,
        recurrence="daily",
    )
    slots = {today + timedelta(days=i): make_slot(today + timedelta(days=i), 3.0) for i in range(5)}

    round_tripped = Task.from_dict(task.to_dict())
    assert round_tripped.is_daily_recurring

    result = PlanningEngine(tasks=[round_tripped], slots=slots).plan()
    allocated_days = [day for day in result.days if day.allocations]
    assert len(allocated_days) == 5
    assert all(day.allocations[0].amount == 100 for day in allocated_days)
    assert result.progress["daily_words"].total_amount == 500
    assert result.progress["daily_words"].completed == 500

    print("  PASS — daily task appears every day without a DDL")


# ── Run all ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_models()
    test_basic_plan()
    test_ddl_priority()
    test_buffer()
    test_single_task_complete()
    test_infeasibility()
    test_plan_serialization()
    test_daily_recurring_task()
    print("\n" + "=" * 50)
    print("All planning engine tests passed!")
