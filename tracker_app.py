"""
Sticky-Note Daily Tracker App.

Features:
    - If no plan exists: create one inside this app (upload/type -> analyze -> schedule -> plan)
    - If a plan exists: two-phase daily check-in
    - Import new tasks from the task list, then dynamically re-plan

Run:
    streamlit run tracker_app.py
"""

import json
import math
import os
import sqlite3
import tempfile
from datetime import date, timedelta

import streamlit as st

from daily_tracker import DailyTracker
from doc_parser import parse_document
from doc_parser.i18n import Lang, t, translate_error
from planning_engine import PlanningEngine
from planning_engine.models import PlanResult
from schedule_engine import ScheduleEngine, UserSettings
from schedule_engine.models import DailySlot
from task_analyzer import TaskAnalyzer
from task_analyzer.models import Task


st.set_page_config(
    page_title="Daily Tracker",
    page_icon="📋",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
.main .block-container {
    max-width: 500px;
    padding: 1rem;
}
.stButton button {
    width: 100%;
    border-radius: 8px;
}
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 8px;
}
</style>
""",
    unsafe_allow_html=True,
)


DEFAULTS = {
    "lang": "zh",
    "tracker": None,
    "today_state": None,
    "plan_result": None,
    "analyzed_tasks": None,
    "slots": None,
    "show_review": False,
    "confirm_pending": None,
    "praise_shown": False,
    "create_doc": None,
    "create_analysis": None,
    "create_slots": None,
    "api_key": os.environ.get("DEEPSEEK_API_KEY", "") or os.environ.get("OPENAI_API_KEY", ""),
    "provider": "deepseek",
    "sticky_opacity": 95,
    "delete_tasks_pending": False,
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value

lang: Lang = st.session_state.lang


def _(key: str) -> str:
    return t(key, lang)


def _connect_tracker_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    return conn


def get_db_setting(db_path: str, key: str, default: str = "") -> str:
    conn = _connect_tracker_db(db_path)
    try:
        row = conn.execute("SELECT value FROM user_settings WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()
    return row["value"] if row else default


def set_db_setting(db_path: str, key: str, value: str):
    conn = _connect_tracker_db(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO user_settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def clear_current_plan(db_path: str, current_day: date):
    """Remove the active plan and today's checklist without deleting history."""
    conn = _connect_tracker_db(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS checkin_state (
                date TEXT PRIMARY KEY,
                phase1_done INTEGER DEFAULT 0,
                phase2_done INTEGER DEFAULT 0,
                greeting_shown INTEGER DEFAULT 0,
                tasks_json TEXT DEFAULT '[]',
                phase1_time TEXT,
                phase2_time TEXT
            )
        """)
        conn.execute("DELETE FROM user_settings WHERE key = ?", ("plan_snapshot",))
        conn.execute("DELETE FROM checkin_state WHERE date = ?", (current_day.isoformat(),))
        conn.commit()
    finally:
        conn.close()

    for key in (
        "plan_result",
        "analyzed_tasks",
        "slots",
        "today_state",
        "create_doc",
        "create_analysis",
        "create_slots",
    ):
        st.session_state[key] = None
    st.session_state.confirm_pending = None
    st.session_state.show_review = False
    st.session_state.praise_shown = False


def _slot_from_dict(data: dict) -> DailySlot:
    slot_data = dict(data)
    if isinstance(slot_data.get("date"), str):
        slot_data["date"] = date.fromisoformat(slot_data["date"])
    return DailySlot(**slot_data)


def save_plan_snapshot(db_path: str, tasks: list[Task], slots: dict[date, DailySlot], plan: PlanResult):
    """Save current plan into tracker DB so it survives app restarts."""
    payload = {
        "tasks": [task.to_dict() for task in tasks],
        "slots": {day.isoformat(): slot.to_dict() for day, slot in slots.items()},
        "plan_json": plan.to_dict(),
    }
    conn = _connect_tracker_db(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO user_settings (key, value) VALUES (?, ?)",
            ("plan_snapshot", json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()


def load_existing_plan(db_path: str) -> tuple[list[Task] | None, dict[date, DailySlot] | None]:
    """Load previously generated task/schedule snapshot from SQLite."""
    if not os.path.exists(db_path):
        return None, None
    conn = _connect_tracker_db(db_path)
    try:
        row = conn.execute(
            "SELECT value FROM user_settings WHERE key = ?",
            ("plan_snapshot",),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None, None

    data = json.loads(row["value"])
    tasks = [Task.from_dict(task) for task in data.get("tasks", [])]
    slots = {
        date.fromisoformat(day): _slot_from_dict(slot)
        for day, slot in data.get("slots", {}).items()
    }
    return tasks, slots


def build_plan(tasks: list[Task], slots: dict[date, DailySlot]) -> PlanResult:
    """Generate a plan with task alternation enabled to avoid pile-ups."""
    engine = PlanningEngine(
        tasks=tasks,
        slots=slots,
        max_tasks_per_day=2,
        buffer_ratio=0.10,
    )
    return engine.plan()


def build_schedule(start: date, end: date, workday_h: float, weekend_h: float, holiday_h: float):
    settings = UserSettings(
        workday_hours=workday_h,
        weekend_hours=weekend_h,
        holiday_hours=holiday_h,
    )
    return ScheduleEngine(settings).generate(start, end)


def apply_soft_deadlines(tasks: list[Task], planning_start: date | None = None) -> list[Task]:
    """Infer soft deadlines for tasks without DDL so they receive daily load.

    The LLM still estimates difficulty and hours. This function turns a missing
    DDL into a conservative soft deadline so the planner increases daily amount
    instead of leaving the task as open-ended filler work.
    """
    start = planning_start or date.today()
    typed_daily_hours = {
        "memorize": 1.0,
        "exercise": 1.0,
        "reading": 1.0,
        "writing": 1.5,
        "project": 1.5,
        "other": 1.0,
    }
    existing_deadlines = [task.deadline for task in tasks if task.deadline]
    current_horizon = max(existing_deadlines, default=start + timedelta(days=21))

    for task in tasks:
        if task.is_daily_recurring:
            continue
        if task.deadline is not None:
            continue

        base_daily = typed_daily_hours.get(task.task_type, 1.0)
        difficulty_boost = max(0, task.difficulty - 3) * 0.25
        target_daily_hours = min(2.5, base_daily + difficulty_boost)
        estimated_hours = max(task.estimated_hours, 1.0)
        desired_days = max(3, math.ceil(estimated_hours / target_daily_hours))
        desired_days = min(desired_days, 30)
        soft_deadline = min(start + timedelta(days=desired_days), current_horizon + timedelta(days=7))
        if soft_deadline <= start:
            soft_deadline = start + timedelta(days=3)

        task.deadline = soft_deadline
        days = max(1, (soft_deadline - start).days)
        task.suggested_daily_hours = max(task.suggested_daily_hours, estimated_hours / days)
        note = f"No explicit DDL; added a soft deadline at {soft_deadline.isoformat()} for steady daily progress."
        task.notes = f"{task.notes} {note}".strip() if task.notes else note

    return tasks


def ensure_slots_cover_tasks(slots: dict[date, DailySlot], tasks: list[Task]) -> dict[date, DailySlot]:
    latest_deadline = max((task.deadline for task in tasks if task.deadline), default=None)
    if latest_deadline is None:
        return slots
    if slots and max(slots.keys()) >= latest_deadline:
        return slots
    start = min(slots.keys(), default=date.today())
    return build_schedule(start, latest_deadline, 2.0, 6.0, 4.0)


def analyze_text(raw_text: str, api_key: str, provider: str, language: str = "zh") -> list[Task]:
    analyzer = TaskAnalyzer(api_key=api_key, provider=provider)
    result = analyzer.analyze(raw_text, language=language)
    return result.tasks


def merge_tasks(existing: list[Task], new_tasks: list[Task]) -> list[Task]:
    """Merge tasks and avoid ID collisions."""
    merged = list(existing)
    existing_ids = {task.id for task in merged}
    next_idx = len(merged) + 1
    for task in new_tasks:
        if task.id in existing_ids:
            task.id = f"task_{next_idx:03d}"
        while task.id in existing_ids:
            next_idx += 1
            task.id = f"task_{next_idx:03d}"
        existing_ids.add(task.id)
        merged.append(task)
        next_idx += 1
    return merged


def reset_today_state_after_replan(tracker: DailyTracker, plan: PlanResult, tasks: list[Task]):
    """Rebuild today's check list while preserving already selected tiers."""
    old_state = tracker.storage.get_checkin_state(tracker.today)
    selected = {}
    if old_state:
        selected = {item.task_id: item.selected_tier for item in old_state.tasks if item.selected_tier}

    new_state = tracker._create_from_plan(tracker.today, plan, tasks)
    if old_state:
        new_state.phase1_done = old_state.phase1_done
        new_state.greeting_shown = old_state.greeting_shown
        new_state.phase1_time = old_state.phase1_time
    for item in new_state.tasks:
        if item.task_id in selected:
            item.selected_tier = selected[item.task_id]
    if new_state.all_min_selected:
        new_state.phase2_done = True
    tracker.storage.save_checkin_state(new_state)
    st.session_state.today_state = new_state
    return new_state


def parse_uploaded_file(uploaded_file):
    suffix = os.path.splitext(uploaded_file.name)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name
    try:
        return parse_document(tmp_path)
    finally:
        os.unlink(tmp_path)


with st.expander("⚙️ " + ("设置" if lang == "zh" else "Settings"), expanded=False):
    db_path = st.text_input(_("tracker_db_label"), value="tracker.db")
    settle_h = st.slider(_("tracker_settle_label"), 0, 23, 0, help=_("tracker_settle_hint"))
    saved_opacity = int(get_db_setting(db_path, "sticky_opacity", str(st.session_state.sticky_opacity)))
    opacity = st.slider(_("sticky_opacity_label"), 40, 100, saved_opacity, 5, help=_("sticky_opacity_hint"))
    if opacity != saved_opacity:
        set_db_setting(db_path, "sticky_opacity", str(opacity))
    st.session_state.sticky_opacity = opacity

    st.session_state.provider = st.selectbox(
        "Provider",
        ["deepseek", "openai"],
        format_func=lambda value: "DeepSeek" if value == "deepseek" else "OpenAI",
        index=0 if st.session_state.provider == "deepseek" else 1,
    )
    st.session_state.api_key = st.text_input(
        _("api_key_label"),
        value=st.session_state.api_key,
        type="password",
        placeholder=_("api_key_placeholder"),
    )
    st.caption(_("api_key_help"))

    if st.button("📅 " + ("重新加载已有计划" if lang == "zh" else "Reload Existing Plan")):
        loaded_tasks, loaded_slots = load_existing_plan(db_path)
        if loaded_tasks and loaded_slots:
            st.session_state.analyzed_tasks = loaded_tasks
            st.session_state.slots = loaded_slots
            st.session_state.plan_result = build_plan(loaded_tasks, loaded_slots)
            st.success("✅ " + ("已加载" if lang == "zh" else "Loaded"))
        else:
            st.warning("⚠️ " + ("未找到已有计划" if lang == "zh" else "No existing plan found"))

    st.divider()
    if not st.session_state.delete_tasks_pending:
        if st.button(_("delete_tasks_btn"), type="secondary"):
            st.session_state.delete_tasks_pending = True
            st.rerun()
    else:
        st.warning(_("delete_tasks_confirm_text"))
        col_delete, col_cancel = st.columns(2)
        with col_delete:
            if st.button(_("delete_tasks_confirm_btn"), type="primary"):
                clear_current_plan(db_path, date.today())
                st.session_state.delete_tasks_pending = False
                st.success(_("delete_tasks_done"))
                st.rerun()
        with col_cancel:
            if st.button(_("delete_tasks_cancel_btn")):
                st.session_state.delete_tasks_pending = False
                st.rerun()

st.markdown(
    f"""
<style>
.main .block-container {{
    opacity: {st.session_state.sticky_opacity / 100:.2f};
}}
</style>
""",
    unsafe_allow_html=True,
)


if st.session_state.tracker is None:
    st.session_state.tracker = DailyTracker(db_path)

tracker: DailyTracker = st.session_state.tracker
tracker.settlement_hour = settle_h

if st.session_state.plan_result is None or st.session_state.analyzed_tasks is None or st.session_state.slots is None:
    loaded_tasks, loaded_slots = load_existing_plan(db_path)
    if loaded_tasks and loaded_slots:
        st.session_state.analyzed_tasks = loaded_tasks
        st.session_state.slots = loaded_slots
        st.session_state.plan_result = build_plan(loaded_tasks, loaded_slots)

plan = st.session_state.plan_result
tasks = st.session_state.analyzed_tasks
slots = st.session_state.slots

if plan and tasks:
    state = tracker.get_or_create_today(plan=plan, tasks=tasks)
else:
    state = tracker.get_or_create_today()


col_t, col_l = st.columns([3, 1])
with col_t:
    st.markdown(f"### {_('tracker_title')}")
with col_l:
    new_lang = st.selectbox(
        "Language",
        ["zh", "en"],
        format_func=lambda value: "中" if value == "zh" else "EN",
        label_visibility="collapsed",
        index=0 if lang == "zh" else 1,
    )
    if new_lang != lang:
        st.session_state.lang = new_lang
        st.rerun()

st.caption(state.date.isoformat() + " " + (
    ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][state.date.weekday()]
    if lang == "zh" else
    ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][state.date.weekday()]
))


