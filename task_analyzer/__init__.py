"""
Task Analyzer Module — Uses LLM to analyze task descriptions and extract
structured task information (type, difficulty, duration, deadline).

Usage:
    from task_analyzer import TaskAnalyzer, TaskAnalysisResult

    analyzer = TaskAnalyzer(api_key="sk-...", base_url="https://api.deepseek.com/v1")
    result = analyzer.analyze("I need to memorize 500 words in 7 days.")

    for task in result.tasks:
        print(task.task_type, task.estimated_hours, task.deadline)
"""

from task_analyzer.analyzer import TaskAnalyzer, analyze_text, decompose_goal, generate_plan_rationale
from task_analyzer.models import Task, TaskAnalysisResult

__all__ = [
    "TaskAnalyzer",
    "Task",
    "TaskAnalysisResult",
    "analyze_text",
    "decompose_goal",
    "generate_plan_rationale",
]
