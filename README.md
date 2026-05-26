# Task Planner Agent — All 5 Modules Complete

> **Status:** All 5/5 modules complete  
> **Goal:** An AI agent that parses multi-task documents (PDF/Word/Text), considers deadlines, difficulty, and user schedules to auto-generate daily study plans.

---

## Project Structure

```
d:\Demo\
├── desktop_app/              # Desktop main program (system tray + topmost sticky + create/import tasks)
├── scripts/                  # Build/packaging scripts
├── dist/                     # Packaged .exe output directory
├── requirements.txt          # Python dependencies
├── test_parser.py            # Document parsing tests (6 items)
├── test_analyzer.py          # Task analysis tests (8 items)
├── test_schedule.py          # Schedule awareness tests (7 items)
├── test_planner.py           # Planning engine tests (11 items)
├── test_tracker.py           # Daily check-in tracker tests (8 items)
├── README.md                 # This file
├── 任务规划智能体_架构与流程.ipynb  # Architecture doc (notebook, Chinese)
├── doc_parser/               # Module 1: Document Parser
│   ├── __init__.py
│   ├── models.py             # ParsedDocument
│   ├── parser.py             # Unified entry point + routing
│   ├── pdf_parser.py         # PDF -> text (PyMuPDF)
│   ├── word_parser.py        # .docx -> text (python-docx)
│   ├── text_parser.py        # .txt/.md/raw string -> text
│   └── i18n.py               # CN/EN translation dictionary
├── task_analyzer/            # Module 2: Task Analyzer
│   ├── __init__.py
│   ├── models.py             # Task / TaskAnalysisResult
│   ├── analyzer.py           # Core analysis orchestration
│   ├── llm_client.py         # LLM client (DeepSeek / OpenAI)
│   └── prompts.py            # Prompt templates (with efficiency priors)
└── schedule_engine/          # Module 3: Schedule Engine
    ├── __init__.py
    ├── models.py             # DailySlot / UserSettings
    ├── engine.py             # Core scheduling orchestration
    └── holiday_api.py        # Chinese holiday API (timor.tech)
├── planning_engine/          # Module 4: Planning Engine
│   ├── __init__.py
│   ├── models.py             # DailyPlan / TaskAllocation / PlanResult
│   └── engine.py             # Constraint solving + proportional allocation
└── daily_tracker/            # Module 5: Daily Check-in Tracker
    ├── __init__.py
    ├── models.py             # CheckinState / TaskCheckItem / DayRecord
    ├── storage.py            # SQLite persistence
    ├── tracker.py            # Two-phase check-in + settlement + re-planning
    ├── quotes.py             # Daily motivational quotes + encouragement
    └── news_jokes.py         # Tech news + jokes (review page)
```

---

## Module 1 — Document Parser

### Features

- **PDF** (.pdf): Extract text page by page via PyMuPDF, detect encrypted PDFs.
- **Word** (.docx): Extract text from paragraphs and tables via python-docx.
- **Plain Text** (.txt, .md, manual input): Read from file or accept raw string input.

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| All code in **English** | Clean, maintainable, portable |
| UI strings in `i18n.py` | Users toggle between CN/EN interface |
| `ParsedDocument` in `models.py` | Avoid circular imports between parser and sub-parsers |
| Extension check **before** file existence check | Provide more accurate error messages (wrong type vs. missing file) |

### Test Results (6/6 passed)

```
Test 1: Manual raw text input         Passed
Test 2: .txt file parsing             Passed
Test 3: Unsupported file type         Passed
Test 4: File not found                Passed
Test 5: Both params provided          Passed
Test 6: No parameters provided        Passed
```

---

## Module 2 — Task Analyzer

### Features

- **LLM abstraction**: `LLMClient` wraps OpenAI SDK, supports DeepSeek / OpenAI, key from env var or UI input.
- **Structured prompts**: Built-in efficiency priors table (vocab 20-30 words/h, math 3-8 problems/h...), guides LLM to output standard JSON.
- **Multi-task detection**: Auto-detect and split multiple tasks from a single text block.
- **Goal decomposition**: For vague goals (e.g. "learn Unity in a month"), LLM autonomously breaks them into milestone tasks with ordered subtasks and prerequisite dependencies.
- **Plan rationale generation**: After plan generation, LLM explains the reasoning: why tasks are ordered that way, key trade-offs, and execution tips.
- **Result dataclass**: `Task` provides `days_until_deadline`, `min_daily_amount`, subtasks, and prerequisites for direct use by the planning engine.

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| `openai` SDK with custom `base_url` | DeepSeek API is fully OpenAI-compatible, no extra adapter needed |
| `response_format={"type":"json_object"}` | Force LLM to output valid JSON, avoid parse failures |
| Efficiency priors in System Prompt | Significantly improves time estimation accuracy |
| Separate goal decomposition prompt | Tailored for milestone creation, not raw task extraction |
| `Task` has `prerequisites` and `subtasks` | Enables milestone-type tasks and dependency-aware scheduling |
| `Task` has `min_daily_amount` | Planning engine can use it directly, reducing coupling |
| Offline tests (8 items) need no API Key | CI/CD friendly, test model serialization/prompts/error handling |

