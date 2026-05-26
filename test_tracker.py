"""
Daily Tracker Module — Unit Tests.

Tests:
  1. TaskCheckItem dataclass
  2. CheckinState all_min_selected / all_max_selected
  3. DayRecord all_challenge
  4. TrackerStorage CRUD
  5. DailyTracker get_or_create_today
  6. DailyTracker phase1 + phase2 flow
  7. Settlement logic
  8. Quote rotation
"""

import os
from datetime import date, timedelta, datetime

from task_analyzer.models import Task
from schedule_engine.models import DailySlot
from planning_engine.engine import PlanningEngine


TEST_DB = "test_tracker.db"


def cleanup():
    import time
    for _ in range(3):
        try:
            if os.path.exists(TEST_DB):
                os.remove(TEST_DB)
            break
        except PermissionError:
            time.sleep(0.1)


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


def make_slot(d: date, hours: float = 4.0) -> DailySlot:
    return DailySlot(
        date=d, day_of_week=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][d.weekday()],
        is_workday=d.weekday()<5, is_holiday=False,
        base_hours=hours, available_hours=hours,
    )


# ── Test 1: TaskCheckItem ───────────────────────────────────────────
def test_task_check_item():
    from daily_tracker.models import TaskCheckItem

    print("=" * 50)
    print("Test 1: TaskCheckItem")

    t = TaskCheckItem(
        task_id="t1", description="Test", task_type="memorize",
        unit="words", tier_min=10, tier_ideal=15, tier_challenge=20,
    )
    assert t.selected_tier is None
    t.selected_tier = "ideal"
    d = t.to_dict()
    assert d["selected_tier"] == "ideal"
    assert d["tier_min"] == 10

    print("  PASS")


# ── Test 2: CheckinState properties ─────────────────────────────────
def test_checkin_state():
    from daily_tracker.models import CheckinState, TaskCheckItem

    print("=" * 50)
    print("Test 2: CheckinState all_min/all_max")

    tasks = [
        TaskCheckItem(task_id="t1", description="A", task_type="memorize",
                      unit="w", tier_min=5, tier_ideal=10, tier_challenge=15),
        TaskCheckItem(task_id="t2", description="B", task_type="exercise",
                      unit="p", tier_min=3, tier_ideal=5, tier_challenge=8),
    ]
    state = CheckinState(date=date.today(), tasks=tasks)
    assert not state.all_min_selected
    assert not state.all_max_selected

    tasks[0].selected_tier = "min"
    assert not state.all_min_selected  # t2 still unset

    tasks[1].selected_tier = "ideal"
    assert state.all_min_selected      # both have something
    assert not state.all_max_selected  # not both challenge

    tasks[0].selected_tier = "challenge"
    tasks[1].selected_tier = "challenge"
    assert state.all_max_selected

    print("  PASS")


# ── Test 3: DayRecord ───────────────────────────────────────────────
def test_day_record():
    from daily_tracker.models import DayRecord

    print("=" * 50)
    print("Test 3: DayRecord all_challenge")

    r = DayRecord(
        date=date.today(),
        tasks_completed=[
            {"task_id": "t1", "tier": "challenge", "amount": 20},
            {"task_id": "t2", "tier": "challenge", "amount": 10},
        ],
    )
    assert r.all_challenge

    r2 = DayRecord(
        date=date.today(),
        tasks_completed=[
            {"task_id": "t1", "tier": "ideal", "amount": 15},
        ],
    )
    assert not r2.all_challenge

    d = r.to_dict()
    assert d["settled"] is False

    print("  PASS")


# ── Test 4: TrackerStorage CRUD ─────────────────────────────────────
def test_storage():
    from daily_tracker.storage import TrackerStorage
    from daily_tracker.models import CheckinState, TaskCheckItem, DayRecord

    print("=" * 50)
    print("Test 4: TrackerStorage CRUD")

    cleanup()
    s = TrackerStorage(TEST_DB)
    try:
        # Save checkin state
        tasks = [
            TaskCheckItem(task_id="t1", description="A", task_type="memorize",
                          unit="w", tier_min=5, tier_ideal=10, tier_challenge=15,
                          selected_tier="ideal"),
        ]
        state = CheckinState(date=date.today(), phase1_done=True, tasks=tasks)
        s.save_checkin_state(state)

        # Load back
        loaded = s.get_checkin_state(date.today())
        assert loaded is not None
        assert loaded.phase1_done
        assert len(loaded.tasks) == 1
        assert loaded.tasks[0].selected_tier == "ideal"

        # Day record
        record = DayRecord(
            date=date.today(),
            tasks_completed=[{"task_id": "t1", "tier": "ideal", "amount": 10}],
            total_hours_completed=0.5,
            settled=True,
        )
        s.save_day_record(record)
        loaded_r = s.get_day_record(date.today())
        assert loaded_r is not None
        assert loaded_r.settled

        # Settings
        s.set_setting("settlement_hour", "2")
        assert s.settlement_hour == 2

        # Recent records
        recents = s.get_recent_record(7)
        assert len(recents) >= 1
    finally:
        # Close connections
        try:
            s._get_conn().close()
        except Exception:
            pass
        cleanup()
    print("  PASS")