def render_creation_mode():
    st.divider()
    st.markdown(f"#### {_('create_mode_title')}")
    st.caption(_("create_mode_sub"))

    tab_upload, tab_text = st.tabs([_("create_mode_upload"), _("create_mode_text")])
    uploaded_file = None
    typed_text = ""
    with tab_upload:
        uploaded_file = st.file_uploader("PDF / Word / TXT / MD", type=["pdf", "docx", "txt", "md"])
    with tab_text:
        typed_text = st.text_area(
            _("create_mode_text"),
            placeholder=_("create_mode_text_placeholder"),
            height=140,
        )

    if st.button(_("create_mode_parse"), type="primary"):
        try:
            if typed_text.strip():
                st.session_state.create_doc = parse_document(raw_text=typed_text.strip())
            elif uploaded_file is not None:
                st.session_state.create_doc = parse_uploaded_file(uploaded_file)
            else:
                st.warning(_("warning_empty"))
        except Exception as exc:
            st.error(translate_error(exc, lang))

    if st.session_state.create_doc:
        st.success(_("create_mode_parsed"))
        with st.expander(_("text_preview_label"), expanded=False):
            st.text_area(
                _("text_preview_label"),
                value=st.session_state.create_doc.raw_text,
                height=120,
                label_visibility="collapsed",
            )

        if st.button(_("create_mode_analyze"), type="primary"):
            if not st.session_state.api_key.strip():
                st.error(_("create_mode_analyze_need_key"))
            else:
                with st.spinner(_("analyzing")):
                    new_tasks = analyze_text(
                        st.session_state.create_doc.raw_text,
                        st.session_state.api_key.strip(),
                        st.session_state.provider,
                        lang,
                    )
                    st.session_state.create_analysis = apply_soft_deadlines(new_tasks)

    if st.session_state.create_analysis:
        st.success(_("create_mode_analyzed").format(count=len(st.session_state.create_analysis)))
        for task in st.session_state.create_analysis:
            st.caption(f"• {task.description} | {task.total_amount:g} {task.unit} | DDL: {task.deadline or '—'}")

        col1, col2, col3 = st.columns(3)
        with col1:
            workday_h = st.number_input(_("create_mode_workday_h"), 0.0, 16.0, 2.0, 0.5)
        with col2:
            weekend_h = st.number_input(_("create_mode_weekend_h"), 0.0, 16.0, 6.0, 0.5)
        with col3:
            holiday_h = st.number_input(_("create_mode_holiday_h"), 0.0, 16.0, 4.0, 0.5)

        today = date.today()
        start = st.date_input(_("create_mode_start"), today)
        latest_deadline = max((task.deadline for task in st.session_state.create_analysis if task.deadline), default=today + timedelta(days=30))
        end = st.date_input(_("create_mode_end"), latest_deadline)

        if st.button(_("create_mode_schedule").format(days=(end - start).days + 1)):
            with st.spinner(_("schedule_generating")):
                st.session_state.create_slots = build_schedule(start, end, workday_h, weekend_h, holiday_h)

    if st.session_state.create_slots:
        st.success(_("create_mode_scheduled").format(days=len(st.session_state.create_slots)))
        if st.button(_("create_mode_plan"), type="primary"):
            plan_result = build_plan(st.session_state.create_analysis, st.session_state.create_slots)
            st.session_state.analyzed_tasks = st.session_state.create_analysis
            st.session_state.slots = st.session_state.create_slots
            st.session_state.plan_result = plan_result
            save_plan_snapshot(db_path, st.session_state.analyzed_tasks, st.session_state.slots, plan_result)
            reset_today_state_after_replan(tracker, plan_result, st.session_state.analyzed_tasks)
            st.success(_("create_mode_planned"))
            st.rerun()