### Test Results (8/8 passed)

```
Test 1: Task model serialization        Passed
Test 2: Task computed properties        Passed
Test 3: TaskAnalysisResult aggregation  Passed
Test 4: Prompt building                 Passed
Test 5: LLMClient config resolution     Passed
Test 6: TaskAnalyzer error handling     Passed
Test 7: Milestone task with pre-reqs    Passed
Test 8: Goal & rationale prompts        Passed
```

---

## Module 3 — Schedule Engine

### Features

- **Manual settings**: User sets available hours per day for weekdays/weekends/holidays, with per-date busy-time overrides.
- **Chinese statutory holidays**: Auto-query timor.tech API, identify official holidays + adjusted workdays.
- **Three-layer overlay**: base settings -> holiday override -> manual busy deduction = final available time.
- **Date range generation**: Input start/end dates, output per-day `DailySlot` table.

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Skip OAuth calendar integration (P2) | High dev cost; P0+P1 covers 80% of use cases |
| API data cached per year | Only one request to timor.tech per year |
| Graceful degradation when API unavailable | Fall back to standard calendar (Mon-Fri work, weekends off) |
| Manual busy as `date=hours` text format | More flexible than forms, supports batch paste |

### Test Results (7/7 passed)

```
Test 1: DailySlot dataclass          Passed
Test 2: UserSettings get_base_hours  Passed
Test 3: Holiday API functions        Passed
Test 4: ScheduleEngine.generate      Passed
Test 5: Manual busy deduction        Passed
Test 6: Invalid date range           Passed
Test 7: DailySlot serialization      Passed
```

---

## Module 4 — Planning Engine

### Features

- **Two-phase allocation**: First ensure every task's minimum DDL requirement, then distribute remaining free time proportionally by remaining workload.
- **DDL-priority sorting**: Tasks with earlier deadlines + higher difficulty get allocated first.
- **Prerequisite-aware scheduling**: If task B depends on task A, B won't be allocated until A is fully completed.
- **Milestone progress tracking**: For milestone-type tasks, `total_amount` = subtask count; progress tracks completed subtasks.
- **Daily buffer**: Reserve 10% of time per day as buffer to prevent over-scheduling.
- **Task cap**: Single task max 4h/day to avoid burnout.
- **Infeasibility detection**: Total demand > total supply or insufficient time before DDL -> auto alert.

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Proportional allocation over greedy | Prevents one task from monopolizing all time |
| Phase 1 minimum guarantee + Phase 2 proportional | Ensures urgent tasks don't fall behind |
| Prerequisite blocking with warnings | Makes dependencies visible to the user |
| Buffer ratio configurable | User adjustable (0%-30%) |
| Plan result includes CSV export | Easy to print or import into other calendar tools |

### Test Results (11/11 passed)

```
Test 1: Planning models              Passed
Test 2: Basic plan generation        Passed
Test 3: DDL-based priority           Passed
Test 4: Buffer ratio                 Passed
Test 5: Single task completes        Passed
Test 6: Infeasibility detection      Passed
Test 7: PlanResult serialization     Passed
Test 8: Daily recurring tasks        Passed
Test 9: Prerequisite-aware scheduling Passed
Test 10: PlanResult rationale field   Passed
Test 11: Goal detection heuristic     Passed
```

---

## Module 5 — Daily Check-in Tracker (+ Goal Decomposition)

### Features

