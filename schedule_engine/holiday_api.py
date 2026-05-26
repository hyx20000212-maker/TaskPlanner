"""
Chinese Holiday API — Fetches statutory holiday data from timor.tech.

Source: https://timor.tech/api/holiday
Free, no API key required.

Data format per date:
{
    "holiday": true,        // true = rest day (holiday or makeup rest)
    "name": "春节",         // holiday name (if holiday=true)
    "wage": 3,              // overtime wage multiplier
    "date": "2026-02-17"
}
"""

import json
from datetime import date, timedelta
from typing import Optional

import requests

# ── Cache: in-memory dict to avoid repeated API calls ───────────────
_holiday_cache: dict[int, dict[str, dict]] = {}


def _fetch_year(year: int) -> dict[str, dict]:
    """Fetch holiday data for a full year from timor.tech, with caching."""
    if year in _holiday_cache:
        return _holiday_cache[year]

    url = f"https://timor.tech/api/holiday/year/{year}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        # API unavailable → return empty (treat all as normal days)
        data = {"holiday": {}}

    holidays = data.get("holiday", {})
    _holiday_cache[year] = holidays
    return holidays


def get_holiday_info(d: date) -> Optional[dict]:
    """
    Get holiday info for a specific date.

    Returns:
        dict with keys: holiday (bool), name (str), wage (int), date (str)
        None if no holiday data and it's a normal day.
    """
    year_data = _fetch_year(d.year)
    key = d.isoformat()
    info = year_data.get(key)
    return info


def is_holiday(d: date) -> bool:
    """Check if a date is a statutory holiday or makeup rest day."""
    info = get_holiday_info(d)
    if info is None:
        return False
    return bool(info.get("holiday", False))


def is_rest_day(d: date) -> bool:
    """
    Determine if a day is a rest day (non-work day).
    True when: statutory holiday OR weekend (Sat/Sun) AND not a makeup workday.
    """
    info = get_holiday_info(d)

    # Statutory holiday or makeup rest → definitely rest
    if info and info.get("holiday"):
        return True

    # Normal weekend (Sat=5, Sun=6)
    if d.weekday() >= 5:
        # Check if it's a makeup workday (holiday=false means it's a work makeup day)
        # timor.tech marks makeup workdays with holiday=false
        if info is not None and not info.get("holiday"):
            return False  # Makeup workday → NOT a rest day
        return True  # Normal weekend → rest

    # Weekday → work day unless marked as holiday
    return False


def is_workday(d: date) -> bool:
    """Determine if a day is a work day (not a rest day)."""
    return not is_rest_day(d)


def get_holiday_name(d: date) -> str:
    """Get the holiday name if applicable, empty string otherwise."""
    info = get_holiday_info(d)
    if info and info.get("holiday") and info.get("name"):
        return info["name"]
    return ""


def warmup_cache(start: date, end: date):
    """Pre-fetch holiday data for all years in the given range."""
    for year in range(start.year, end.year + 1):
        _fetch_year(year)
