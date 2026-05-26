"""
Streamlit Setup App — Configure tasks, schedule, and generate the daily plan.
The daily tracker (tracker_app.py) reads the plan from tracker.db.

Run:
    streamlit run app.py
"""

import json
import os
import sqlite3
import tempfile
import streamlit as st

from doc_parser import parse_document, ParsedDocument
from doc_parser.i18n import t, translate_error, Lang
from task_analyzer import TaskAnalyzer, TaskAnalysisResult
from schedule_engine import ScheduleEngine, UserSettings
from planning_engine import PlanningEngine

# ── Page config ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="Task Planner Agent — Doc Parser",
    page_icon="📋",
    layout="wide",
)

# ── Session state init ──────────────────────────────────────────────
if "lang" not in st.session_state:
    st.session_state.lang = "zh"
if "parsed_doc" not in st.session_state:
    st.session_state.parsed_doc = None
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "api_key" not in st.session_state:
    st.session_state.api_key = os.environ.get("DEEPSEEK_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
if "provider" not in st.session_state:
    st.session_state.provider = "deepseek"
if "schedule_slots" not in st.session_state:
    st.session_state.schedule_slots = None
if "plan_result" not in st.session_state:
    st.session_state.plan_result = None

lang: Lang = st.session_state.lang


# ── Helper: get i18n string ─────────────────────────────────────────
def _(key: str) -> str:
    return t(key, lang)


def _parse_json_map(i18n_key: str) -> dict:
    """Safely parse a JSON map string from i18n into a Python dict."""
    raw = t(i18n_key, lang)
    # Handle double-brace escaping in format strings
    raw = raw.replace("{{", "{").replace("}}", "}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _save_plan_snapshot(tasks, slots, result):
    """Save plan data to tracker.db so tracker_app.py can read it."""
    db_path = "tracker.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        snapshot = {
            "tasks": [t.to_dict() for t in tasks],
            "slots": {k.isoformat(): v.to_dict() for k, v in slots.items()},
            "plan_json": result.to_dict(),
        }
        conn.execute(
            "INSERT OR REPLACE INTO user_settings (key, value) VALUES (?, ?)",
            ("plan_snapshot", json.dumps(snapshot, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()


# ── Sidebar ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### " + _("lang_label"))
    new_lang = st.radio(
        label=_("lang_label"),
        options=["zh", "en"],
        format_func=lambda x: "🇨🇳 中文" if x == "zh" else "🇺🇸 English",
        index=0 if lang == "zh" else 1,
        horizontal=True,
        label_visibility="collapsed",
        key="lang_radio",
    )
    if new_lang != lang:
        st.session_state.lang = new_lang
        st.rerun()

    st.divider()

    # ── LLM API Settings ──
    st.markdown("### " + _("provider_label"))
    st.session_state.provider = st.selectbox(
        label="Provider",
        options=["deepseek", "openai"],
        format_func=lambda x: "DeepSeek" if x == "deepseek" else "OpenAI",
        index=0 if st.session_state.provider == "deepseek" else 1,
    )

    st.session_state.api_key = st.text_input(
        label=_("api_key_label"),
        value=st.session_state.api_key,
        type="password",
        placeholder=_("api_key_placeholder"),
    )
    st.caption(_("api_key_help"))

    st.divider()

    # Status area
    if st.session_state.analysis_result:
        count = len(st.session_state.analysis_result.tasks)
        st.success(_("analysis_success").format(count=count))
    elif st.session_state.parsed_doc:
        st.success(_("success_parsed"))
    else:
        st.info("⏳ " + (_("warning_empty") if lang == "zh" else "⏳ Ready for input"))


# ── Main content ────────────────────────────────────────────────────
st.title(_("app_title"))
st.caption(_("app_subtitle"))

# ── Progress indicator ──────────────────────────────────────────────
progress_steps = {
    "zh": ["📄 解析 ✅", "🧠 分析 ✅", "📅 日程 ✅", "⚙️ 规划 ✅", "📊 追踪 ✅"],
    "en": ["📄 Parse ✅", "🧠 Analyze ✅", "📅 Sched ✅", "⚙️ Plan ✅", "📊 Track ✅"],
}
st.caption("  →  ".join(progress_steps[lang]))
st.caption(
    "💡 " + (
        "配置完成后，运行 `streamlit run tracker_app.py` 打开每日便利贴打卡窗口。"
        if lang == "zh" else
        "After setup, run `streamlit run tracker_app.py` for the daily sticky-note tracker."
    )
)

st.divider()

# ── Input Section ───────────────────────────────────────────────────
st.subheader(_("input_header"))

tab_upload, tab_text = st.tabs([_("tab_upload"), _("tab_text")])

uploaded_file = None
manual_text = ""

with tab_upload:
    st.caption(_("upload_help"))
    uploaded_file = st.file_uploader(
        label=_("upload_label"),
        type=["pdf", "docx", "txt", "md"],
        key="file_uploader",
    )

with tab_text:
    st.caption(_("text_help"))
    manual_text = st.text_area(
        label=_("text_label"),
        placeholder=_("text_placeholder"),
        height=200,
        key="text_input",
    )

# ── Parse Button ────────────────────────────────────────────────────
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    parse_clicked = st.button(
        _("parse_btn"),
        use_container_width=True,
        type="primary",
    )

# ── Parse Logic ─────────────────────────────────────────────────────
if parse_clicked:
    try:
        with st.spinner(_("parsing")):
            if manual_text.strip():
                doc = parse_document(raw_text=manual_text.strip())
                st.session_state.parsed_doc = doc
            elif uploaded_file is not None:
                # Save uploaded file to temp path
                suffix = os.path.splitext(uploaded_file.name)[1].lower()
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=suffix
                ) as tmp:
                    tmp.write(uploaded_file.read())
                    tmp_path = tmp.name
                try:
                    doc = parse_document(tmp_path)
                    st.session_state.parsed_doc = doc
                finally:
                    os.unlink(tmp_path)
            else:
                st.warning(_("warning_empty"))
    except Exception as e:
        st.error(translate_error(e, lang))

# ── Results Section ─────────────────────────────────────────────────
doc = st.session_state.parsed_doc

if doc:
    st.divider()
    st.subheader(_("result_header"))

    # Metadata grid
    meta_cols = st.columns(4 if doc.metadata else 3)

    with meta_cols[0]:
        st.metric(label=_("file_type_label"), value=doc.file_type.upper())
    with meta_cols[1]:
        source_display = "📝 Manual Input" if doc.source == "manual_input" else doc.source
        st.metric(label=_("source_label"), value=source_display)
    with meta_cols[2]:
        st.metric(label=_("char_count_label"), value=len(doc.raw_text))

    if doc.metadata:
        with meta_cols[3]:
            if "line_count" in doc.metadata:
                st.metric(label=_("line_count_label"), value=doc.metadata["line_count"])
            elif "pages_with_text" in doc.metadata:
                st.metric(
                    label=_("page_count_label"),
                    value=f"{doc.metadata['pages_with_text']}/{doc.page_count}"
                )
            elif "paragraph_count" in doc.metadata:
                st.metric(label=_("para_count_label"), value=doc.metadata["paragraph_count"])

    if doc.metadata and "table_count" in doc.metadata:
        st.caption(f"📊 {_('table_count_label')}: {doc.metadata['table_count']}")

    # Text preview
    st.text_area(
        label=_("text_preview_label"),
        value=doc.raw_text,
        height=300,
        key="text_preview",
    )

    # Download button
    col_dl, col_hint = st.columns([1, 3])
    with col_dl:
        st.download_button(
            label=_("download_label"),
            data=doc.raw_text,
            file_name=f"extracted_{doc.file_type}.txt",
            mime="text/plain",
        )
    with col_hint:
        st.info(_("next_step_hint"))

# ── Task Analysis Section ───────────────────────────────────────────
if doc:
    st.divider()
    st.subheader(_("analyzer_header"))

    col_btn1, col_btn2 = st.columns([1, 3])
    with col_btn1:
        analyze_clicked = st.button(
            _("analyze_btn"),
            use_container_width=True,
            type="primary",
            key="analyze_btn",
        )

    if analyze_clicked:
        api_key = st.session_state.api_key.strip()
        if not api_key:
            st.error(_("analysis_missing_key"))
        else:
            try:
                with st.spinner(_("analyzing")):
                    analyzer = TaskAnalyzer(
                        api_key=api_key,
                        provider=st.session_state.provider,
                    )
                    result = analyzer.analyze(doc.raw_text, language=lang)
                    st.session_state.analysis_result = result
            except Exception as e:
                st.error(f"{_('error_generic')}{e}")

# ── Analysis Results ────────────────────────────────────────────────
analysis = st.session_state.analysis_result

if analysis:
    task_count = len(analysis.tasks)

    if task_count == 0:
        st.warning(_("no_tasks_found"))
    else:
        # Success / warning banner
        wc = len(analysis.warnings)
        if wc > 0:
            st.warning(_("analysis_warning").format(count=wc))
        else:
            st.success(_("analysis_success").format(count=task_count))

        # Load type/difficulty maps
        type_map = _parse_json_map("task_type_map")
        diff_map = _parse_json_map("difficulty_map")

        # Task cards
        for task in analysis.tasks:
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    type_display = type_map.get(task.task_type, task.task_type)
                    st.metric(label=_("task_type_label"), value=type_display)
                    st.caption(task.description)

                with col2:
                    st.metric(
                        label=_("task_amount_label"),
                        value=f"{task.total_amount:g} {task.unit}"
                    )
                    st.metric(
                        label=_("task_hours_label"),
                        value=f"{task.estimated_hours:.1f}h"
                    )

                with col3:
                    diff_display = diff_map.get(str(task.difficulty), f"⭐{task.difficulty}")
                    st.metric(label=_("task_difficulty_label"), value=diff_display)
                    st.metric(
                        label=_("task_confidence_label"),
                        value=f"{task.confidence:.0%}"
                    )

                with col4:
                    deadline_str = task.deadline.isoformat() if task.deadline else "—"
                    st.metric(label=_("task_deadline_label"), value=deadline_str)
                    days = task.days_until_deadline
                    if days is not None:
                        st.caption(f"{_('days_left_label')}: {days} 天" if lang == "zh" else f"{_('days_left_label')}: {days} days")
                    if task.suggested_daily_hours > 0:
                        st.caption(
                            f"{_('task_daily_label')}: {task.suggested_daily_hours:.1f}h/天" if lang == "zh"
                            else f"{_('task_daily_label')}: {task.suggested_daily_hours:.1f}h/day"
                        )

                if task.notes:
                    st.caption(f"💬 {task.notes}")

        # Warnings
        if analysis.warnings:
            with st.expander(
                "⚠️ " + ("分析警告" if lang == "zh" else "Analysis Warnings")
            ):
                for w in analysis.warnings:
                    st.warning(w)

        # Raw JSON toggle
        with st.expander(_("raw_json_label")):
            st.json(json.loads(analysis.raw_response))
            st.caption(
                f"Model: {analysis.model_used} | "
                f"Tokens: {analysis.tokens_used}"
            )

        st.caption(_("task_edit_hint"))

# ── Schedule Engine Section ─────────────────────────────────────────
st.divider()
st.subheader(_("schedule_header"))

# Settings
col_wd, col_we, col_ho = st.columns(3)
with col_wd:
    wd_hours = st.number_input(
        _("schedule_workday_label"),
        min_value=0.0, max_value=16.0, value=2.0, step=0.5,
    )
with col_we:
    we_hours = st.number_input(
        _("schedule_weekend_label"),
        min_value=0.0, max_value=16.0, value=6.0, step=0.5,
    )
with col_ho:
    ho_hours = st.number_input(
        _("schedule_holiday_label"),
        min_value=0.0, max_value=16.0, value=4.0, step=0.5,
    )

# Date range
col_start, col_end = st.columns(2)
with col_start:
    start_date = st.date_input(
        _("schedule_start_label"),
        value="today" if lang == "zh" else "today",
    )
with col_end:
    end_date = st.date_input(
        _("schedule_end_label"),
        value=None,
    )
# Default end = start + 30 days
if end_date is None:
    end_date = start_date + __import__("datetime").timedelta(days=30)

# Manual busy time
with st.expander(
    "📝 " + ("手动标记忙碌时段" if lang == "zh" else "Mark Busy Time")
):
    busy_text = st.text_area(
        label=_("schedule_busy_label"),
        placeholder=_("schedule_busy_placeholder"),
        height=100,
        key="busy_input",
    )
    st.caption(_("schedule_busy_help"))

# Generate button
col_g1, col_g2, col_g3 = st.columns([1, 2, 1])
with col_g2:
    schedule_clicked = st.button(
        _("schedule_generate_btn"),
        use_container_width=True,
        type="primary",
        key="schedule_btn",
    )

if schedule_clicked:
    # Parse manual busy
    manual_busy: dict[str, float] = {}
    if busy_text.strip():
        for line in busy_text.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                parts = line.split("=", 1)
                try:
                    d = parts[0].strip()
                    h = float(parts[1].split("#")[0].strip())
                    manual_busy[d] = h
                except (ValueError, IndexError):
                    pass

    try:
        with st.spinner(_("schedule_generating")):
            settings = UserSettings(
                workday_hours=wd_hours,
                weekend_hours=we_hours,
                holiday_hours=ho_hours,
                manual_busy=manual_busy,
            )
            engine = ScheduleEngine(settings)
            slots = engine.generate(start_date, end_date)
            st.session_state.schedule_slots = slots
    except Exception as e:
        st.error(f"{_('error_generic')}{e}")

# ── Schedule Results ────────────────────────────────────────────────
slots = st.session_state.schedule_slots

if slots:
    st.subheader(_("schedule_result_header"))

    # Summary
    total = sum(s.available_hours for s in slots.values())
    days = len(slots)
    workdays = sum(1 for s in slots.values() if s.is_workday)
    holidays = sum(1 for s in slots.values() if s.is_holiday)
    weekends = days - workdays - holidays

    st.caption(
        _("schedule_summary").format(days=days, total_hours=total, avg=total / days)
    )

    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    with col_s1:
        st.metric(label=_("schedule_workday_count"), value=workdays)
    with col_s2:
        st.metric(
            label=_("schedule_weekend_count"),
            value=weekends if weekends >= 0 else 0,
        )
    with col_s3:
        st.metric(label=_("schedule_holiday_count"), value=holidays)
    with col_s4:
        st.metric(
            label=("日均可用" if lang == "zh" else "Avg/Day"),
            value=f"{total/days:.1f}h"
        )

    st.caption(_("schedule_holiday_tip"))

    # Table
    sorted_slots = sorted(slots.values(), key=lambda s: s.date)
    if days <= 62:  # Don't render huge tables
        # Build compact table
        table_data = []
        for s in sorted_slots:
            type_str = ""
            if s.is_holiday:
                type_str = f"🏮 {s.holiday_name}" if s.holiday_name else "🏮 Holiday"
            elif s.is_workday:
                type_str = "💼 Work" if lang == "en" else "💼 工作日"
            else:
                type_str = "🏠 Weekend" if lang == "en" else "🏠 周末"

            table_data.append({
                _("schedule_table_date"): s.date.isoformat(),
                _("schedule_table_day"): s.day_of_week,
                _("schedule_table_type"): type_str,
                _("schedule_table_available"): f"{s.available_hours:.1f}",
                _("schedule_table_base"): f"{s.base_hours:.1f}",
                _("schedule_table_busy"): f"{s.manual_busy_hours:.1f}" if s.manual_busy_hours > 0 else "—",
            })

        st.dataframe(
            table_data,
            use_container_width=True,
            hide_index=True,
            height=min(35 * days + 38, 500),
        )

    # Download schedule as CSV
    csv_lines = ["date,day_of_week,type,available_hours,base_hours,busy_hours"]
    for s in sorted_slots:
        type_str = "holiday" if s.is_holiday else ("workday" if s.is_workday else "weekend")
        csv_lines.append(
            f"{s.date.isoformat()},{s.day_of_week},{type_str},"
            f"{s.available_hours:.1f},{s.base_hours:.1f},{s.manual_busy_hours:.1f}"
        )
    st.download_button(
        label="📥 " + ("下载 CSV" if lang == "zh" else "Download CSV"),
        data="\n".join(csv_lines),
        file_name=f"schedule_{start_date}_{end_date}.csv",
        mime="text/csv",
    )

# ── Planning Engine Section ────────────────────────────────────────
if analysis and slots:
    st.divider()
    st.subheader(_("planner_header"))

    col_p1, col_p2 = st.columns([1, 3])
    with col_p1:
        plan_clicked = st.button(
            _("planner_btn"),
            use_container_width=True,
            type="primary",
            key="plan_btn",
        )

    if plan_clicked:
        try:
            with st.spinner(_("planner_generating")):
                engine = PlanningEngine(
                    tasks=analysis.tasks,
                    slots=slots,
                )
                result = engine.plan()
                st.session_state.plan_result = result

                # ── Save plan snapshot for tracker app ─────────────
                _save_plan_snapshot(analysis.tasks, slots, result)
        except Exception as e:
            st.error(f"{_('error_generic')}{e}")

# ── Plan Results ───────────────────────────────────────────────────
plan = st.session_state.plan_result

if plan:
    wc = len(plan.warnings)
    if wc > 0:
        st.warning(_("planner_warning").format(count=wc))
    else:
        st.success(
            _("planner_success").format(
                days=plan.day_count, tasks=len(plan.progress)
            )
        )

    # ── Warnings expander ──
    if plan.warnings:
        with st.expander(_("planner_warnings_header")):
            for w in plan.warnings:
                st.warning(w)

    # ── Progress overview ──
    st.subheader(_("planner_progress_header"))
    prog_data = []
    for p in sorted(plan.progress.values(), key=lambda x: x.progress_pct):
        pct = p.progress_pct
        emoji = "🟢" if pct >= 0.99 else ("🟡" if pct >= 0.7 else "🔴")
        prog_data.append({
            _("planner_progress_task"): f"{emoji} {p.description}",
            _("planner_progress_done"): f"{p.completed:.1f}",
            _("planner_progress_total"): f"{p.total_amount:.1f} {p.unit}",
            _("planner_progress_pct"): f"{pct:.0%}",
            _("planner_progress_hours"): f"{p.total_hours:.1f}",
        })
    st.dataframe(prog_data, use_container_width=True, hide_index=True)

    # ── Daily plan table ──
    st.subheader(_("planner_header"))
    for daily in plan.days:
        if not daily.allocations:
            continue  # Skip empty days
        with st.container(border=True):
            cap_text = (
                f"📅 {daily.date} {daily.day_of_week}  |  "
                f"{_('planner_table_available')}: {daily.available_hours:.1f}h  |  "
                f"{_('planner_table_allocated')}: {daily.total_allocated_hours:.1f}h"
            )
            if daily.slack_hours > 0.1:
                cap_text += f"  |  {_('planner_table_slack')}: {daily.slack_hours:.1f}h"
            st.caption(cap_text)

            for alloc in daily.allocations:
                catch_tag = f" {_('planner_catch_up_tag')}" if alloc.is_catch_up else ""
                type_icon = {"memorize": "📖", "exercise": "📐", "reading": "📚",
                             "writing": "✍️", "project": "📁"}.get(alloc.task_type, "📌")
                st.write(
                    f"{type_icon} **{alloc.description}**{catch_tag}: "
                    f"{alloc.amount:.1f} {alloc.unit}（{alloc.hours:.1f}h）"
                )

    # ── Download plan CSV ──
    csv_plan = ["date,day,task_id,description,amount,unit,hours"]
    for daily in plan.days:
        for a in daily.allocations:
            csv_plan.append(
                f"{daily.date},{daily.day_of_week},{a.task_id},"
                f"{a.description},{a.amount:.1f},{a.unit},{a.hours:.1f}"
            )
    st.download_button(
        label=_("planner_download_csv"),
        data="\n".join(csv_plan),
        file_name="daily_plan.csv",
        mime="text/csv",
    )

elif not analysis and not slots:
    st.caption(_("planner_no_tasks"))
elif not analysis:
    st.caption(_("planner_no_tasks"))
elif not slots:
    st.caption(_("planner_no_slots"))

# ── Footer ──────────────────────────────────────────────────────────
st.divider()
st.caption(_("footer"))