if not plan or not tasks:
    render_creation_mode()
    st.divider()
    st.caption("Task Planner Agent — Daily Tracker v0.6")
    st.stop()


def render_import_task():
    with st.expander(_("import_task_title"), expanded=False):
        import_text = st.text_area(
            _("import_task_label"),
            placeholder=_("import_task_placeholder"),
            height=100,
            key="import_task_text",
        )
        uploaded_import = st.file_uploader(
            _("create_mode_upload"),
            type=["pdf", "docx", "txt", "md"],
            key="import_task_file",
        )
        if st.button(_("import_task_btn"), type="primary"):
            if not st.session_state.api_key.strip():
                st.error(_("create_mode_analyze_need_key"))
                return
            try:
                with st.spinner(_("import_task_parsing")):
                    if import_text.strip():
                        doc = parse_document(raw_text=import_text.strip())
                    elif uploaded_import is not None:
                        doc = parse_uploaded_file(uploaded_import)
                    else:
                        st.warning(_("warning_empty"))
                        return
                with st.spinner(_("import_task_analyzing")):
                    added_tasks = analyze_text(doc.raw_text, st.session_state.api_key.strip(), st.session_state.provider, lang)
                with st.spinner(_("import_task_replanning")):
                    merged = apply_soft_deadlines(merge_tasks(st.session_state.analyzed_tasks or [], added_tasks))
                    if not st.session_state.slots:
                        start = date.today()
                        end = max((task.deadline for task in merged if task.deadline), default=start + timedelta(days=30))
                        st.session_state.slots = build_schedule(start, end, 2.0, 6.0, 4.0)
                    st.session_state.slots = ensure_slots_cover_tasks(st.session_state.slots, merged)
                    new_plan = build_plan(merged, st.session_state.slots)
                    st.session_state.analyzed_tasks = merged
                    st.session_state.plan_result = new_plan
                    save_plan_snapshot(db_path, merged, st.session_state.slots, new_plan)
                    reset_today_state_after_replan(tracker, new_plan, merged)
                st.success(_("import_task_done").format(count=len(added_tasks), total=len(merged)))
                st.rerun()
            except Exception as exc:
                st.error(f"{_('error_generic')}{exc}")


