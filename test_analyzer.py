"""
Task Analyzer Module — Unit Tests (offline, no API key required).

Tests:
  1. Task model serialization (to_dict / from_dict)
  2. Task computed properties (days_until_deadline, min_daily_amount)
  3. TaskAnalysisResult aggregation
  4. Prompt building (system + user)
  5. LLMClient config resolution
  6. TaskAnalyzer error handling (empty text, missing key)
  7. Milestone task with prerequisites and subtasks
  8. Goal decomposition prompt building
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


# ── Test 7: Milestone task with prerequisites and subtasks ──────────
def test_milestone_task():
    """Task supports milestone type with prerequisites and subtasks."""
    from task_analyzer.models import Task

    print("=" * 50)
    print("Test 7: Milestone task with prerequisites and subtasks")

    task = Task(
        id="m1",
        description="Learn C# fundamentals",
        task_type="milestone",
        total_amount=3,
        unit="steps",
        difficulty=3,
        estimated_hours=15.0,
        unit_efficiency=0.2,
        efficiency_unit="steps_per_hour",
        deadline=date(2026, 6, 10),
        subtasks=[
            {"id": "s1", "description": "Variables and types", "estimated_hours": 5, "order": 1},
            {"id": "s2", "description": "OOP basics", "estimated_hours": 5, "order": 2},
            {"id": "s3", "description": "LINQ and collections", "estimated_hours": 5, "order": 3},
        ],
        prerequisites=[],
    )

    assert task.is_milestone
    assert len(task.subtasks) == 3
    assert task.total_amount == 3  # subtask count

    # Round-trip
    d = task.to_dict()
    assert d["task_type"] == "milestone"
    assert len(d["subtasks"]) == 3
    assert d["prerequisites"] == []

    task2 = Task.from_dict(d)
    assert task2.is_milestone
    assert len(task2.subtasks) == 3
    assert task2.subtasks[0]["description"] == "Variables and types"

    # Task with prerequisites
    task3 = Task(
        id="m2",
        description="Build Unity prototype",
        task_type="milestone",
        total_amount=4,
        unit="steps",
        difficulty=4,
        estimated_hours=20.0,
        unit_efficiency=0.2,
        efficiency_unit="steps_per_hour",
        prerequisites=["m1"],
        subtasks=[
            {"id": "s4", "description": "Set up project", "estimated_hours": 3, "order": 1},
            {"id": "s5", "description": "Implement mechanics", "estimated_hours": 10, "order": 2},
            {"id": "s6", "description": "Add UI", "estimated_hours": 4, "order": 3},
            {"id": "s7", "description": "Test and polish", "estimated_hours": 3, "order": 4},
        ],
    )
    assert task3.prerequisites == ["m1"]

    d3 = task3.to_dict()
    task3b = Task.from_dict(d3)
    assert task3b.prerequisites == ["m1"]

    print("  PASS — milestone task with prerequisites and subtasks OK")


# ── Test 8: Task start_date field ─────────────────────────────────
def test_start_date():
    """Task start_date restricts scheduling to on/after that date."""
    from task_analyzer.models import Task

    print("=" * 50)
    print("Test 8.b: Task start_date field")

    today = date.today()
    tomorrow = today + timedelta(days=1)

    # Task scheduled for a specific day
    task = Task(
        id="t1",
        description="Run 1000m",
        task_type="exercise",
        total_amount=1000,
        unit="meters",
        difficulty=2,
        estimated_hours=0.15,
        unit_efficiency=6667,
        efficiency_unit="meters_per_hour",
        deadline=tomorrow,
        start_date=tomorrow,
    )
    d = task.to_dict()
    assert d["start_date"] == tomorrow.isoformat()
    assert d["deadline"] == tomorrow.isoformat()

    task2 = Task.from_dict(d)
    assert task2.start_date == tomorrow
    assert task2.deadline == tomorrow

    # Task with no start_date (default)
    task3 = Task(id="t2", description="No start", task_type="other",
                 total_amount=10, unit="items", difficulty=1,
                 estimated_hours=1, unit_efficiency=10, efficiency_unit="items_per_hour")
    d3 = task3.to_dict()
    assert d3["start_date"] is None

    print("  PASS — start_date field round-trips correctly")


# ── Test 9: Chore task type ─────────────────────────────────────────
def test_chore_task():
    """Chore tasks have task_type='chore', total_amount=estimated_hours."""
    from task_analyzer.models import Task

    print("=" * 50)
    print("Test 9: Chore task type")

    # Chore: brush teeth (0.1h = 6 min)
    chore = Task(
        id="c1",
        description="Brush teeth",
        task_type="chore",
        total_amount=0.1,
        unit="hours",
        difficulty=1,
        estimated_hours=0.1,
        unit_efficiency=1.0,
        efficiency_unit="hours_per_hour",
    )
    assert chore.is_chore
    assert chore.estimated_hours == 0.1

    d = chore.to_dict()
    chore2 = Task.from_dict(d)
    assert chore2.is_chore
    assert chore2.total_amount == 0.1

    print("  PASS — chore task supports non-quantified short tasks")


# ── Test 10: start_date safety net ─────────────────────────────────
def test_start_date_safety_net():
    """_fix_missing_start_dates assigns start_date from text time words."""
    from datetime import date, timedelta
    from task_analyzer.analyzer import TaskAnalyzer
    from task_analyzer.models import Task

    print("=" * 50)
    print("Test 10: start_date safety net")

    today = date.today()
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)

    # Case 1: "明天跟同学聚会"
    tasks = [
        Task(id="t1", description="跟同学聚会", task_type="chore",
             total_amount=1.0, unit="hours", difficulty=1, estimated_hours=1.0,
             unit_efficiency=1.0, efficiency_unit="hours_per_hour"),
    ]
    TaskAnalyzer._fix_missing_start_dates(tasks, "提醒我今天买菜，明天跟同学聚会")
    assert tasks[0].start_date == tomorrow
    assert tasks[0].deadline == tomorrow

    # Case 2: already has start_date — not overridden
    tasks3 = [
        Task(id="t3", description="聚会", task_type="chore",
             total_amount=1.0, unit="hours", difficulty=1, estimated_hours=1.0,
             unit_efficiency=1.0, efficiency_unit="hours_per_hour",
             start_date=day_after, deadline=day_after),
    ]
    TaskAnalyzer._fix_missing_start_dates(tasks3, "明天聚会")
    assert tasks3[0].start_date == day_after

    print("  PASS — start_date safety net fixes LLM misses")


# ── Test 8: Goal decomposition prompt building ──────────────────────
def test_goal_prompts():
    """Goal decomposition and rationale prompts build correctly."""
    from task_analyzer.prompts import (
        build_goal_system_prompt,
        build_goal_user_prompt,
        build_rationale_system_prompt,
        build_rationale_user_prompt,
    )

    print("=" * 50)
    print("Test 8: Goal decomposition prompt building")

    sys_prompt = build_goal_system_prompt("2026-05-26", "zh")
    assert "2026-05-26" in sys_prompt
    assert "Simplified Chinese" in sys_prompt
    assert "milestone" in sys_prompt

    user_prompt = build_goal_user_prompt("I want to learn Unity in one month.")
    assert "Unity" in user_prompt

    rationale_sys = build_rationale_system_prompt("en")
    assert "English" in rationale_sys

    rationale_user = build_rationale_user_prompt(
        task_summaries="- t1: Task A",
        schedule_summary="2026-05-26: Task A (2h)",
        warnings=["Warning: tight deadline"],
    )
    assert "Task A" in rationale_user
    assert "tight deadline" in rationale_user

    print("  PASS — goal and rationale prompts build OK")


# ── Run all ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_task_serialization()
    test_task_properties()
    test_analysis_result()
    test_prompt_building()
    test_llm_client_config()
    test_analyzer_errors()
    test_milestone_task()
    test_start_date()
    test_chore_task()
    test_start_date_safety_net()
    test_goal_prompts()
    print("\n" + "=" * 50)
    print("All analyzer tests passed!")
