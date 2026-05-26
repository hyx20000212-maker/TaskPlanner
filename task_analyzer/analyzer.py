"""
Core Task Analyzer — orchestrates LLM call and parses structured results.
"""

import json
from datetime import date
from typing import Optional

from task_analyzer.models import Task, TaskAnalysisResult
from task_analyzer.llm_client import LLMClient
from task_analyzer.prompts import (
    build_system_prompt,
    build_user_prompt,
    build_goal_system_prompt,
    build_goal_user_prompt,
    build_rationale_system_prompt,
    build_rationale_user_prompt,
)


class TaskAnalyzer:
    """Analyze task descriptions using an LLM and return structured Task objects.

    Usage:
        analyzer = TaskAnalyzer(api_key="sk-...", provider="deepseek")
        result = analyzer.analyze("Memorize 500 words in 7 days.")
        print(result.tasks[0].deadline)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        provider: str = "deepseek",
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.3,
    ):
        """
        Args:
            api_key: LLM API key. If None, reads from environment.
            provider: "deepseek" or "openai".
            model: Model name override.
            base_url: Custom API base URL.
            temperature: LLM temperature (0.0-2.0).
        """
        self.llm = LLMClient(
            api_key=api_key,
            provider=provider,
            model=model,
            base_url=base_url,
            temperature=temperature,
        )

    def analyze(self, raw_text: str, language: str = "en") -> TaskAnalysisResult:
        """Analyze raw task description text and return structured results.

        Args:
            raw_text: The task description text (from document parser or manual input).
            language: Human-facing output language for task descriptions and notes.

        Returns:
            TaskAnalysisResult with list of Task objects.
        """
        if not raw_text or not raw_text.strip():
            raise ValueError("Empty text — cannot analyze.")

        # Truncate very long input to avoid token overflow
        text = raw_text.strip()
        if len(text) > 6000:
            text = text[:6000] + "\n...[truncated]"
            truncation_warning = True
        else:
            truncation_warning = False

        # Build prompts
        today = date.today().isoformat()
        system_prompt = build_system_prompt(today, language=language)
        user_prompt = build_user_prompt(text)

        # Call LLM
        try:
            response = self.llm.chat_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as e:
            return TaskAnalysisResult(
                tasks=[],
                warnings=[f"LLM call failed: {e}"],
                raw_response=str(e),
            )

        # Extract metadata
        meta = response.pop("_meta", {})
        raw_json = json.dumps(response, ensure_ascii=False, indent=2)

        # Parse tasks
        tasks_data = response.get("tasks", [])
        tasks = [Task.from_dict(t) for t in tasks_data]

        # Collect warnings
        warnings = response.get("warnings", [])
        if truncation_warning:
            warnings.append("Text was truncated to 6000 chars — analysis may be incomplete.")

        # Post-process: fix missing deadline for relative dates
        # (This is a safety net; the prompt already handles this)
        for task in tasks:
            if task.deadline is None:
                warnings.append(
                    f"Task '{task.description}' has no deadline. "
                    f"Please provide a deadline for accurate planning."
                )

        return TaskAnalysisResult(
            tasks=tasks,
            warnings=warnings,
            raw_response=raw_json,
            model_used=meta.get("model", self.llm.model),
            tokens_used=meta.get("tokens_used", 0),
        )

    def decompose_goal(self, raw_text: str, language: str = "en") -> dict:
        """Decompose a high-level goal into milestone tasks with subtasks and dependencies.

        Use this when the user input is a vague goal (e.g. "learn Unity in a month")
        rather than concrete quantified tasks.

        Args:
            raw_text: The goal description text.
            language: Human-facing output language.

        Returns:
            Dict with keys: goal_summary, tasks (list[Task]), rationale (str), warnings.
        """
        if not raw_text or not raw_text.strip():
            raise ValueError("Empty text — cannot analyze.")

        text = raw_text.strip()
        if len(text) > 4000:
            text = text[:4000] + "\n...[truncated]"

        today = date.today().isoformat()
        system_prompt = build_goal_system_prompt(today, language=language)
        user_prompt = build_goal_user_prompt(text)

        try:
            response = self.llm.chat_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as e:
            return {
                "goal_summary": raw_text[:100],
                "tasks": [],
                "rationale": "",
                "warnings": [f"LLM call failed: {e}"],
            }

        tasks_data = response.get("tasks", [])
        tasks = [Task.from_dict(t) for t in tasks_data]

        # Post-process: ensure milestone tasks have subtasks
        for task in tasks:
            if task.is_milestone and not task.subtasks:
                task.subtasks = [{
                    "id": f"{task.id}_sub_001",
                    "description": task.description,
                    "estimated_hours": task.estimated_hours,
                    "order": 1,
                }]

        return {
            "goal_summary": response.get("goal_summary", ""),
            "tasks": tasks,
            "rationale": response.get("rationale", ""),
            "warnings": response.get("warnings", []),
        }

    def generate_rationale(
        self,
        tasks: list[Task],
        schedule_summary: str,
        warnings: list[str],
        language: str = "en",
    ) -> str:
        """Generate a natural-language explanation of the plan.

        Args:
            tasks: The tasks in the plan.
            schedule_summary: A text summary of the daily schedule.
            warnings: Any feasibility warnings from the planner.
            language: Output language for the rationale.

        Returns:
            Natural language rationale text.
        """
        task_lines = []
        for t in tasks:
            deps = f" (prerequisites: {', '.join(t.prerequisites)})" if t.prerequisites else ""
            deadline = t.deadline.isoformat() if t.deadline else "none"
            subtask_count = len(t.subtasks) if t.subtasks else 0
            subtask_info = f", {subtask_count} subtasks" if subtask_count else ""
            task_lines.append(
                f"- {t.id}: {t.description} | {t.estimated_hours:.1f}h | "
                f"deadline={deadline} | type={t.task_type}{subtask_info}{deps}"
            )
        task_summaries = "\n".join(task_lines)

        system_prompt = build_rationale_system_prompt(language)
        user_prompt = build_rationale_user_prompt(
            task_summaries=task_summaries,
            schedule_summary=schedule_summary,
            warnings=warnings,
        )

        try:
            response = self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.5,
                max_tokens=1024,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"(Could not generate rationale: {e})"


# ── Convenience functions ────────────────────────────────────────────

def analyze_text(
    raw_text: str,
    api_key: Optional[str] = None,
    provider: str = "deepseek",
    language: str = "en",
) -> TaskAnalysisResult:
    """One-liner: analyze a task description and return structured results."""
    analyzer = TaskAnalyzer(api_key=api_key, provider=provider)
    return analyzer.analyze(raw_text, language=language)


def decompose_goal(
    raw_text: str,
    api_key: Optional[str] = None,
    provider: str = "deepseek",
    language: str = "en",
) -> dict:
    """One-liner: decompose a goal into milestone tasks."""
    analyzer = TaskAnalyzer(api_key=api_key, provider=provider)
    return analyzer.decompose_goal(raw_text, language=language)


def generate_plan_rationale(
    tasks: list[Task],
    schedule_summary: str,
    warnings: list[str],
    api_key: Optional[str] = None,
    provider: str = "deepseek",
    language: str = "en",
) -> str:
    """One-liner: generate plan rationale text."""
    analyzer = TaskAnalyzer(api_key=api_key, provider=provider)
    return analyzer.generate_rationale(tasks, schedule_summary, warnings, language)