- **Goal decomposition**: For non-quantified goals (e.g. "learn Unity in a month and build a game"), the system auto-detects the input type and decomposes it into milestone tasks with ordered subtasks and prerequisite dependencies.
- **Prerequisite-aware scheduling**: The planning engine respects task dependencies — a blocked task won't be scheduled until its prerequisites are complete.
- **Plan rationale**: After generating a plan, the AI produces a natural-language explanation of the planning logic: why tasks are ordered this way, key trade-offs, and execution tips. The rationale can be revisited anytime from the Review window via the "View AI Analysis" button.
- **Fixed-height task list**: When there are more than 2 tasks, the task list uses a fixed-height scrollable area so the window doesn't grow excessively long. Scroll with mouse wheel.
- **Review window**: Shows yesterday's recap, current progress, and a button to revisit the AI's original plan analysis.
- **Auto-create when no plan**: If no existing plan is detected, the settings window supports PDF/Word/TXT/MD upload or text input, walking through parsing, AI analysis/decomposition, and plan generation in one flow.
- **Two-phase check-in**: Phase 1 greeting + quote + yesterday review -> confirm; Phase 2 task list -> three-tier check -> complete.
- **Task list import**: Import new tasks from the daily task interface; system merges tasks, dynamically re-plans, and preserves today's checked items.
- **Even distribution strategy**: Planning engine limits daily task count by default, rotating through different tasks; urgent near-DDL tasks get priority and may exceed the limit.
- **Soft deadline for no-DDL tasks**: If a task has no DDL, the system assigns a reasonable soft deadline based on task type, difficulty, and estimated hours.
- **Sticky note settings**: Adjustable transparency; topmost toggle; delete all/individual tasks with confirmation; historical check-in records preserved.
- **Desktop-only architecture**: tkinter + pystray desktop app with system tray icon, show/hide topmost sticky note, all features accessible through Settings.
- **Three-tier goals**: Minimum/Ideal/Challenge, mutually exclusive per task with confirmation dialog to prevent misclicks.
- **Daily quotes**: 20 Chinese + 20 English motivational quotes, rotated daily.
- **Encouragement + praise**: All challenge yesterday -> encouragement message; all checked today -> praise + balloon animation.
- **Daily settlement**: Default midnight, user-customizable settlement time; checked items logged by tier, unchecked logged as 0.
- **SQLite persistence**: Check-in state, history, preferences, and plan snapshots all stored in database.

### Entry Points

| App | Run Command | Purpose |
|-----|-------------|---------|
| `dist/TaskPlannerDesktop.exe` | Double-click | Recommended entry: desktop sticky + settings for creating/importing tasks + check-in + re-plan |
| `desktop_app/main.py` | `python -m desktop_app.main` | Dev entry: same as .exe, easier to debug |

The desktop .exe is the only entry point. The app supports both quantified tasks (e.g. "memorize 500 words in 7 days") and high-level goals (e.g. "learn Unity and build a game in one month") — goals are automatically decomposed into milestone tasks with subtasks and prerequisites.

### Test Results (8/8 passed)

```
Test 1: TaskCheckItem              Passed
Test 2: CheckinState properties    Passed
Test 3: DayRecord all_challenge    Passed
Test 4: TrackerStorage CRUD        Passed
Test 5: get_or_create_today        Passed
Test 6: Two-phase flow             Passed
Test 7: Settlement                 Passed
Test 8: Quotes and jokes           Passed
```

---

## How to Run

### 1. Setup

```powershell
cd d:\Demo
uv venv
uv pip install -r requirements.txt
```

### 2. Run Tests

```powershell
.venv\Scripts\python.exe test_parser.py
```

### 3. Launch Desktop App

```powershell
# Run desktop app in dev mode
.venv\Scripts\python.exe -m desktop_app.main

# Package .exe
.\scripts\build_desktop_exe.ps1

# Run .exe
.\dist\TaskPlannerDesktop.exe
```

---

## Implementation Roadmap

| Module | Description | Status |
|--------|-------------|--------|
| **1. Document Parser** | PDF / Word / TXT -> extract text | Complete |
| **2. Task Analyzer** | LLM analysis: task type, difficulty, estimated hours, DDL; goal decomposition into milestones | Complete |
| **3. Schedule Engine** | Holiday API + user availability -> daily time slots | Complete |
| **4. Planning Engine** | Constraint solving + proportional allocation + prerequisite dependencies -> daily plan + rationale | Complete |
| **5. Output & Tracking** | Two-phase check-in + three-tier goals + quotes + settlement + goal decomposition + plan explanation | Complete |

---

## Project Complete!

All five modules ready. Desktop-only architecture with tkinter + pystray. Supports both quantified tasks and high-level goals (auto-decomposed into milestones with dependencies). AI-generated plan rationale explains the reasoning behind every schedule. **40 tests all passing.**

---

*Last updated: 2026-05-26*

