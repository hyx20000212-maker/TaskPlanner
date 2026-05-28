"""Lightweight desktop shell MVP for the Task Planner Agent.

Run:
    python -m desktop_app.main

MVP scope:
    - System tray icon with show/hide, refresh, opacity, delete current tasks, exit
    - Small always-on-top sticky-note window implemented with tkinter
    - Reads existing tracker.db plan_snapshot
    - Shows today's tasks and supports min/ideal/challenge check-in
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
import threading
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox

from PIL import Image, ImageDraw
import pystray

from daily_tracker import DailyTracker
from doc_parser import parse_document
from planning_engine.models import PlanResult
from planning_engine import PlanningEngine
from schedule_engine import ScheduleEngine, UserSettings
from schedule_engine.models import DailySlot
from task_analyzer import TaskAnalyzer, decompose_goal, generate_plan_rationale
from task_analyzer.models import Task


if getattr(sys, "frozen", False):
    ROOT_DIR = Path(sys.executable).resolve().parent
else:
    ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT_DIR / "tracker.db"


COLORS = {
    "paper": "#fff6bf",
    "paper_dark": "#d8c66a",
    "ink": "#222222",
    "muted": "#675f2b",
    "card": "#fffbe0",
    "button": "#d6b73f",
    "button_active": "#c7a934",
    "green": "#207245",
    "tier_min": "#b9ddff",
    "tier_ideal": "#ffffff",
    "tier_challenge": "#ffd0d6",
}


DESKTOP_TEXT = {
    "zh": {
        "title": "今日任务",
        "settings": "设置",
        "set_language": "设置语言",
        "set_nickname": "设置昵称",
        "nickname": "昵称",
        "nickname_placeholder": "用户",
        "greeting_morning": "早上好，{nickname}。",
        "greeting_noon": "中午好，{nickname}。",
        "greeting_evening": "晚上好，{nickname}。",
        "pin_window": "固定窗口",
        "unpin_window": "取消固定",
        "set_opacity": "透明度",
        "adjust_schedule": "调整日程",
        "save": "保存",
        "saved": "已保存。",
        "review": "回顾",
        "yesterday_review": "昨日回顾",
        "progress_review": "当前进度",
        "no_review": "暂无可回顾内容。",
        "view_ai_rationale": "查看 AI 分析",
        "no_rationale": "暂无 AI 分析记录。",
        "ai_analysis_title": "AI 规划分析",
        "opacity": "透明度",
        "language": "语言",
        "zh": "中文",
        "en": "English",
        "workday_h": "工作日 h",
        "weekend_h": "周末 h",
        "holiday_h": "节假日 h",
        "create_import": "创建 / 导入任务",
        "task_placeholder": "例如：新增任务，两周内完成论文初稿 5000 字。\n也可以只写目标：周末要考英语，请帮我安排复习。\n日常任务：每天背 100 个单词。",
        "choose_file": "选择文件",
        "run_import": "生成 / 导入并重规划",
        "manage_tasks": "管理任务",
        "delete_tasks": "删除所有任务",
        "delete_one": "删除",
        "no_saved_tasks": "当前没有可管理的任务。",
        "task_deleted": "已删除任务并重新规划。",
        "recurring_tag": "每日",
        "close_settings": "关闭设置",
        "close_app": "关闭程序",
        "refresh": "刷新",
        "empty_plan": "还没有当前计划。\n点击右上角“设置”，输入或选择任务文件，\n即可在桌面程序里创建计划。",
        "progress": "进度：{done}/{total}",
        "selected": "已选择：{tier}",
        "daily_quote_title": "今日鸡汤",
        "greeting_title": "今日问候",
        "tier_min": "最低",
        "tier_ideal": "理想",
        "tier_challenge": "挑战",
        "confirm_delete_title": "确认删除",
        "confirm_delete_body": "确定要删除当前计划和今天的任务清单吗？\n历史打卡记录会保留。",
        "file_title": "选择任务文件",
        "file_documents": "任务文档",
        "file_all": "所有文件",
        "need_input": "请输入任务描述，或选择 PDF/Word/TXT/MD 文件。",
        "missing_key": "未检测到 API Key。请先设置 DEEPSEEK_API_KEY 环境变量。",
        "bad_hours": "每日可用时间必须是数字。",
        "parsing_file": "正在解析文件...",
        "analyzing": "AI 正在分析新任务...",
        "created": "创建",
        "imported": "导入",
        "done": "已{action} {count} 个任务并生成计划。",
        "failed": "生成失败：{error}",
        "tray_title": "任务规划智能体",
        "tray_toggle": "显示/隐藏便签",
    },
    "en": {
        "title": "Today's Tasks",
        "settings": "Settings",
        "set_language": "Language",
        "set_nickname": "Nickname",
        "nickname": "Nickname",
        "nickname_placeholder": "User",
        "greeting_morning": "Good morning, {nickname}.",
        "greeting_noon": "Good afternoon, {nickname}.",
        "greeting_evening": "Good evening, {nickname}.",
        "pin_window": "Pin Window",
        "unpin_window": "Unpin Window",
        "set_opacity": "Opacity",
        "adjust_schedule": "Schedule Hours",
        "save": "Save",
        "saved": "Saved.",
        "review": "Review",
        "yesterday_review": "Yesterday",
        "progress_review": "Progress",
        "no_review": "Nothing to review yet.",
        "view_ai_rationale": "View AI Analysis",
        "no_rationale": "No AI analysis record.",
        "ai_analysis_title": "AI Plan Analysis",
        "opacity": "Opacity",
        "language": "Language",
        "zh": "中文",
        "en": "English",
        "workday_h": "Workday h",
        "weekend_h": "Weekend h",
        "holiday_h": "Holiday h",
        "create_import": "Create / Import Tasks",
        "task_placeholder": "Example: New task: finish a 5,000-word paper draft within two weeks.\nYou can also write a goal: I have an English exam this weekend, plan my review.\nDaily routine: memorize 100 words every day.",
        "choose_file": "Choose File",
        "run_import": "Generate / Import and Replan",
        "manage_tasks": "Manage Tasks",
        "delete_tasks": "Delete All Tasks",
        "delete_one": "Delete",
        "no_saved_tasks": "No saved tasks to manage.",
        "task_deleted": "Task deleted and plan regenerated.",
        "recurring_tag": "Daily",
        "close_settings": "Close Settings",
        "close_app": "Exit App",
        "refresh": "Refresh",
        "empty_plan": "No current plan yet.\nOpen Settings, type a task or choose a file,\nand create a plan inside the desktop app.",
        "progress": "Progress: {done}/{total}",
        "selected": "Selected: {tier}",
        "daily_quote_title": "Daily Motivation",
        "greeting_title": "Today's Greeting",
        "tier_min": "Minimum",
        "tier_ideal": "Ideal",
        "tier_challenge": "Challenge",
        "confirm_delete_title": "Confirm Delete",
        "confirm_delete_body": "Delete the current plan and today's task list?\nHistory records will be kept.",
        "file_title": "Choose Task File",
        "file_documents": "Task documents",
        "file_all": "All files",
        "need_input": "Enter a task description, or choose a PDF/Word/TXT/MD file.",
        "missing_key": "No API Key detected. Set the DEEPSEEK_API_KEY environment variable first.",
        "bad_hours": "Daily available hours must be numbers.",
        "parsing_file": "Parsing file...",
        "analyzing": "AI is analyzing the new task...",
        "created": "created",
        "imported": "imported",
        "done": "{action} {count} task(s) and generated the plan.",
        "failed": "Generation failed: {error}",
        "tray_title": "Task Planner Agent",
        "tray_toggle": "Show/Hide Sticky Note",
    },
}


def _connect(db_path: Path) -> sqlite3.Connection:
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


def get_setting(db_path: Path, key: str, default: str = "") -> str:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT value FROM user_settings WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()
    return row["value"] if row else default


def set_setting(db_path: Path, key: str, value: str):
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO user_settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def get_language(db_path: Path) -> str:
    lang = get_setting(db_path, "desktop_language", "zh")
    return lang if lang in DESKTOP_TEXT else "zh"


def set_language(db_path: Path, lang: str):
    if lang in DESKTOP_TEXT:
        set_setting(db_path, "desktop_language", lang)


def get_nickname(db_path: Path) -> str:
    default = DESKTOP_TEXT[get_language(db_path)]["nickname_placeholder"]
    return get_setting(db_path, "desktop_nickname", default).strip() or default


def set_nickname(db_path: Path, nickname: str):
    set_setting(db_path, "desktop_nickname", nickname.strip() or DESKTOP_TEXT[get_language(db_path)]["nickname_placeholder"])


def tr(db_path: Path, key: str, **kwargs) -> str:
    lang = get_language(db_path)
    text = DESKTOP_TEXT[lang].get(key, DESKTOP_TEXT["zh"].get(key, key))
    return text.format(**kwargs) if kwargs else text


def styled_button(parent: tk.Widget, text: str, command, **kwargs) -> tk.Button:
    bg = kwargs.pop("bg", COLORS["button"])
    fg = kwargs.pop("fg", "white")
    activebackground = kwargs.pop("activebackground", COLORS["button_active"])
    activeforeground = kwargs.pop("activeforeground", fg)
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        activebackground=activebackground,
        activeforeground=activeforeground,
        font=("Microsoft YaHei UI", 10, "bold"),
        relief="flat",
        borderwidth=0,
        highlightthickness=0,
        cursor="hand2",
        **kwargs,
    )





def _slot_from_dict(data: dict) -> DailySlot:
    slot_data = dict(data)
    if isinstance(slot_data.get("date"), str):
        slot_data["date"] = date.fromisoformat(slot_data["date"])
    return DailySlot(**slot_data)


def save_plan_snapshot(db_path: Path, tasks: list[Task], slots: dict[date, DailySlot], plan: PlanResult):
    payload = {
        "tasks": [task.to_dict() for task in tasks],
        "slots": {day.isoformat(): slot.to_dict() for day, slot in slots.items()},
        "plan_json": plan.to_dict(),
    }
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO user_settings (key, value) VALUES (?, ?)",
            ("plan_snapshot", json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()


def load_plan_snapshot(db_path: Path) -> tuple[list[Task] | None, dict[date, DailySlot] | None]:
    if not db_path.exists():
        return None, None
    conn = _connect(db_path)
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
    tasks = [Task.from_dict(item) for item in data.get("tasks", [])]
    slots = {
        date.fromisoformat(day): _slot_from_dict(slot)
        for day, slot in data.get("slots", {}).items()
    }
    return tasks, slots


def clear_current_tasks(db_path: Path, current_day: date):
    conn = _connect(db_path)
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


def clear_today_checkin_state(db_path: Path, current_day: date):
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM checkin_state WHERE date = ?", (current_day.isoformat(),))
        conn.commit()
    finally:
        conn.close()


def build_existing_tasks_context(tasks: list[Task] | None) -> str:
    if not tasks:
        return ""
    lines = ["Existing tasks already in the user's plan:"]
    for task in tasks:
        deadline = task.deadline.isoformat() if task.deadline else "none"
        recurrence = task.recurrence or "none"
        lines.append(
            f"- {task.description}; type={task.task_type}; amount={task.total_amount:g} {task.unit}; "
            f"deadline={deadline}; recurrence={recurrence}"
        )
    return "\n".join(lines)


def build_schedule(
    start: date,
    end: date,
    workday_hours: float = 2.0,
    weekend_hours: float = 6.0,
    holiday_hours: float = 4.0,
) -> dict[date, DailySlot]:
    settings = UserSettings(
        workday_hours=workday_hours,
        weekend_hours=weekend_hours,
        holiday_hours=holiday_hours,
    )
    return ScheduleEngine(settings).generate(start, end)


def build_plan(tasks: list[Task], slots: dict[date, DailySlot]) -> PlanResult:
    return PlanningEngine(tasks=tasks, slots=slots, max_tasks_per_day=2, buffer_ratio=0.10).plan()


def apply_soft_deadlines(tasks: list[Task], planning_start: date | None = None) -> list[Task]:
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


def merge_tasks(existing: list[Task], new_tasks: list[Task]) -> list[Task]:
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


def ensure_slots_cover_tasks(
    slots: dict[date, DailySlot],
    tasks: list[Task],
    workday_hours: float = 2.0,
    weekend_hours: float = 6.0,
    holiday_hours: float = 4.0,
) -> dict[date, DailySlot]:
    latest_deadline = max((task.deadline for task in tasks if task.deadline), default=None)
    if latest_deadline is None:
        return slots
    if slots and max(slots.keys()) >= latest_deadline:
        return slots
    start = min(slots.keys(), default=date.today())
    return build_schedule(start, latest_deadline, workday_hours, weekend_hours, holiday_hours)


def get_schedule_hours(db_path: Path) -> tuple[float, float, float]:
    def read_float(key: str, default: float) -> float:
        raw = get_setting(db_path, key, str(default))
        try:
            return max(0.0, float(raw))
        except ValueError:
            return default

    return (
        read_float("desktop_workday_hours", 2.0),
        read_float("desktop_weekend_hours", 6.0),
        read_float("desktop_holiday_hours", 4.0),
    )


def set_schedule_hours(db_path: Path, workday: float, weekend: float, holiday: float):
    set_setting(db_path, "desktop_workday_hours", str(workday))
    set_setting(db_path, "desktop_weekend_hours", str(weekend))
    set_setting(db_path, "desktop_holiday_hours", str(holiday))


class StickyWindow:
    def __init__(self, root: tk.Tk, db_path: Path):
        self.root = root
        self.db_path = db_path
        self.tracker = DailyTracker(str(db_path))
        self.state = None
        self.settings_window: tk.Toplevel | None = None
        self.language_window: tk.Toplevel | None = None
        self.nickname_window: tk.Toplevel | None = None
        self.opacity_window: tk.Toplevel | None = None
        self.create_window: tk.Toplevel | None = None
        self.manage_window: tk.Toplevel | None = None
        self.schedule_window: tk.Toplevel | None = None
        self.review_window: tk.Toplevel | None = None
        self.tray = None
        self.drag_x = 0
        self.drag_y = 0
        self.is_pinned = False
        self.locked_geometry: str | None = None
        self.restoring_geometry = False
        self.pointer_inside = True
        self.task_canvas: tk.Canvas | None = None

        self.root.title(tr(self.db_path, "title"))
        self.root.geometry("360x360+120+120")
        self.root.minsize(300, 240)
        self.root.configure(bg=COLORS["paper"])
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)

        self.root.bind("<Configure>", self._restore_pinned_geometry)
        self.root.bind("<Enter>", self._handle_mouse_enter)
        self.root.bind("<Leave>", self._handle_mouse_leave)
        self.apply_opacity()
        self.refresh()

    def apply_opacity(self):
        opacity_text = get_setting(self.db_path, "sticky_opacity", "95")
        opacity = int(opacity_text) if opacity_text.isdigit() else 95
        if self.is_pinned and not self.pointer_inside:
            opacity = max(20, opacity // 2)
        self.root.attributes("-alpha", max(20, min(100, opacity)) / 100)

    def set_opacity_percent(self, value: int):
        set_setting(self.db_path, "sticky_opacity", str(value))
        self.apply_opacity()

    def _handle_mouse_enter(self, _event=None):
        self.pointer_inside = True
        self.apply_opacity()

    def _handle_mouse_leave(self, _event=None):
        self.root.after(120, self._dim_if_pointer_left)

    def _dim_if_pointer_left(self):
        x = self.root.winfo_pointerx()
        y = self.root.winfo_pointery()
        left = self.root.winfo_rootx()
        top = self.root.winfo_rooty()
        right = left + self.root.winfo_width()
        bottom = top + self.root.winfo_height()
        self.pointer_inside = left <= x <= right and top <= y <= bottom
        self.apply_opacity()

    def get_modal_parent(self) -> tk.Tk | tk.Toplevel:
        if self.settings_window and self.settings_window.winfo_exists():
            return self.settings_window
        return self.root

    def close_modal_window(self, window: tk.Toplevel):
        if window and window.winfo_exists():
            window.destroy()

    def prepare_modal_window(self, window: tk.Toplevel, parent: tk.Tk | tk.Toplevel | None = None):
        modal_parent = parent or self.root
        window.transient(modal_parent)
        parent_disabled = False
        try:
            modal_parent.attributes("-disabled", True)
            parent_disabled = True
        except tk.TclError:
            pass

        released = False

        def release_modal():
            nonlocal released
            if released:
                return
            released = True
            try:
                window.grab_release()
            except tk.TclError:
                pass
            if parent_disabled:
                try:
                    modal_parent.attributes("-disabled", False)
                    modal_parent.lift()
                    modal_parent.focus_force()
                except tk.TclError:
                    pass

        def close_window():
            release_modal()
            window.destroy()

        def on_destroy(event):
            if event.widget is window:
                release_modal()

        window.protocol("WM_DELETE_WINDOW", close_window)
        window.bind("<Destroy>", on_destroy, add="+")
        window.grab_set()
        window.focus_force()

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self):
        self.root.withdraw()

    def close_app(self):
        self.root.quit()
        self.root.destroy()

    def toggle(self):
        if self.root.state() == "withdrawn":
            self.refresh()
            self.show()
        else:
            self.hide()

    def current_greeting(self) -> str:
        hour = datetime.now().hour
        if hour < 11:
            key = "greeting_morning"
        elif hour < 18:
            key = "greeting_noon"
        else:
            key = "greeting_evening"
        return tr(self.db_path, key, nickname=get_nickname(self.db_path))

    def toggle_pin(self):
        if self.is_pinned:
            self.is_pinned = False
            self.locked_geometry = None
            self.root.resizable(True, True)
            self.render()
            return

        self.is_pinned = True
        self.render()
        self.root.update_idletasks()
        self.locked_geometry = self.root.geometry()
        self.root.resizable(False, False)
        self.apply_opacity()

    def refresh(self):
        tasks, slots = load_plan_snapshot(self.db_path)
        if tasks and slots:
            plan = PlanningEngine(tasks=tasks, slots=slots, max_tasks_per_day=2).plan()
            self.state = self.tracker.get_or_create_today(plan=plan, tasks=tasks)
        else:
            self.state = self.tracker.get_or_create_today()
        self.render()

    def delete_current_tasks(self):
        confirmed = messagebox.askyesno(
            tr(self.db_path, "confirm_delete_title"),
            tr(self.db_path, "confirm_delete_body"),
            parent=self.root,
        )
        if confirmed:
            clear_current_tasks(self.db_path, self.tracker.today)
            self.refresh()
            if self.manage_window and self.manage_window.winfo_exists():
                self.manage_window.destroy()
                self.manage_window = None

    def delete_one_task(self, task_id: str):
        tasks, slots = load_plan_snapshot(self.db_path)
        if not tasks:
            return
        remaining = [task for task in tasks if task.id != task_id]
        if not remaining:
            clear_current_tasks(self.db_path, self.tracker.today)
        else:
            workday, weekend, holiday = get_schedule_hours(self.db_path)
            updated_tasks = apply_soft_deadlines(remaining)
            if slots:
                updated_slots = ensure_slots_cover_tasks(slots, updated_tasks, workday, weekend, holiday)
            else:
                latest_deadline = max((task.deadline for task in updated_tasks if task.deadline), default=date.today() + timedelta(days=30))
                updated_slots = build_schedule(date.today(), latest_deadline, workday, weekend, holiday)
            plan = build_plan(updated_tasks, updated_slots)
            save_plan_snapshot(self.db_path, updated_tasks, updated_slots, plan)
            clear_today_checkin_state(self.db_path, self.tracker.today)

        self.refresh()
        self.render_manage_tasks()

    def open_manage_tasks(self):
        if self.manage_window and self.manage_window.winfo_exists():
            self.manage_window.lift()
            self.manage_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        self.manage_window = window
        window.title(tr(self.db_path, "manage_tasks"))
        window.geometry("500x700+560+120")
        window.configure(bg=COLORS["paper"])
        window.attributes("-topmost", True)
        self.prepare_modal_window(window, self.get_modal_parent())
        self.render_manage_tasks()

    def open_create_import_tasks(self):
        if self.create_window and self.create_window.winfo_exists():
            self.create_window.lift()
            self.create_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        self.create_window = window
        window.title(tr(self.db_path, "create_import"))
        window.geometry("500x430+540+150")
        window.configure(bg=COLORS["paper"])
        window.attributes("-topmost", True)
        self.prepare_modal_window(window, self.get_modal_parent())

        tk.Label(
            window,
            text=tr(self.db_path, "create_import"),
            bg=COLORS["paper"],
            fg=COLORS["ink"],
            font=("Microsoft YaHei UI", 16, "bold"),
        ).pack(anchor="w", padx=14, pady=(12, 8))

        task_text = tk.Text(window, height=8, wrap="word")
        task_text.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        task_text.insert("1.0", tr(self.db_path, "task_placeholder"))

        selected_file_var = tk.StringVar(value="")
        file_row = tk.Frame(window, bg=COLORS["paper"])
        file_row.pack(fill="x", padx=14, pady=(0, 8))
        styled_button(
            file_row,
            text=tr(self.db_path, "choose_file"),
            command=lambda: self.choose_task_file(selected_file_var),
        ).pack(side="left")
        tk.Label(
            file_row,
            textvariable=selected_file_var,
            bg=COLORS["paper"],
            fg=COLORS["muted"],
            anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=(8, 0))

        status_var = tk.StringVar(value="")
        tk.Label(
            window,
            textvariable=status_var,
            bg=COLORS["paper"],
            fg=COLORS["muted"],
            wraplength=430,
        ).pack(fill="x", padx=14, pady=(0, 8))

        styled_button(
            window,
            text=tr(self.db_path, "run_import"),
            command=lambda: self.create_or_import_task(
                task_text.get("1.0", "end").strip(),
                selected_file_var.get(),
                status_var,
            ),
        ).pack(fill="x", padx=14, pady=(0, 14))

    def render_manage_tasks(self):
        window = self.manage_window
        if not window or not window.winfo_exists():
            return
        for child in window.winfo_children():
            child.destroy()

        tk.Label(
            window,
            text=tr(self.db_path, "manage_tasks"),
            bg=COLORS["paper"],
            fg=COLORS["ink"],
            font=("Microsoft YaHei UI", 16, "bold"),
        ).pack(anchor="w", padx=14, pady=(12, 8))

        tasks, _slots = load_plan_snapshot(self.db_path)
        if not tasks:
            tk.Label(
                window,
                text=tr(self.db_path, "no_saved_tasks"),
                bg=COLORS["paper"],
                fg=COLORS["muted"],
                font=("Microsoft YaHei UI", 11),
            ).pack(expand=True)
        else:
            list_frame = tk.Frame(window, bg=COLORS["paper"])
            list_frame.pack(fill="both", expand=True, padx=14, pady=(0, 10))
            for task in tasks:
                row = tk.Frame(list_frame, bg=COLORS["card"], highlightbackground=COLORS["paper_dark"], highlightthickness=1)
                row.pack(fill="x", pady=4)
                tag = f" · {tr(self.db_path, 'recurring_tag')}" if task.is_daily_recurring else ""
                deadline = task.deadline.isoformat() if task.deadline else "No DDL"
                text = f"{task.description}\n{task.total_amount:g} {task.unit} · {deadline}{tag}"
                tk.Label(
                    row,
                    text=text,
                    bg=COLORS["card"],
                    fg=COLORS["ink"],
                    anchor="w",
                    justify="left",
                    wraplength=300,
                    font=("Microsoft YaHei UI", 10, "bold"),
                ).pack(side="left", fill="x", expand=True, padx=8, pady=8)
                styled_button(
                    row,
                    text=tr(self.db_path, "delete_one"),
                    command=lambda task_id=task.id: self.delete_one_task(task_id),
                    width=8,
                ).pack(side="right", padx=8, pady=8)

        bottom = tk.Frame(window, bg=COLORS["paper"])
        bottom.pack(fill="x", padx=14, pady=(0, 14))
        styled_button(bottom, text=tr(self.db_path, "delete_tasks"), command=self.delete_current_tasks).pack(fill="x", pady=(0, 8))
        styled_button(bottom, text=tr(self.db_path, "close_settings"), command=lambda: self.close_modal_window(window)).pack(fill="x")

    def open_language_settings(self):
        if self.language_window and self.language_window.winfo_exists():
            self.language_window.lift()
            self.language_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        self.language_window = window
        window.title(tr(self.db_path, "set_language"))
        window.geometry("300x180+560+180")
        window.configure(bg=COLORS["paper"])
        window.attributes("-topmost", True)
        self.prepare_modal_window(window, self.get_modal_parent())

        tk.Label(window, text=tr(self.db_path, "set_language"), bg=COLORS["paper"], fg=COLORS["ink"], font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w", padx=14, pady=(12, 12))
        lang_var = tk.StringVar(value=get_language(self.db_path))

        def change_language():
            set_language(self.db_path, lang_var.get())
            self.refresh()
            if self.tray:
                self.tray.refresh_menu()
            if self.settings_window and self.settings_window.winfo_exists():
                self.settings_window.destroy()
                self.settings_window = None

        for code in ("zh", "en"):
            tk.Radiobutton(
                window,
                text=DESKTOP_TEXT[get_language(self.db_path)][code],
                value=code,
                variable=lang_var,
                command=change_language,
                bg=COLORS["paper"],
                fg=COLORS["ink"],
                activebackground=COLORS["paper"],
                selectcolor=COLORS["card"],
                font=("Microsoft YaHei UI", 11, "bold"),
            ).pack(anchor="w", padx=18, pady=4)

    def open_nickname_settings(self):
        if self.nickname_window and self.nickname_window.winfo_exists():
            self.nickname_window.lift()
            self.nickname_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        self.nickname_window = window
        window.title(tr(self.db_path, "set_nickname"))
        window.geometry("330x190+560+180")
        window.configure(bg=COLORS["paper"])
        window.attributes("-topmost", True)
        self.prepare_modal_window(window, self.get_modal_parent())

        tk.Label(window, text=tr(self.db_path, "set_nickname"), bg=COLORS["paper"], fg=COLORS["ink"], font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w", padx=14, pady=(12, 12))
        nickname_var = tk.StringVar(value=get_nickname(self.db_path))
        tk.Entry(window, textvariable=nickname_var).pack(fill="x", padx=14, pady=(0, 10))
        status_var = tk.StringVar(value="")
        tk.Label(window, textvariable=status_var, bg=COLORS["paper"], fg=COLORS["muted"]).pack(fill="x", padx=14, pady=(0, 8))

        def save_nickname():
            set_nickname(self.db_path, nickname_var.get())
            status_var.set(tr(self.db_path, "saved"))
            self.refresh()

        styled_button(window, text=tr(self.db_path, "save"), command=save_nickname).pack(fill="x", padx=14, pady=(0, 14))

    def open_opacity_settings(self):
        if self.opacity_window and self.opacity_window.winfo_exists():
            self.opacity_window.lift()
            self.opacity_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        self.opacity_window = window
        window.title(tr(self.db_path, "set_opacity"))
        window.geometry("360x180+560+180")
        window.configure(bg=COLORS["paper"])
        window.attributes("-topmost", True)
        self.prepare_modal_window(window, self.get_modal_parent())

        tk.Label(window, text=tr(self.db_path, "set_opacity"), bg=COLORS["paper"], fg=COLORS["ink"], font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w", padx=14, pady=(12, 12))
        opacity_value = int(get_setting(self.db_path, "sticky_opacity", "95"))
        opacity_scale = tk.Scale(
            window,
            from_=40,
            to=100,
            orient="horizontal",
            resolution=5,
            bg=COLORS["paper"],
            highlightthickness=0,
            command=lambda value: self.set_opacity_percent(int(float(value))),
        )
        opacity_scale.set(opacity_value)
        opacity_scale.pack(fill="x", padx=14, pady=(0, 12))

    def open_schedule_settings(self):
        if self.schedule_window and self.schedule_window.winfo_exists():
            self.schedule_window.lift()
            self.schedule_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        self.schedule_window = window
        window.title(tr(self.db_path, "adjust_schedule"))
        window.geometry("380x230+560+180")
        window.configure(bg=COLORS["paper"])
        window.attributes("-topmost", True)
        self.prepare_modal_window(window, self.get_modal_parent())

        tk.Label(window, text=tr(self.db_path, "adjust_schedule"), bg=COLORS["paper"], fg=COLORS["ink"], font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w", padx=14, pady=(12, 12))
        workday_h, weekend_h, holiday_h = get_schedule_hours(self.db_path)
        hours_vars = {
            "workday": tk.StringVar(value=str(workday_h)),
            "weekend": tk.StringVar(value=str(weekend_h)),
            "holiday": tk.StringVar(value=str(holiday_h)),
        }
        hours_frame = tk.Frame(window, bg=COLORS["paper"])
        hours_frame.pack(fill="x", padx=14, pady=(0, 14))
        for label, key in ((tr(self.db_path, "workday_h"), "workday"), (tr(self.db_path, "weekend_h"), "weekend"), (tr(self.db_path, "holiday_h"), "holiday")):
            block = tk.Frame(hours_frame, bg=COLORS["paper"])
            block.pack(side="left", expand=True, fill="x", padx=2)
            tk.Label(block, text=label, bg=COLORS["paper"], fg=COLORS["ink"]).pack(anchor="w")
            tk.Entry(block, textvariable=hours_vars[key], width=8).pack(fill="x")

        status_var = tk.StringVar(value="")
        tk.Label(window, textvariable=status_var, bg=COLORS["paper"], fg=COLORS["muted"]).pack(fill="x", padx=14, pady=(0, 8))

        def save_hours():
            try:
                workday = max(0.0, float(hours_vars["workday"].get()))
                weekend = max(0.0, float(hours_vars["weekend"].get()))
                holiday = max(0.0, float(hours_vars["holiday"].get()))
            except ValueError:
                status_var.set(tr(self.db_path, "bad_hours"))
                return
            set_schedule_hours(self.db_path, workday, weekend, holiday)
            tasks, existing_slots = load_plan_snapshot(self.db_path)
            if tasks:
                latest_deadline = max((task.deadline for task in tasks if task.deadline), default=None)
                existing_end = max(existing_slots.keys(), default=None) if existing_slots else None
                end = latest_deadline or existing_end or (date.today() + timedelta(days=30))
                if end < date.today():
                    end = date.today() + timedelta(days=30)
                slots = build_schedule(date.today(), end, workday, weekend, holiday)
                plan = build_plan(tasks, slots)
                save_plan_snapshot(self.db_path, tasks, slots, plan)
                clear_today_checkin_state(self.db_path, self.tracker.today)
                self.refresh()
            status_var.set(tr(self.db_path, "saved"))

        styled_button(window, text=tr(self.db_path, "save"), command=save_hours).pack(fill="x", padx=14, pady=(0, 14))

    def open_review(self):
        if self.review_window and self.review_window.winfo_exists():
            self.review_window.lift()
            self.review_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        self.review_window = window
        window.title(tr(self.db_path, "review"))
        window.geometry("420x410+520+180")
        window.configure(bg=COLORS["paper"])
        window.attributes("-topmost", True)
        self.prepare_modal_window(window, self.get_modal_parent())

        tk.Label(window, text=tr(self.db_path, "review"), bg=COLORS["paper"], fg=COLORS["ink"], font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w", padx=14, pady=(12, 8))
        lang = get_language(self.db_path)
        yesterday = self.tracker.get_yesterday_summary(lang)
        tasks, _slots = load_plan_snapshot(self.db_path)
        progress = self.tracker.get_progress_summary(tasks or [], lang) if tasks else ""
        content = []
        if yesterday:
            content.append(f"{tr(self.db_path, 'yesterday_review')}\n{yesterday}")
        if progress:
            content.append(f"{tr(self.db_path, 'progress_review')}\n{progress}")
        text = "\n\n".join(content) if content else tr(self.db_path, "no_review")
        tk.Label(
            window,
            text=text,
            bg=COLORS["paper"],
            fg=COLORS["ink"],
            justify="left",
            anchor="nw",
            wraplength=380,
            font=("Microsoft YaHei UI", 10),
        ).pack(fill="both", expand=True, padx=14, pady=(0, 8))

        # ── "View AI Analysis" button ────────────────────────────
        def show_rationale():
            rationale = self._load_rationale()
            if rationale:
                self._show_rationale(rationale, parent=window)
            else:
                messagebox.showinfo(
                    tr(self.db_path, "ai_analysis_title"),
                    tr(self.db_path, "no_rationale"),
                    parent=window,
                )

        styled_button(
            window,
            text=tr(self.db_path, "view_ai_rationale"),
            command=show_rationale,
        ).pack(fill="x", padx=14, pady=(0, 10))

    def open_settings(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            self.settings_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        self.settings_window = window
        window.title(tr(self.db_path, "settings"))
        window.geometry("360x360+520+140")
        window.configure(bg=COLORS["paper"])
        window.attributes("-topmost", True)
        self.prepare_modal_window(window, self.root)

        title = tk.Label(
            window,
            text=tr(self.db_path, "settings"),
            bg=COLORS["paper"],
            fg=COLORS["ink"],
            font=("Microsoft YaHei UI", 16, "bold"),
        )
        title.pack(anchor="w", padx=14, pady=(12, 12))

        buttons = [
            (tr(self.db_path, "set_language"), self.open_language_settings),
            (tr(self.db_path, "set_nickname"), self.open_nickname_settings),
            (tr(self.db_path, "set_opacity"), self.open_opacity_settings),
            (tr(self.db_path, "create_import"), self.open_create_import_tasks),
            (tr(self.db_path, "manage_tasks"), self.open_manage_tasks),
            (tr(self.db_path, "adjust_schedule"), self.open_schedule_settings),
        ]
        for label, command in buttons:
            styled_button(window, text=label, command=command).pack(fill="x", padx=14, pady=(0, 10))

    def choose_task_file(self, selected_file_var: tk.StringVar):
        file_path = filedialog.askopenfilename(
            parent=self.root,
            title=tr(self.db_path, "file_title"),
            filetypes=(
                (tr(self.db_path, "file_documents"), "*.pdf *.docx *.txt *.md"),
                ("PDF", "*.pdf"),
                ("Word", "*.docx"),
                ("Text", "*.txt *.md"),
                (tr(self.db_path, "file_all"), "*.*"),
            ),
        )
        if file_path:
            selected_file_var.set(file_path)

    def create_or_import_task(
        self,
        raw_text: str,
        file_path: str,
        status_var: tk.StringVar,
    ):
        if not raw_text and not file_path:
            status_var.set(tr(self.db_path, "need_input"))
            return
        api_key = os.environ.get("DEEPSEEK_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            status_var.set(tr(self.db_path, "missing_key"))
            return

        workday, weekend, holiday = get_schedule_hours(self.db_path)
        lang = get_language(self.db_path)

        try:
            if file_path:
                status_var.set(tr(self.db_path, "parsing_file"))
                self.root.update_idletasks()
                doc = parse_document(file_path)
                analyze_input = f"{doc.raw_text}\n\n{raw_text}" if raw_text else doc.raw_text
            else:
                analyze_input = raw_text

            existing_tasks, existing_slots = load_plan_snapshot(self.db_path)
            existing_context = build_existing_tasks_context(existing_tasks)

            status_var.set(tr(self.db_path, "analyzing"))
            self.root.update_idletasks()
            provider = "deepseek" if os.environ.get("DEEPSEEK_API_KEY") else "openai"

            # ── Detect goal vs. quantified task ────────────────────
            is_goal = self._is_goal_input(analyze_input)

            if is_goal:
                full_input = analyze_input
                if existing_context:
                    full_input = f"{existing_context}\n\nUser's new goal:\n{analyze_input}"
                result = decompose_goal(full_input, api_key=api_key, provider=provider, language=lang)
                new_tasks = result.get("tasks", [])
                goal_rationale = result.get("rationale", "")
            else:
                full_input = analyze_input
                if existing_context:
                    full_input = f"{existing_context}\n\nUser's new request to turn into schedulable tasks:\n{analyze_input}"
                analyzer = TaskAnalyzer(api_key=api_key, provider=provider)
                analysis = analyzer.analyze(full_input, language=lang)
                new_tasks = analysis.tasks
                goal_rationale = ""

            if not new_tasks:
                status_var.set(tr(self.db_path, "failed", error="No tasks extracted"))
                return

            if existing_tasks and existing_slots:
                merged = apply_soft_deadlines(merge_tasks(existing_tasks, new_tasks))
                slots = ensure_slots_cover_tasks(existing_slots, merged, workday, weekend, holiday)
                action = tr(self.db_path, "imported")
            else:
                merged = apply_soft_deadlines(new_tasks)
                latest_deadline = max((task.deadline for task in merged if task.deadline), default=date.today() + timedelta(days=30))
                slots = build_schedule(date.today(), latest_deadline, workday, weekend, holiday)
                action = tr(self.db_path, "created")

            plan = build_plan(merged, slots)

            # ── Generate plan rationale via LLM ────────────────────
            schedule_text = self._summarize_plan(plan)
            try:
                plan.rationale = generate_plan_rationale(
                    tasks=merged,
                    schedule_summary=schedule_text,
                    warnings=plan.warnings,
                    api_key=api_key,
                    provider=provider,
                    language=lang,
                )
            except Exception:
                plan.rationale = goal_rationale or ""

            save_plan_snapshot(self.db_path, merged, slots, plan)
            set_schedule_hours(self.db_path, workday, weekend, holiday)
            clear_today_checkin_state(self.db_path, self.tracker.today)
            status_var.set(tr(self.db_path, "done", action=action, count=len(new_tasks)))
            self.refresh()
            self.render_manage_tasks()

            # ── Show rationale popup ───────────────────────────────
            if plan.rationale:
                self._show_rationale(plan.rationale)
        except Exception as exc:
            status_var.set(tr(self.db_path, "failed", error=exc))

    @staticmethod
    def _is_goal_input(text: str) -> bool:
        """Heuristic: detect if input is a vague goal vs a quantified task or short chore."""
        import re
        goal_keywords = [
            "入门", "学会", "掌握", "做一个", "开发", "手搓", "搭建",
            "学习", "准备", "备考", "复习", "通过",
            "learn", "build", "create", "master", "study", "prepare",
            "develop", "make a", "get started",
        ]
        has_quantity = bool(re.search(
            r'\d+\s*(个|篇|页|道|题|m|米|公里|km|words|pages|problems|hours|h\b)',
            text.lower()
        ))
        # Very short inputs (<=8 words) with no goal keywords are chores / simple tasks
        has_goal_word = any(kw in text.lower() for kw in goal_keywords)
        return has_goal_word and not has_quantity

    @staticmethod
    def _summarize_plan(plan: PlanResult) -> str:
        """Build a text summary of the daily plan for rationale generation."""
        lines = []
        for day in plan.days:
            if not day.allocations:
                continue
            tasks_str = "; ".join(
                f"{a.description} ({a.hours:.1f}h)" for a in day.allocations
            )
            lines.append(f"{day.date} ({day.day_of_week}): {tasks_str}")
        if not lines:
            return "No allocations in the plan."
        return "\n".join(lines[:14])  # Limit to avoid token overflow

    def _show_rationale(self, text: str, parent: tk.Toplevel | None = None):
        """Display the planning rationale in a popup window."""
        window = tk.Toplevel(self.root)
        window.title("AI Plan Explanation")
        window.geometry("480x400+560+200")
        window.configure(bg=COLORS["paper"])
        window.attributes("-topmost", True)
        self.prepare_modal_window(window, parent or self.get_modal_parent())

        tk.Label(
            window,
            text="Plan Reasoning",
            bg=COLORS["paper"],
            fg=COLORS["ink"],
            font=("Microsoft YaHei UI", 16, "bold"),
        ).pack(anchor="w", padx=14, pady=(12, 8))

        frame = tk.Frame(window, bg=COLORS["paper"])
        frame.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        text_widget = tk.Text(
            frame,
            wrap="word",
            bg=COLORS["card"],
            fg=COLORS["ink"],
            font=("Microsoft YaHei UI", 10),
            relief="flat",
            borderwidth=0,
        )
        text_widget.insert("1.0", text)
        text_widget.configure(state="disabled")
        text_widget.pack(fill="both", expand=True)

        styled_button(
            window,
            text="OK",
            command=lambda: self.close_modal_window(window),
        ).pack(fill="x", padx=14, pady=(0, 14))

    def _load_rationale(self) -> str:
        """Load the plan rationale from the saved plan snapshot."""
        if not self.db_path.exists():
            return ""
        conn = _connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT value FROM user_settings WHERE key = ?",
                ("plan_snapshot",),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return ""
        try:
            data = json.loads(row["value"])
            plan_json = data.get("plan_json", {})
            return plan_json.get("rationale", "")
        except (json.JSONDecodeError, KeyError):
            return ""

    def render(self):
        self.root.title(tr(self.db_path, "title"))
        for child in self.root.winfo_children():
            child.destroy()

        header = tk.Frame(self.root, bg=COLORS["paper"])
        header.pack(fill="x", padx=12, pady=(10, 4))
        # ── Drag window by header (title-bar style) ───────────────
        header.bind("<ButtonPress-1>", self._start_drag)
        header.bind("<B1-Motion>", self._drag)

        greeting_label = tk.Label(
            header,
            text=self.current_greeting(),
            bg=COLORS["paper"],
            fg=COLORS["ink"],
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        greeting_label.pack(side="left")
        greeting_label.bind("<ButtonPress-1>", self._start_drag)
        greeting_label.bind("<B1-Motion>", self._drag)

        date_label = tk.Label(
            header,
            text=self.state.date.isoformat() if self.state else "",
            bg=COLORS["paper"],
            fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        date_label.pack(side="left", padx=(8, 0))
        date_label.bind("<ButtonPress-1>", self._start_drag)
        date_label.bind("<B1-Motion>", self._drag)

        pin_char = "📌" if self.is_pinned else "📍"
        pin_btn = tk.Button(
            header,
            text=pin_char,
            command=self.toggle_pin,
            bg=COLORS["paper"],
            activebackground=COLORS["card"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            cursor="hand2",
            font=("Segoe UI Emoji", 12),
        )
        pin_btn.pack(side="right", padx=(0, 4))
        pin_btn.bind("<Enter>", lambda _event: self._handle_mouse_enter())

        settings_btn = styled_button(header, text=tr(self.db_path, "settings"), width=8, command=self.open_settings)
        settings_btn.pack(side="right")

        quote_frame = tk.Frame(self.root, bg=COLORS["card"], highlightbackground=COLORS["paper_dark"], highlightthickness=1)
        quote_frame.pack(fill="x", padx=12, pady=(4, 6))
        tk.Label(
            quote_frame,
            text=self.tracker.get_daily_motivation(get_language(self.db_path)),
            bg=COLORS["card"],
            fg=COLORS["ink"],
            anchor="w",
            justify="left",
            wraplength=320,
            font=("Microsoft YaHei UI", 10),
        ).pack(fill="x", padx=8, pady=6)

        body = tk.Frame(self.root, bg=COLORS["paper"])
        body.pack(fill="x", padx=12, pady=6)
        self.task_canvas = None

        if not self.state or not self.state.tasks:
            empty = tk.Label(
                body,
                text=tr(self.db_path, "empty_plan"),
                bg=COLORS["paper"],
                fg=COLORS["muted"],
                justify="center",
                font=("Microsoft YaHei UI", 11),
            )
            empty.pack(expand=True)
        else:
            canvas = tk.Canvas(body, bg=COLORS["paper"], highlightthickness=0, borderwidth=0)
            scrollbar = tk.Scrollbar(body, orient="vertical", command=canvas.yview)
            scroll_frame = tk.Frame(canvas, bg=COLORS["paper"])
            window_id = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.pack(side="left", fill="x", expand=True)
            self.task_canvas = canvas

            def update_scroll_region(_event=None):
                canvas.configure(scrollregion=canvas.bbox("all"))
                canvas.itemconfigure(window_id, width=canvas.winfo_width())

            canvas.bind("<Configure>", update_scroll_region)
            scroll_frame.bind("<Configure>", update_scroll_region)
            canvas.bind("<MouseWheel>", self._on_task_scroll)
            scroll_frame.bind("<MouseWheel>", self._on_task_scroll)

            for item in self.state.tasks:
                self._render_task_card(scroll_frame, item)

            self.root.update_idletasks()
            # ── Fixed height: show 2 cards, scroll if more ─────────
            card_count = len(self.state.tasks)
            fixed_card_height = 110
            body_height = min(card_count, 2) * fixed_card_height + 8
            canvas.configure(height=body_height)
            if card_count > 2:
                scrollbar.pack(side="right", fill="y")
            else:
                scrollbar.pack_forget()

            done = sum(1 for item in self.state.tasks if item.selected_tier)
            footer = tk.Label(
                self.root,
                text=tr(self.db_path, "progress", done=done, total=len(self.state.tasks)),
                bg=COLORS["paper"],
                fg=COLORS["muted"],
            )
            footer.pack(fill="x", padx=12, pady=(0, 4))

        bottom = tk.Frame(self.root, bg=COLORS["paper"])
        bottom.pack(fill="x", padx=12, pady=(0, 10))
        review = styled_button(bottom, text=tr(self.db_path, "review"), command=self.open_review)
        review.pack(side="left", fill="x", expand=True, padx=(0, 4))
        refresh = styled_button(bottom, text=tr(self.db_path, "refresh"), command=self.refresh)
        refresh.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.adjust_window_height()

    def _on_task_scroll(self, event):
        if self.task_canvas:
            self.task_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def adjust_window_height(self):
        self.root.update_idletasks()
        if self.is_pinned and self.locked_geometry:
            self.root.geometry(self.locked_geometry)
            return
        requested = self.root.winfo_reqheight() + 8
        screen_limit = max(260, min(1040, self.root.winfo_screenheight() - 80))
        height = min(max(260, requested), screen_limit)
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.root.geometry(f"360x{height}+{x}+{y}")

    def _render_task_card(self, parent: tk.Widget, item):
        card = tk.Frame(parent, bg=COLORS["card"], highlightbackground=COLORS["paper_dark"], highlightthickness=1)
        card.pack(fill="x", pady=5)

        desc = tk.Label(
            card,
            text=item.description,
            bg=COLORS["card"],
            fg=COLORS["ink"],
            anchor="w",
            justify="left",
            wraplength=300,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        desc.pack(fill="x", padx=8, pady=(8, 4))

        if item.selected_tier:
            labels = {
                "min": tr(self.db_path, "tier_min"),
                "ideal": tr(self.db_path, "tier_ideal"),
                "challenge": tr(self.db_path, "tier_challenge"),
            }
            selected = tk.Label(
                card,
                text=tr(self.db_path, "selected", tier=labels.get(item.selected_tier, item.selected_tier)),
                bg=COLORS["card"],
                fg=COLORS["green"],
                anchor="w",
                font=("Microsoft YaHei UI", 10, "bold"),
            )
            selected.pack(fill="x", padx=8, pady=(0, 8))
            return

        row = tk.Frame(card, bg=COLORS["card"])
        row.pack(fill="x", padx=8, pady=(0, 8))
        options = [
            ("min", tr(self.db_path, "tier_min"), item.tier_min, item.tier_min_hours, COLORS["tier_min"]),
            ("ideal", tr(self.db_path, "tier_ideal"), item.tier_ideal, item.tier_ideal_hours, COLORS["tier_ideal"]),
            ("challenge", tr(self.db_path, "tier_challenge"), item.tier_challenge, item.tier_challenge_hours, COLORS["tier_challenge"]),
        ]
        for tier, label, amount, hours, text_color in options:
            button = styled_button(
                row,
                text=f"{label}\n{amount:.0f}{item.unit}\n{hours:.1f}h",
                command=lambda task_id=item.task_id, selected=tier: self.select_tier(task_id, selected),
                fg=text_color,
                activeforeground=text_color,
            )
            button.pack(side="left", expand=True, fill="x", padx=2)

    def select_tier(self, task_id: str, tier: str):
        if self.state:
            self.tracker.select_tier(self.state, task_id, tier)
            self.refresh()

    def _start_drag(self, event):
        if self.is_pinned:
            return
        # Drag only from header area — buttons/settings already excluded
        self.drag_x = event.x
        self.drag_y = event.y

    def _drag(self, event):
        if self.is_pinned:
            return
        x = self.root.winfo_pointerx() - self.drag_x
        y = self.root.winfo_pointery() - self.drag_y
        self.root.geometry(f"+{x}+{y}")

    def _restore_pinned_geometry(self, event):
        if event.widget is not self.root or not self.is_pinned or not self.locked_geometry:
            return
        if self.restoring_geometry:
            return
        current_geometry = self.root.geometry()
        if current_geometry == self.locked_geometry:
            return
        self.restoring_geometry = True
        self.root.after_idle(self._finish_restore_pinned_geometry)

    def _finish_restore_pinned_geometry(self):
        if self.is_pinned and self.locked_geometry:
            self.root.geometry(self.locked_geometry)
        self.restoring_geometry = False


def make_tray_image() -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((10, 8, 54, 56), radius=8, fill=(255, 246, 191), outline=(120, 105, 35), width=3)
    draw.line((20, 24, 44, 24), fill=(40, 40, 40), width=3)
    draw.line((20, 34, 44, 34), fill=(40, 40, 40), width=3)
    draw.line((20, 44, 36, 44), fill=(40, 40, 40), width=3)
    return image


class TrayController:
    def __init__(self, sticky: StickyWindow):
        self.sticky = sticky
        self.sticky.tray = self
        self.icon = pystray.Icon(
            "task_planner_agent",
            make_tray_image(),
            tr(self.sticky.db_path, "tray_title"),
            self._menu(),
        )

    def _menu(self):
        return pystray.Menu(
            pystray.MenuItem(tr(self.sticky.db_path, "tray_toggle"), self._toggle),
            pystray.MenuItem(tr(self.sticky.db_path, "refresh"), self._refresh),
            pystray.MenuItem(tr(self.sticky.db_path, "settings"), self._open_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(tr(self.sticky.db_path, "close_app"), self._quit),
        )

    def refresh_menu(self):
        self.icon.title = tr(self.sticky.db_path, "tray_title")
        self.icon.menu = self._menu()
        self.icon.update_menu()

    def run(self):
        thread = threading.Thread(target=self.icon.run, daemon=True)
        thread.start()

    def _call_ui(self, func):
        self.sticky.root.after(0, func)

    def _toggle(self, _icon=None, _item=None):
        self._call_ui(self.sticky.toggle)

    def _refresh(self, _icon=None, _item=None):
        self._call_ui(self.sticky.refresh)

    def _open_settings(self, _icon=None, _item=None):
        self._call_ui(self.sticky.open_settings)

    def _quit(self, _icon=None, _item=None):
        self.icon.stop()
        self._call_ui(self.sticky.close_app)


def main():
    root = tk.Tk()
    sticky = StickyWindow(root, DEFAULT_DB)
    tray = TrayController(sticky)
    tray.run()
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
