"""System and user prompt templates for task analysis.

The prompt instructions are written in English for model reliability, while
human-facing fields can follow the selected UI language.
"""

# ── Default prior knowledge for task efficiency ─────────────────────
# These are injected into the system prompt to improve accuracy.
EFFICIENCY_PRIORS = """
## Efficiency Reference (units per hour, for a typical adult learner):

| Task Type   | Low Difficulty | Medium Difficulty | High Difficulty |
|-------------|---------------|-------------------|-----------------|
| memorize    | 30-40 words/h | 20-30 words/h     | 10-20 words/h   |
| exercise    | 6-8 problems/h| 3-5 problems/h    | 1-2 problems/h  |
| reading     | 40-60 pages/h | 25-40 pages/h     | 10-25 pages/h   |
| writing     | 500-800 words/h| 300-500 words/h  | 100-300 words/h |
| chore       | (short fixed-duration tasks, typically 5-60 min)          |
| project     | (varies widely — estimate based on description)           |
| other       | (estimate based on description)                           |

Note: For memorization tasks (e.g., vocabulary), include review/revision time.
Note: For exercise/physical tasks (running, swimming), estimate duration directly — 1000m run ≈ 0.1-0.15h, 5km run ≈ 0.4-0.6h.
"""

# ── System prompt ───────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert task analyst and study planner. Your job is to analyze a user's task description and extract structured information.

{EFFICIENCY_PRIORS}

## Your Task

Given the user's task description, produce a JSON object with the following structure:

```json
{{
  "tasks": [
    {{
      "id": "task_001",
      "description": "A concise 5-15 word description of the task",
      "task_type": "one of: memorize, exercise, reading, writing, chore, project, other",
      "total_amount": 500,
      "unit": "words / problems / pages / meters / items / time",
      "difficulty": 3,
      "estimated_hours": 25.0,
      "unit_efficiency": 20.0,
      "efficiency_unit": "words_per_hour / problems_per_hour / pages_per_hour",
      "deadline": "YYYY-MM-DD or null if not specified",
      "start_date": "YYYY-MM-DD or null",
      "suggested_daily_hours": 3.5,
      "confidence": 0.8,
      "notes": "Any relevant observations, assumptions made, or warnings",
      "recurrence": "none or daily"
    }}
  ],
  "warnings": ["Any issues detected: ambiguous deadline, very aggressive timeline, etc."]
}}
```

## Guidelines

1. **Extract deadline and start_date carefully**: 
   - "明天做X / 明天给我安排X / 明天跟同学聚会 / remind me to do X tomorrow / schedule X for tomorrow": set `start_date` = tomorrow AND `deadline` = tomorrow. The task should ONLY be scheduled on that day, never today.
   - "今天X / 提醒我今天X / today X": set `start_date` = today AND `deadline` = today. Schedule only today.
   - "后天X / 下周X": same pattern — `start_date` AND `deadline` both = the stated date.
   - "在X号之前完成 / by Friday / DDL: 5月26日": set `deadline` to that date, leave `start_date` as null. The task can be worked on any day from now until the deadline.
   - "下周开始X / start next week": set `start_date` to next Monday, leave `deadline` as null or as stated.
   - Convert relative dates (明天, 后天, 今天, 下周, 周末, today, tomorrow, next week, next month) to absolute dates assuming TODAY is {TODAY}.

1a. **Non-quantified chore tasks**: If the user mentions a brief one-off task that has no natural quantity — e.g. "刷牙" (brush teeth), "洗脸" (wash face), "买菜" (grocery shopping), "聚会" (hang out with friends), "提醒我X" (remind me to X) — set `task_type` = "chore", `total_amount` = `estimated_hours` (so e.g. 0.5 for a 30-min task), `unit` = "hours", `unit_efficiency` = 1.0. Estimate `estimated_hours` directly (chores are typically 0.1-2.0h). Set `start_date` and `deadline` based on the user's time words if any. Chores display a single "Complete" button — no min/ideal/challenge tiers.

2. **Estimate total hours**: Based on the efficiency table above, the difficulty level you judge, and the total amount. Be conservative — it's better to overestimate slightly than underestimate.

2a. **Numeric field types are strict**: `unit_efficiency`, `total_amount`, `difficulty`, `estimated_hours`, `suggested_daily_hours`, and `confidence` must be numbers only. Never put strings such as "pages_per_hour" or "words_per_hour" in `unit_efficiency`; put those strings only in `efficiency_unit`.

3. **Detect multiple tasks**: If the user describes multiple separate tasks (e.g., "memorize 500 words AND complete 20 math problems"), split them into separate task entries.

