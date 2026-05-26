"""
Task Analyzer Module — Unit Tests (offline, no API key required).

Tests:
  1. Task model serialization (to_dict / from_dict)
  2. Task computed properties (days_until_deadline, min_daily_amount)
  3. TaskAnalysisResult aggregation
  4. Prompt building (system + user)
  5. LLMClient config resolution
  6. TaskAnalyzer error handling (empty text, missing key)
"""

import os
import json
from datetime import date, timedelta

# ── Test 1: Task model serialization ────────────────────────────────
def test_task_serialization():
    """Task.to_dict() and Task.from_dict() round-trip."""
    from task_analyzer.models import Task

    print("=" * 50)
    print("Test 1: Task model serialization")

    task = Task(
        id="task_001",
        description="Memorize 500 English words",
        task_type="memorize",
        total_amount=500,
        unit="words",
        difficulty=3,
        estimated_hours=25.0,
        unit_efficiency=20.0,
        efficiency_unit="words_per_hour",
        deadline=date(2026, 5, 26),
        suggested_daily_hours=3.5,
        confidence=0.8,
        notes="Use spaced repetition",
    )

    d = task.to_dict()
    assert d["task_type"] == "memorize"
    assert d["deadline"] == "2026-05-26"
    assert d["total_amount"] == 500

    task2 = Task.from_dict(d)
    assert task2.id == task.id
    assert task2.deadline == task.deadline
    assert task2.confidence == 0.8

    swapped = Task.from_dict({
        "id": "task_bad_efficiency",
        "description": "Read textbook pages",
        "task_type": "reading",
        "total_amount": "120 pages",
        "unit": "pages",
        "difficulty": "3",
        "estimated_hours": "4h",
        "unit_efficiency": "pages_per_hour",
        "efficiency_unit": "30",
    })
    assert swapped.unit_efficiency == 30.0
    assert swapped.efficiency_unit == "pages_per_hour"
    assert swapped.total_amount == 120.0

    print("  PASS — round-trip serialization OK")


# ── Test 2: Task computed properties ────────────────────────────────
def test_task_properties():
    """Task.days_until_deadline and Task.min_daily_amount."""
    from task_analyzer.models import Task

    print("=" * 50)
    print("Test 2: Task computed properties")

    tomorrow = date.today() + timedelta(days=1)
    in_7_days = date.today() + timedelta(days=7)

    # Task due tomorrow — 1 day remaining
    t1 = Task(id="t1", description="Test", task_type="other",
              total_amount=10, unit="items", difficulty=1,
              estimated_hours=1, unit_efficiency=10, efficiency_unit="items_per_hour",
              deadline=tomorrow)
    assert t1.days_until_deadline == 1
    assert t1.min_daily_amount == 10.0

    # Task due in 7 days
    t2 = Task(id="t2", description="Test", task_type="other",
              total_amount=70, unit="items", difficulty=1,
              estimated_hours=7, unit_efficiency=10, efficiency_unit="items_per_hour",
              deadline=in_7_days)
    assert t2.days_until_deadline == 7
    assert t2.min_daily_amount == 10.0

    # No deadline
    t3 = Task(id="t3", description="Test", task_type="other",
              total_amount=100, unit="items", difficulty=1,
              estimated_hours=10, unit_efficiency=10, efficiency_unit="items_per_hour")
    assert t3.days_until_deadline is None
    assert t3.min_daily_amount is None

    print("  PASS — computed properties OK")