# ── Test 5: DailyTracker get_or_create ──────────────────────────────
def test_tracker_create():
    from daily_tracker import DailyTracker

    print("=" * 50)
    print("Test 5: DailyTracker get_or_create_today")

    cleanup()
    tracker = DailyTracker(TEST_DB)
    try:
        tracker.settlement_hour = 0
        tasks = [
            make_task(id="t1", total_amount=100, unit_efficiency=20, estimated_hours=5),
        ]
        slots = {}
        for i in range(7):
            d = date.today() + timedelta(days=i)
            slots[d] = make_slot(d, 4.0)
        plan = PlanningEngine(tasks=tasks, slots=slots).plan()
        state = tracker.get_or_create_today(plan=plan, tasks=tasks)
        assert state is not None
        assert len(state.tasks) == 1
        assert state.tasks[0].tier_min > 0
        assert state.tasks[0].tier_ideal >= state.tasks[0].tier_min
        assert state.tasks[0].tier_challenge >= state.tasks[0].tier_ideal
        print(f"  Tiers: min={state.tasks[0].tier_min:.0f}, "
              f"ideal={state.tasks[0].tier_ideal:.0f}, "
              f"challenge={state.tasks[0].tier_challenge:.0f}")

        empty_first = DailyTracker(TEST_DB)
        empty_state = empty_first.get_or_create_today()
        empty_first.storage.save_checkin_state(empty_state)
        rebuilt = empty_first.get_or_create_today(plan=plan, tasks=tasks)
        assert len(rebuilt.tasks) == 1
        assert rebuilt.tasks[0].task_id == "t1"
    finally:
        cleanup()
    print("  PASS")


# ── Test 6: Phase 1 + Phase 2 flow ──────────────────────────────────
def test_phase_flow():
    from daily_tracker import DailyTracker

    print("=" * 50)
    print("Test 6: Two-phase flow")

    cleanup()
    tracker = DailyTracker(TEST_DB)
    try:
        # Use a fresh date to avoid collision with previous test
        d = date.today()
        tasks = [make_task(id="t1")]
        slots = {d: make_slot(d, 4.0)}
        plan = PlanningEngine(tasks=tasks, slots=slots).plan()
        state = tracker.get_or_create_today(plan=plan, tasks=tasks)
        assert not state.phase1_done
        tracker.confirm_phase1(state)
        assert state.phase1_done
        result = tracker.select_tier(state, "t1", "ideal")
        assert result == "ok_all_done"
        # Verify it persisted
        state2 = tracker.storage.get_checkin_state(tracker.today)
        assert state2 is not None
        assert state2.phase2_done
    finally:
        cleanup()
    print("  PASS")


# ── Test 7: Settlement ──────────────────────────────────────────────
def test_settlement():
    from daily_tracker import DailyTracker

    print("=" * 50)
    print("Test 7: Settlement")

    cleanup()
    # Use a separate DB to avoid collision
    db = "test_settle.db"
    try:
        import os as _os
        if _os.path.exists(db):
            _os.remove(db)
    except Exception:
        pass

    tracker = DailyTracker(db)
    try:
        tasks = [make_task(id="t1", total_amount=100, unit_efficiency=20)]
        d = date.today()
        slots = {d: make_slot(d, 4.0)}
        plan = PlanningEngine(tasks=tasks, slots=slots).plan()
        state = tracker.get_or_create_today(plan=plan, tasks=tasks)
        tracker.confirm_phase1(state)
        tracker.select_tier(state, "t1", "challenge")
        tracker.force_settle_today()
        record = tracker.storage.get_day_record(tracker.today)
        assert record is not None
        assert record.settled
        assert len(record.tasks_completed) == 1
        assert record.tasks_completed[0]["tier"] == "challenge"
    finally:
        try:
            import os as _os
            if _os.path.exists(db):
                _os.remove(db)
        except Exception:
            pass
    print("  PASS")


# ── Test 8: Quote rotation ──────────────────────────────────────────
def test_quotes():
    from daily_tracker.quotes import (
        get_daily_quote, get_encouragement, get_praise,
    )
    from daily_tracker.news_jokes import get_news_joke

    print("=" * 50)
    print("Test 8: Quotes and jokes")

    q = get_daily_quote("zh", 0)
    assert len(q) > 3
    print(f"  Quote zh[0]: {q[:30]}...")

    q2 = get_daily_quote("zh", 100)  # Wraps
    assert len(q2) > 3

    e = get_encouragement("zh", 0)
    assert len(e) > 5

    p = get_praise("zh", 0)
    assert len(p) > 5

    n = get_news_joke("zh", 0)
    assert len(n) > 5

    print("  PASS")


# ── Run all ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_task_check_item()
    test_checkin_state()
    test_day_record()
    test_storage()
    test_tracker_create()
    test_phase_flow()
    test_settlement()
    test_quotes()
    print("\n" + "=" * 50)
    print("All daily tracker tests passed!")