st.info(tracker.get_daily_motivation(lang))

if not state.phase1_done and not st.session_state.show_review:
    st.divider()
    greeting = tracker.get_greeting_quote(lang)
    st.markdown(f"💬 *{greeting}*")

    enc = tracker.get_today_encouragement(lang)
    if enc:
        st.success(enc)

    yesterday_summary = tracker.get_yesterday_summary(lang)
    if yesterday_summary:
        with st.expander(_("tracker_yesterday_label"), expanded=True):
            st.markdown(yesterday_summary)

    progress_text = tracker.get_progress_summary(tasks, lang)
    with st.expander(_("tracker_progress_label"), expanded=True):
        st.markdown(progress_text)

    if state.tasks:
        with st.expander(_("tracker_today_goals"), expanded=True):
            for item in state.tasks:
                st.markdown(
                    f"• **{item.description}**: "
                    f"{_('tracker_tier_min')} {item.tier_min:.0f}{item.unit} / "
                    f"{_('tracker_tier_ideal')} {item.tier_ideal:.0f}{item.unit} / "
                    f"{_('tracker_tier_challenge')} {item.tier_challenge:.0f}{item.unit}"
                )

    if not state.greeting_shown:
        st.info(_("tracker_first_tip"))

    if st.button(_("tracker_phase1_confirm"), type="primary"):
        tracker.confirm_phase1(state)
        st.rerun()

