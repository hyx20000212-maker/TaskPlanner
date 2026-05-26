"""
Daily Tracker — Two-phase check-in orchestrator.

Phase 1: Greeting + yesterday review + today's goals → confirm → phase 2
Phase 2: Task list with min/ideal/challenge tiers → check all → done

Daily settlement: at configurable hour, auto-settle and re-plan.
"""

import random
from datetime import date, datetime, timedelta
from typing import Optional

from daily_tracker.models import CheckinState, TaskCheckItem, DayRecord
from daily_tracker.storage import TrackerStorage
from daily_tracker.quotes import (
    get_daily_quote, get_encouragement, get_greeting, get_praise,
)
from daily_tracker.news_jokes import get_news_joke
from planning_engine.models import PlanResult, DailyPlan, TaskAllocation
from task_analyzer.models import Task
from schedule_engine.models import DailySlot


class DailyTracker:
    """Manages daily two-phase check-in and progress tracking.

    Usage:
        tracker = DailyTracker("tracker.db")
        state = tracker.get_or_create_today(
            plan=plan_result,
            tasks=analyzed_tasks,
        )
        tracker.confirm_phase1(state)   # → phase 2
        tracker.select_tier(state, task_id, "ideal")
        tracker.confirm_phase2(state)   # → done
    """

    def __init__(self, db_path: str = "tracker.db"):
        self.storage = TrackerStorage(db_path)

    # ── Settlement time ─────────────────────────────────────────────

    @property
    def settlement_hour(self) -> int:
        return self.storage.settlement_hour

    @settlement_hour.setter
    def settlement_hour(self, hour: int):
        self.storage.settlement_hour = hour

    @property
    def today(self) -> date:
        now = datetime.now()
        # If before settlement hour, "today" is still the previous calendar day
        if now.hour < self.settlement_hour:
            return (now - timedelta(days=1)).date()
        return now.date()

    # ── State management ────────────────────────────────────────────

    def get_or_create_today(
        self,
        plan: Optional[PlanResult] = None,
        tasks: Optional[list[Task]] = None,
    ) -> CheckinState:
        """Get today's state, creating it from a plan if needed.

        Also runs settlement for any missed days.
        """
        d = self.today

        # Auto-settle any days between last settlement and today
        self._auto_settle()

        # Try existing state
        state = self.storage.get_checkin_state(d)
        if state:
            if plan and tasks and self._state_needs_rebuild(state, tasks):
                state = self._create_from_plan(d, plan, tasks)
                self.storage.save_checkin_state(state)
            return state

        # Create from plan
        if plan and tasks:
            state = self._create_from_plan(d, plan, tasks)
            self.storage.save_checkin_state(state)
            return state

        # No plan available — return empty state
        state = CheckinState(date=d)
        return state

    @staticmethod
    def _state_needs_rebuild(state: CheckinState, tasks: list[Task]) -> bool:
        if not tasks:
            return False
        state_ids = {item.task_id for item in state.tasks}
        plan_ids = {task.id for task in tasks}
        return state_ids != plan_ids

    def _create_from_plan(
        self, d: date, plan: PlanResult, tasks: list[Task],
    ) -> CheckinState:
        """Create a new CheckinState from a PlanResult."""
        # Find today's daily plan
        today_allocations: list[TaskAllocation] = []
        for dp in plan.days:
            if dp.date == d:
                today_allocations = dp.allocations
                break

        # Build task → allocation map
        alloc_map: dict[str, TaskAllocation] = {}
        for a in today_allocations:
            alloc_map[a.task_id] = a

        # Build task→original task map
        task_map: dict[str, Task] = {}
        for t in tasks:
            task_map[t.id] = t

        # Create check items with three tiers
        check_items: list[TaskCheckItem] = []
        for t in tasks:
            alloc = alloc_map.get(t.id)
            base_amount = alloc.amount if alloc else t.min_daily_amount or 0
            efficiency = t.unit_efficiency if t.unit_efficiency > 0 else 1.0

            # Three tiers around the base allocation
            tier_min = max(1, round(base_amount * 0.7, 0))
            tier_ideal = max(2, round(base_amount, 0))
            tier_challenge = max(3, round(base_amount * 1.3, 0))

            check_items.append(TaskCheckItem(
                task_id=t.id,
                description=t.description,
                task_type=t.task_type,
                unit=t.unit,
                tier_min=tier_min,
                tier_ideal=tier_ideal,
                tier_challenge=tier_challenge,
                tier_min_hours=round(tier_min / efficiency, 1),
                tier_ideal_hours=round(tier_ideal / efficiency, 1),
                tier_challenge_hours=round(tier_challenge / efficiency, 1),
            ))

        return CheckinState(
            date=d,
            tasks=check_items,
        )

    # ── Phase 1 ─────────────────────────────────────────────────────

    def confirm_phase1(self, state: CheckinState):
        """Mark phase 1 as done."""
        state.phase1_done = True
        state.greeting_shown = True
        state.phase1_time = datetime.now()
        self.storage.save_checkin_state(state)

    # ── Phase 2: Tier selection ─────────────────────────────────────

    def select_tier(
        self, state: CheckinState, task_id: str, tier: str,
    ) -> str:
        """Select a tier for a task. Returns confirmation message key.

        Args:
            state: Current checkin state.
            task_id: Task to update.
            tier: "min", "ideal", or "challenge".

        Returns:
            "ok" if set, "ok_all_done" if this was the last one, "invalid" if bad tier.
        """
        if tier not in ("min", "ideal", "challenge"):
            return "invalid"

        for t in state.tasks:
            if t.task_id == task_id:
                t.selected_tier = tier
                break

        self.storage.save_checkin_state(state)

        # Check if all tasks have at least min selected
        if state.all_min_selected:
            state.phase2_done = True
            state.phase2_time = datetime.now()
            self.storage.save_checkin_state(state)
            return "ok_all_done"

        return "ok"

    # ── Settlement ──────────────────────────────────────────────────

    def _auto_settle(self):
        """Auto-settle any days between last settlement and today."""
        last = self.storage.get_last_settlement_date() or (
            self.today - timedelta(days=1)
        )
        check_date = last + timedelta(days=1)
        while check_date < self.today:
            self._settle_day(check_date)
            check_date += timedelta(days=1)

    def _settle_day(self, d: date):
        """Settle a single day: save record, mark as done."""
        state = self.storage.get_checkin_state(d)

        tasks_completed = []
        total_hours = 0.0

        if state:
            for t in state.tasks:
                tier = t.selected_tier or "none"
                if tier == "min":
                    amount = t.tier_min
                    hours = t.tier_min_hours
                elif tier == "ideal":
                    amount = t.tier_ideal
                    hours = t.tier_ideal_hours
                elif tier == "challenge":
                    amount = t.tier_challenge
                    hours = t.tier_challenge_hours
                else:
                    amount = 0.0
                    hours = 0.0

                tasks_completed.append({
                    "task_id": t.task_id,
                    "description": t.description,
                    "tier": tier,
                    "amount": amount,
                    "unit": t.unit,
                    "hours": hours,
                })
                total_hours += hours

        record = DayRecord(
            date=d,
            tasks_completed=tasks_completed,
            total_hours_completed=round(total_hours, 1),
            settled=True,
            settled_at=datetime.now(),
        )
        self.storage.save_day_record(record)
        self.storage.set_last_settlement_date(d)

    def force_settle_today(self):
        """Manually trigger settlement for today."""
        self._settle_day(self.today)

    # ── Quote helpers ───────────────────────────────────────────────

    def get_greeting_quote(self, lang: str = "zh") -> str:
        idx = self.today.toordinal()
        return get_greeting(lang, idx)

    def get_daily_motivation(self, lang: str = "zh") -> str:
        idx = self.today.toordinal()
        return get_daily_quote(lang, idx)

    def get_news_or_joke(self, lang: str = "zh") -> str:
        idx = self.storage.get_quote_index("news")
        item = get_news_joke(lang, idx)
        self.storage.set_quote_index("news", idx + 1)
        return item

    def get_today_encouragement(self, lang: str = "zh") -> Optional[str]:
        """If yesterday was all-challenge, return encouragement."""
        yesterday = self.today - timedelta(days=1)
        record = self.storage.get_day_record(yesterday)
        if record and record.all_challenge:
            idx = random.randint(0, 99)
            return get_encouragement(lang, idx)
        return None

    def get_today_praise(self, lang: str = "zh") -> Optional[str]:
        """If today all tasks checked, return praise."""
        state = self.storage.get_checkin_state(self.today)
        if state and state.all_min_selected:
            idx = random.randint(0, 99)
            return get_praise(lang, idx)
        return None

    # ── Yesterday summary ───────────────────────────────────────────

    def get_yesterday_summary(self, lang: str = "zh") -> Optional[str]:
        """Get a human-readable summary of yesterday's completion."""
        yesterday = self.today - timedelta(days=1)
        record = self.storage.get_day_record(yesterday)
        if not record or not record.tasks_completed:
            return None

        lines = []
        for t in record.tasks_completed:
            tier_label = {"min": "最低", "ideal": "理想", "challenge": "挑战", "none": "未完成"}
            tier_label_en = {"min": "Min", "ideal": "Ideal", "challenge": "Challenge", "none": "Not done"}
            label = tier_label if lang == "zh" else tier_label_en
            tier_name = label.get(t["tier"], t["tier"])
            emoji = {"challenge": "🔥", "ideal": "✅", "min": "📌", "none": "❌"}.get(t["tier"], "—")

            if lang == "zh":
                lines.append(
                    f"{emoji} {t['description']}: {tier_name}档 "
                    f"（完成 {t['amount']:.0f} {t['unit']}，耗时 {t['hours']:.1f}h）"
                )
            else:
                lines.append(
                    f"{emoji} {t['description']}: {tier_name} tier "
                    f"({t['amount']:.0f} {t['unit']}, {t['hours']:.1f}h)"
                )

        return "\n".join(lines)

    # ── Progress summary ────────────────────────────────────────────

    def get_progress_summary(self, tasks: list[Task], lang: str = "zh") -> str:
        """Build a progress summary for the greeting view."""
        lines = []
        for t in tasks:
            pct = t.progress_pct * 100 if hasattr(t, 'progress_pct') else 0
            remaining = t.remaining if hasattr(t, 'remaining') else t.total_amount
            if lang == "zh":
                lines.append(f"• {t.description}: 进度 {pct:.0f}%，剩余 {remaining:.0f} {t.unit}")
            else:
                lines.append(f"• {t.description}: {pct:.0f}% done, {remaining:.0f} {t.unit} remaining")
        return "\n".join(lines)
