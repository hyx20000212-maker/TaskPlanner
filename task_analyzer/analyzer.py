"""
Core Task Analyzer — orchestrates LLM call and parses structured results.
"""

import json
from datetime import date
from typing import Optional

from task_analyzer.models import Task, TaskAnalysisResult
from task_analyzer.llm_client import LLMClient
from task_analyzer.prompts import build_system_prompt, build_user_prompt


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


# ── Convenience function ────────────────────────────────────────────

def analyze_text(
    raw_text: str,
    api_key: Optional[str] = None,
    provider: str = "deepseek",
    language: str = "en",
) -> TaskAnalysisResult:
    """One-liner: analyze a task description and return structured results."""
    analyzer = TaskAnalyzer(api_key=api_key, provider=provider)
    return analyzer.analyze(raw_text, language=language)