elif st.session_state.show_review and state.phase1_done:
    st.divider()
    st.markdown(f"#### {_('tracker_return_news')}")
    st.info(tracker.get_news_or_joke(lang))
    with st.expander(_("tracker_progress_label"), expanded=True):
        st.markdown(tracker.get_progress_summary(tasks, lang))
    render_import_task()
    if st.button(_("tracker_back_btn"), type="primary"):
        st.session_state.show_review = False
        st.rerun()

elif state.phase1_done:
    st.divider()
    st.markdown(f"**{_('tracker_phase2_header')}**")
    render_import_task()

    col_r1, _col_r2 = st.columns([1, 3])
    with col_r1:
        if st.button(_("tracker_review_btn")):
            st.session_state.show_review = True
            st.rerun()

    if state.all_min_selected and not st.session_state.praise_shown:
        praise = tracker.get_today_praise(lang)
        if praise:
            st.balloons()
            st.success(praise)
            st.session_state.praise_shown = True

    for item in state.tasks:
        with st.container(border=True):
            hours = {
                "min": item.tier_min_hours,
                "ideal": item.tier_ideal_hours,
                "challenge": item.tier_challenge_hours,
            }
            amounts = {"min": item.tier_min, "ideal": item.tier_ideal, "challenge": item.tier_challenge}
            tier_label = (
                {"min": "最低", "ideal": "理想", "challenge": "挑战"}
                if lang == "zh" else
                {"min": "Min", "ideal": "Ideal", "challenge": "Challenge"}
            )

            if item.selected_tier:
                selected = item.selected_tier
                st.markdown(
                    f"✅ **{item.description}** — {tier_label[selected]}: "
                    f"{amounts[selected]:.0f} {item.unit} ({hours[selected]:.1f}h)"
                )
            else:
                st.markdown(f"**{item.description}**")
                cols = st.columns(3)
                choices = [
                    ("min", _("tracker_tier_min"), item.tier_min),
                    ("ideal", _("tracker_tier_ideal"), item.tier_ideal),
                    ("challenge", _("tracker_tier_challenge"), item.tier_challenge),
                ]
                for col, (tier, label, amount) in zip(cols, choices):
                    with col:
                        if st.button(
                            f"{label}\n{amount:.0f}{item.unit}",
                            key=f"{tier}_{item.task_id}",
                            use_container_width=True,
                            type="primary" if tier == "ideal" else "secondary",
                        ):
                            st.session_state.confirm_pending = (item.task_id, tier)
                            st.rerun()

    st.divider()
    if state.tasks:
        done = sum(1 for item in state.tasks if item.selected_tier is not None)
        total = len(state.tasks)
        st.progress(done / total, text=f"{done}/{total} " + ("已完成" if lang == "zh" else "Done"))
        if done < total:
            st.caption(_("tracker_some_left").format(count=total - done))
        else:
            st.success(_("tracker_all_done"))


