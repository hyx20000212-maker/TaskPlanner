"""SQLite persistence for the daily tracker."""

import json
import sqlite3
from datetime import date, datetime
from typing import Optional

from daily_tracker.models import CheckinState, TaskCheckItem, DayRecord


class TrackerStorage:
    """SQLite-backed storage for check-in states and day records.

    All methods use explicit try/finally to ensure connections are closed.
    """

    def __init__(self, db_path: str = "tracker.db"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS checkin_state (
                    date TEXT PRIMARY KEY,
                    phase1_done INTEGER DEFAULT 0,
                    phase2_done INTEGER DEFAULT 0,
                    greeting_shown INTEGER DEFAULT 0,
                    tasks_json TEXT DEFAULT '[]',
                    phase1_time TEXT,
                    phase2_time TEXT
                );
                CREATE TABLE IF NOT EXISTS day_record (
                    date TEXT PRIMARY KEY,
                    tasks_completed_json TEXT DEFAULT '[]',
                    total_hours REAL DEFAULT 0.0,
                    settled INTEGER DEFAULT 0,
                    settled_at TEXT
                );
                CREATE TABLE IF NOT EXISTS user_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                CREATE TABLE IF NOT EXISTS quote_index (
                    category TEXT PRIMARY KEY,
                    idx INTEGER DEFAULT 0
                );
            """)
            conn.commit()
        finally:
            conn.close()

    # ── CheckinState ────────────────────────────────────────────────

    def get_checkin_state(self, d: date) -> Optional[CheckinState]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM checkin_state WHERE date = ?", (d.isoformat(),)
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        tasks_data = json.loads(row["tasks_json"])
        tasks = [TaskCheckItem(**t) for t in tasks_data]
        return CheckinState(
            date=date.fromisoformat(row["date"]),
            phase1_done=bool(row["phase1_done"]),
            phase2_done=bool(row["phase2_done"]),
            greeting_shown=bool(row["greeting_shown"]),
            tasks=tasks,
            phase1_time=datetime.fromisoformat(row["phase1_time"]) if row["phase1_time"] else None,
            phase2_time=datetime.fromisoformat(row["phase2_time"]) if row["phase2_time"] else None,
        )

    def save_checkin_state(self, state: CheckinState):
        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO checkin_state
                (date, phase1_done, phase2_done, greeting_shown, tasks_json, phase1_time, phase2_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                state.date.isoformat(),
                int(state.phase1_done),
                int(state.phase2_done),
                int(state.greeting_shown),
                json.dumps([t.to_dict() for t in state.tasks], ensure_ascii=False),
                state.phase1_time.isoformat() if state.phase1_time else None,
                state.phase2_time.isoformat() if state.phase2_time else None,
            ))
            conn.commit()
        finally:
            conn.close()

    # ── DayRecord ───────────────────────────────────────────────────

    def get_day_record(self, d: date) -> Optional[DayRecord]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM day_record WHERE date = ?", (d.isoformat(),)
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return DayRecord(
            date=date.fromisoformat(row["date"]),
            tasks_completed=json.loads(row["tasks_completed_json"]),
            total_hours_completed=row["total_hours"],
            settled=bool(row["settled"]),
            settled_at=datetime.fromisoformat(row["settled_at"]) if row["settled_at"] else None,
        )

    def save_day_record(self, record: DayRecord):
        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO day_record
                (date, tasks_completed_json, total_hours, settled, settled_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                record.date.isoformat(),
                json.dumps(record.tasks_completed, ensure_ascii=False),
                record.total_hours_completed,
                int(record.settled),
                record.settled_at.isoformat() if record.settled_at else None,
            ))
            conn.commit()
        finally:
            conn.close()

    def get_recent_record(self, days_back: int = 7) -> list[DayRecord]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM day_record ORDER BY date DESC LIMIT ?",
                (days_back,)
            ).fetchall()
        finally:
            conn.close()
        results = []
        for row in rows:
            results.append(DayRecord(
                date=date.fromisoformat(row["date"]),
                tasks_completed=json.loads(row["tasks_completed_json"]),
                total_hours_completed=row["total_hours"],
                settled=bool(row["settled"]),
                settled_at=datetime.fromisoformat(row["settled_at"]) if row["settled_at"] else None,
            ))
        return results

    # ── User Settings ───────────────────────────────────────────────

    def get_setting(self, key: str, default: str = "") -> str:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT value FROM user_settings WHERE key = ?", (key,)
            ).fetchone()
        finally:
            conn.close()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO user_settings (key, value) VALUES (?, ?)",
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()

    @property
    def settlement_hour(self) -> int:
        val = self.get_setting("settlement_hour", "0")
        return int(val) if val.isdigit() else 0

    @settlement_hour.setter
    def settlement_hour(self, hour: int):
        self.set_setting("settlement_hour", str(max(0, min(23, hour))))

    # ── Quote index ─────────────────────────────────────────────────

    def get_quote_index(self, category: str) -> int:
        val = self.get_setting(f"quote_{category}", "0")
        return int(val) if val.lstrip("-").isdigit() else 0

    def set_quote_index(self, category: str, idx: int):
        self.set_setting(f"quote_{category}", str(idx))

    def get_last_settlement_date(self) -> Optional[date]:
        val = self.get_setting("last_settlement", "")
        return date.fromisoformat(val) if val else None

    def set_last_settlement_date(self, d: date):
        self.set_setting("last_settlement", d.isoformat())

    def close(self):
        """Force close all connections (useful for testing)."""
        pass  # Connections are managed per-call via _get_conn with context manager