# ── Test 3: TaskAnalysisResult aggregation ──────────────────────────
def test_analysis_result():
    """TaskAnalysisResult aggregates tasks correctly."""
    from task_analyzer.models import Task, TaskAnalysisResult

    print("=" * 50)
    print("Test 3: TaskAnalysisResult aggregation")

    tasks = [
        Task(id="t1", description="A", task_type="memorize",
             total_amount=100, unit="words", difficulty=2,
             estimated_hours=5, unit_efficiency=20, efficiency_unit="words_per_hour"),
        Task(id="t2", description="B", task_type="exercise",
             total_amount=20, unit="problems", difficulty=3,
             estimated_hours=6, unit_efficiency=3.3, efficiency_unit="problems_per_hour"),
    ]
    result = TaskAnalysisResult(
        tasks=tasks,
        warnings=["No deadline specified"],
        raw_response='{"tasks":[]}',
        model_used="deepseek-chat",
        tokens_used=500,
    )

    assert result.task_count == 2
    assert result.total_hours == 11.0
    assert len(result.warnings) == 1

    d = result.to_dict()
    assert len(d["tasks"]) == 2
    assert d["model_used"] == "deepseek-chat"

    print("  PASS — aggregation OK")


# ── Test 4: Prompt building ─────────────────────────────────────────
def test_prompt_building():
    """System and user prompts are built with correct date injection."""
    from task_analyzer.prompts import build_system_prompt, build_user_prompt

    print("=" * 50)
    print("Test 4: Prompt building")

    today = "2026-05-20"
    sys_prompt = build_system_prompt(today)
    assert today in sys_prompt
    assert "Task Type" in sys_prompt or "task_type" in sys_prompt
    assert "JSON" in sys_prompt or "json" in sys_prompt.lower()

    user_prompt = build_user_prompt("Memorize 500 words in 7 days.")
    assert "Memorize 500 words" in user_prompt

    multi_prompt = build_user_prompt("Task A. Task B.", expect_multi=True)
    assert "multiple distinct tasks" in multi_prompt.lower()

    print("  PASS — prompt building OK")


# ── Test 5: LLMClient config resolution ─────────────────────────────
def test_llm_client_config():
    """LLMClient resolves API keys and provider configs."""
    from task_analyzer.llm_client import LLMClient, PROVIDERS

    print("=" * 50)
    print("Test 5: LLMClient config resolution")

    # Provider configs exist
    assert "deepseek" in PROVIDERS
    assert "openai" in PROVIDERS
    assert PROVIDERS["deepseek"].default_model == "deepseek-chat"

    # Missing API key raises ValueError
    try:
        # Temporarily unset any env key
        old_key = os.environ.pop("DEEPSEEK_API_KEY", None)
        old_openai = os.environ.pop("OPENAI_API_KEY", None)
        try:
            LLMClient(api_key=None, provider="deepseek")
            print("  WARN — should have raised ValueError for missing key")
        except ValueError as e:
            assert "API key" in str(e)
            print("  PASS — missing key raises ValueError")
    finally:
        if old_key:
            os.environ["DEEPSEEK_API_KEY"] = old_key
        if old_openai:
            os.environ["OPENAI_API_KEY"] = old_openai


# ── Test 6: TaskAnalyzer error handling ─────────────────────────────
def test_analyzer_errors():
    """TaskAnalyzer handles empty input and bad config gracefully."""
    from task_analyzer import TaskAnalyzer

    print("=" * 50)
    print("Test 6: TaskAnalyzer error handling")

    # Empty text
    analyzer = TaskAnalyzer(api_key="sk-fake-key-for-test", provider="deepseek")
    try:
        analyzer.analyze("")
        print("  WARN — should have raised ValueError for empty text")
    except ValueError as e:
        assert "Empty text" in str(e) or "empty" in str(e).lower()
        print("  PASS — empty text raises ValueError")

    # Whitespace-only text
    try:
        result = analyzer.analyze("   \n  ")
        print("  WARN — should have raised ValueError")
    except ValueError:
        print("  PASS — whitespace-only also raises ValueError")


# ── Run all ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_task_serialization()
    test_task_properties()
    test_analysis_result()
    test_prompt_building()
    test_llm_client_config()
    test_analyzer_errors()
    print("\n" + "=" * 50)
    print("All analyzer tests passed!")