if st.session_state.confirm_pending:
    task_id, tier = st.session_state.confirm_pending
    item = next((task for task in state.tasks if task.task_id == task_id), None)
    if item:
        labels = {"min": _("tracker_tier_min"), "ideal": _("tracker_tier_ideal"), "challenge": _("tracker_tier_challenge")}
        amounts = {"min": item.tier_min, "ideal": item.tier_ideal, "challenge": item.tier_challenge}
        hours = {"min": item.tier_min_hours, "ideal": item.tier_ideal_hours, "challenge": item.tier_challenge_hours}
        st.divider()
        st.warning(
            _("tracker_confirm_tier").format(
                tier=labels[tier],
                desc=item.description,
                amount=amounts[tier],
                unit=item.unit,
                hours=hours[tier],
            )
        )
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("✅ " + ("确认" if lang == "zh" else "Confirm"), type="primary"):
                result = tracker.select_tier(state, task_id, tier)
                st.session_state.confirm_pending = None
                if result == "ok_all_done":
                    st.session_state.praise_shown = False
                st.rerun()
        with col_no:
            if st.button("❌ " + ("取消" if lang == "zh" else "Cancel")):
                st.session_state.confirm_pending = None
                st.rerun()


st.divider()
st.caption("Task Planner Agent — Daily Tracker v0.6")