3a. **Daily recurring routines**: If the user asks for an ongoing daily routine without an end date, such as "每天背100个单词", "read 20 pages every day", or "daily listening practice", set `deadline` to null and `recurrence` to "daily". In this case `total_amount` means the amount per day, not a finite total. Do not invent a deadline for this type.

3b. **Vague goals need autonomous task creation**: If the user only gives a goal or event, such as "周末要考英语", "I have an English exam this weekend", or "next month I need to present a project", create reasonable concrete preparation tasks yourself. Split the goal into study/work tasks that can be scheduled, infer a deadline from the event date when possible, and explain assumptions in notes/warnings.

4. **Set confidence**: Use confidence score to indicate how certain you are:
   - 0.9-1.0: All information clearly stated in the description
   - 0.7-0.9: Most info clear, some reasonable assumptions made
   - 0.5-0.7: Significant assumptions needed
   - 0.3-0.5: Very vague description, best-guess estimates
   - <0.3: You're basically guessing; add a warning

5. **Flag issues in warnings**: 
   - Deadline is missing → "No deadline specified — please provide one for accurate planning"
   - Timeline seems unrealistic → "500 words in 2 days requires ~250 words/day — very aggressive"
   - Ambiguous task type → "Unclear if this is reading or exercise — assumed reading"

6. **Output language**: The description may be in Chinese, Japanese, or other languages. Write human-facing fields in {OUTPUT_LANGUAGE}: `description`, `unit`, `notes`, and `warnings`. Preserve the original meaning. Keep machine-readable enum fields in English exactly as specified: `task_type` and `efficiency_unit`.

Respond ONLY with valid JSON — no markdown code fences, no explanations outside the JSON."""


# ── User prompt template ────────────────────────────────────────────

USER_PROMPT_TEMPLATE = """Please analyze the following task description:

{RAW_TEXT}"""


# ── Multi-task detection prompt ─────────────────────────────────────

MULTI_TASK_HINT = """Note: this text may contain multiple distinct tasks. Please identify and separate each one."""


# ── Prompt builder ──────────────────────────────────────────────────

def build_system_prompt(today: str, language: str = "en") -> str:
    """Build the full system prompt with today's date injected."""
    output_language = "Simplified Chinese" if language == "zh" else "English"
    return SYSTEM_PROMPT.format(
        EFFICIENCY_PRIORS=EFFICIENCY_PRIORS,
        TODAY=today,
        OUTPUT_LANGUAGE=output_language,
    )


# ── Goal decomposition prompt (for non-quantified / vague goals) ────

GOAL_SYSTEM_PROMPT = """You are an expert learning-path designer and task decomposition specialist. Your job is to take a user's high-level goal and autonomously break it down into concrete, schedulable milestone tasks — each with ordered subtasks and prerequisite dependencies.

{EFFICIENCY_PRIORS}

## Your Task

Given the user's goal, produce a JSON object that decomposes the goal into a structured learning/working plan:

```json
{{
  "goal_summary": "A 1-sentence summary of what the user wants to achieve",
  "tasks": [
    {{
      "id": "task_001",
      "description": "Concise description of this milestone (5-15 words)",
      "task_type": "milestone",
      "total_amount": 4,
      "unit": "steps",
      "difficulty": 3,
      "estimated_hours": 20.0,
      "unit_efficiency": 0.2,
      "efficiency_unit": "steps_per_hour",
      "deadline": "YYYY-MM-DD",
      "suggested_daily_hours": 2.0,
      "confidence": 0.8,
      "notes": "Why this step is needed and any assumptions",
      "recurrence": "none",
      "prerequisites": [],
      "subtasks": [
        {{"id": "sub_001", "description": "First concrete step", "estimated_hours": 5.0, "order": 1}},
        {{"id": "sub_002", "description": "Second concrete step", "estimated_hours": 5.0, "order": 2}}
      ]
    }}
  ],
  "rationale": "A paragraph explaining the overall decomposition strategy: why these milestones, why in this order, key assumptions made, and how the timeline was estimated.",
  "warnings": ["Any concerns about timeline, missing info, or risky assumptions"]
}}
```

## Guidelines

1. **Detect the goal domain**: Identify what the user is trying to learn or build (programming, language, exam prep, creative project, etc.). Use domain knowledge to propose realistic milestones.

2. **Create ordered milestones**: Break the goal into 3-8 major milestones that build on each other. Each milestone should be a coherent unit of progress (e.g., "Learn C# fundamentals", "Build a simple Unity prototype").

3. **Define concrete subtasks per milestone**: Each milestone should have 2-6 concrete, actionable subtasks. Subtask `estimated_hours` should be realistic — most subtasks take 2-8 hours. The sum of subtask hours should approximately equal the milestone's `estimated_hours`.

4. **Set `total_amount` = number of subtasks**: For milestone tasks, `total_amount` is the subtask count. `unit_efficiency` = number_of_subtasks / estimated_hours.

5. **Set prerequisite dependencies**: If milestone B cannot start before milestone A is complete, add A's ID to B's `prerequisites` list. This ensures the planner schedules them sequentially.

6. **Estimate realistic timelines**: 
   - A beginner learning a new programming paradigm: 2-4 weeks full-time equivalent
   - A beginner learning a game engine: 4-8 weeks full-time equivalent
   - Adjust based on the user's stated timeframe
   - Spread milestones evenly across the available time window

7. **Today's date is {TODAY}**. Convert relative dates ("in one month", "by next week") to absolute YYYY-MM-DD format. Set each milestone's deadline as a progressive target within the overall window.

8. **Output language**: Write human-facing fields (`description`, `notes`, `subtasks[].description`, `rationale`, `warnings`, `goal_summary`) in {OUTPUT_LANGUAGE}. Keep machine-readable enum fields in English.

Respond ONLY with valid JSON — no markdown code fences, no explanations outside the JSON."""


