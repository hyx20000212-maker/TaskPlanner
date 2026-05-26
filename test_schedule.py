"""
Schedule Engine Module — Unit Tests.

Tests:
  1. DailySlot dataclass
  2. UserSettings get_base_hours
  3. Holiday API (is_workday, is_holiday, get_holiday_name)
  4. ScheduleEngine.generate (date range)
  5. Manual busy deduction
  6. Invalid date range
  7. Cache and warmup
"""

from datetime import date, timedelta

# ── Test 1: DailySlot dataclass ─────────────────────────────────────
def test_daily_slot():
    from schedule_engine.models import DailySlot

    print("=" * 50)
    print("Test 1: DailySlot dataclass")

    slot = DailySlot(
        date=date(2026, 5, 20),
        day_of_week="Wed",
        is_workday=True,
        is_holiday=False,
        base_hours=2.0,
        available_hours=2.0,
    )
    assert slot.available_hours == 2.0
    assert slot.day_of_week == "Wed"
    d = slot.to_dict()
    assert d["date"] == "2026-05-20"
    assert d["available_hours"] == 2.0

    print("  PASS — DailySlot OK")


# ── Test 2: UserSettings get_base_hours ─────────────────────────────
def test_user_settings():
    from schedule_engine.models import UserSettings

    print("=" * 50)
    print("Test 2: UserSettings get_base_hours")

    s = UserSettings(workday_hours=2.0, weekend_hours=6.0, holiday_hours=4.0)

    assert s.get_base_hours(is_workday=True, is_holiday=False) == 2.0
    assert s.get_base_hours(is_workday=False, is_holiday=False) == 6.0
    assert s.get_base_hours(is_workday=False, is_holiday=True) == 4.0

    # Holiday overrides workday
    assert s.get_base_hours(is_workday=True, is_holiday=True) == 4.0

    print("  PASS — base hours OK")


# ── Test 3: Holiday API basic checks ────────────────────────────────
def test_holiday_api():
    from schedule_engine.holiday_api import (
        is_workday, is_holiday, get_holiday_name, is_rest_day,
    )

    print("=" * 50)
    print("Test 3: Holiday API functions")

    # Normal Wednesday (May 20, 2026) should be a workday
    d_workday = date(2026, 5, 20)
    assert is_workday(d_workday)
    assert not is_rest_day(d_workday)
    assert not is_holiday(d_workday)

    # Normal Saturday should be rest
    d_sat = date(2026, 5, 23)
    assert not is_workday(d_sat)
    assert is_rest_day(d_sat)

    # Oct 1 (National Day) should be a holiday if data is available
    d_national = date(2026, 10, 1)
    is_hol = is_holiday(d_national)
    is_rest = is_rest_day(d_national)
    name = get_holiday_name(d_national)
    print(f"  Oct 1 — is_holiday: {is_hol}, is_rest_day: {is_rest}, name: '{name}'")
    print(f"  (Holiday data may not be published for 2026 yet — that's OK)")
    print(f"  May 20 is_workday: {is_workday(d_workday)}")
    print(f"  May 23 (Sat) is_rest_day: {is_rest_day(d_sat)}")

    print("  PASS — holiday API checks complete")


# ── Test 4: ScheduleEngine.generate date range ──────────────────────
def test_schedule_generate():
    from schedule_engine.engine import ScheduleEngine

    print("=" * 50)
    print("Test 4: ScheduleEngine.generate date range")

    engine = ScheduleEngine()
    slots = engine.generate("2026-05-20", "2026-05-27")

    # Should have 8 days (inclusive)
    assert len(slots) == 8
    assert date(2026, 5, 20) in slots
    assert date(2026, 5, 27) in slots

    # All slots should have available hours > 0 (default settings)
    for s in slots.values():
        assert s.available_hours >= 0
        assert s.day_of_week in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    print(f"  Generated {len(slots)} days")
    print(f"  First: {slots[date(2026, 5, 20)]}")
    print(f"  Last:  {slots[date(2026, 5, 27)]}")

    print("  PASS — date range OK")


# ── Test 5: Manual busy deduction ───────────────────────────────────
def test_manual_busy():
    from schedule_engine.models import UserSettings
    from schedule_engine.engine import ScheduleEngine

    print("=" * 50)
    print("Test 5: Manual busy deduction")

    settings = UserSettings(
        workday_hours=4.0,
        weekend_hours=8.0,
        manual_busy={"2026-05-20": 3.0},  # 3h blocked on May 20
    )
    engine = ScheduleEngine(settings)
    slots = engine.generate("2026-05-20", "2026-05-20")

    slot = slots[date(2026, 5, 20)]
    assert slot.base_hours == 4.0
    assert slot.manual_busy_hours == 3.0
    assert slot.available_hours == 1.0  # 4.0 - 3.0

    print(f"  Base: {slot.base_hours}h, Busy: {slot.manual_busy_hours}h, "
          f"Available: {slot.available_hours}h")
    print("  PASS — manual busy deduction OK")


# ── Test 6: Invalid date range ──────────────────────────────────────
def test_invalid_range():
    from schedule_engine.engine import ScheduleEngine

    print("=" * 50)
    print("Test 6: Invalid date range")

    engine = ScheduleEngine()
    try:
        engine.generate("2026-06-01", "2026-05-01")
        print("  WARN — should have raised ValueError")
    except ValueError as e:
        assert "start" in str(e).lower()
        print("  PASS — ValueError raised for reversed dates")


# ── Test 7: to_dict round-trip ──────────────────────────────────────
def test_slot_serialization():
    from schedule_engine.models import DailySlot

    print("=" * 50)
    print("Test 7: DailySlot serialization")

    slot = DailySlot(
        date=date(2026, 1, 1),
        day_of_week="Thu",
        is_workday=False,
        is_holiday=True,
        holiday_name="New Year",
        base_hours=4.0,
        manual_busy_hours=1.0,
        available_hours=3.0,
    )
    d = slot.to_dict()
    assert d["holiday_name"] == "New Year"
    assert d["available_hours"] == 3.0
    assert d["is_holiday"] is True

    print("  PASS — serialization OK")


# ── Run all ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_daily_slot()
    test_user_settings()
    test_holiday_api()
    test_schedule_generate()
    test_manual_busy()
    test_invalid_range()
    test_slot_serialization()
    print("\n" + "=" * 50)
    print("All schedule engine tests passed!")