GOAL_USER_TEMPLATE = """Please decompose this goal into a structured learning/work plan:

{RAW_TEXT}"""


# ── Plan rationale prompt ───────────────────────────────────────────

RATIONALE_SYSTEM_PROMPT = """You are an expert study planner explaining a generated schedule to a user. Given a plan that was algorithmically generated, explain the reasoning behind it in natural language that the user can understand.

## Your Task

Given the task list and the generated daily plan, produce a clear explanation (in {OUTPUT_LANGUAGE}) covering:

1. **Overall strategy**: Why the tasks were ordered and prioritized this way
2. **Key decisions**: Why certain tasks are grouped together or spread apart, why some days have more work than others
3. **Trade-offs and warnings**: Any risks (tight deadlines, potential overwork) and what to watch for
4. **Tips**: Practical advice for executing this plan successfully

Keep the explanation concise (3-6 paragraphs). Write in a supportive, helpful tone. Use bullet points only where appropriate.

Respond ONLY with the explanation text — no JSON, no markdown formatting."""


RATIONALE_USER_TEMPLATE = """Here is the plan to explain:

**Tasks:**
{TASK_SUMMARIES}

**Daily schedule summary:**
{SCHEDULE_SUMMARY}

**Warnings from the planner:**
{WARNINGS}

Please explain the reasoning behind this plan."""


def build_goal_system_prompt(today: str, language: str = "en") -> str:
    """Build the goal decomposition system prompt."""
    output_language = "Simplified Chinese" if language == "zh" else "English"
    return GOAL_SYSTEM_PROMPT.format(
        EFFICIENCY_PRIORS=EFFICIENCY_PRIORS,
        TODAY=today,
        OUTPUT_LANGUAGE=output_language,
    )


def build_goal_user_prompt(raw_text: str) -> str:
    """Build the goal decomposition user prompt."""
    return GOAL_USER_TEMPLATE.format(RAW_TEXT=raw_text)


def build_rationale_system_prompt(language: str = "en") -> str:
    """Build the plan rationale system prompt."""
    output_language = "Simplified Chinese" if language == "zh" else "English"
    return RATIONALE_SYSTEM_PROMPT.format(OUTPUT_LANGUAGE=output_language)


def build_rationale_user_prompt(
    task_summaries: str,
    schedule_summary: str,
    warnings: list[str],
) -> str:
    """Build the plan rationale user prompt."""
    return RATIONALE_USER_TEMPLATE.format(
        TASK_SUMMARIES=task_summaries,
        SCHEDULE_SUMMARY=schedule_summary,
        WARNINGS="\n".join(f"- {w}" for w in warnings) if warnings else "None",
    )


def build_user_prompt(raw_text: str, expect_multi: bool = False) -> str:
    """Build the user prompt, optionally with multi-task hint.

    Args:
        raw_text: The extracted text to analyze.
        expect_multi: If True, add a hint to look for multiple tasks.
    """
    prompt = USER_PROMPT_TEMPLATE.format(RAW_TEXT=raw_text)
    if expect_multi:
        prompt += "\n\n" + MULTI_TASK_HINT
    return prompt
