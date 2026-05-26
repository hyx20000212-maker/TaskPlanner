# 任务规划智能体 — 全部 5 模块完成 🎉

> **当前状态：** 全部 5/5 模块已完成 ✅  
> **目标：** 构建一个 AI 智能体，解析多任务文档（PDF/Word/文本），结合 DDL、难度和用户日程，自动生成每日学习计划。

---

## 📂 项目结构

```
d:\Demo\
├── app.py                    # Streamlit 配置 App（设置→分析→日程→规划）
├── tracker_app.py            # 便利贴每日打卡 App（双阶段+鸡汤+新闻）
├── desktop_app/              # 桌面主程序（托盘+置顶小便签+创建/导入任务）
├── scripts/                  # 打包脚本
├── dist/                     # 打包后的 exe 输出目录
├── requirements.txt          # Python 依赖
├── test_parser.py            # 文档解析测试（6 项）
├── test_analyzer.py          # 任务分析测试（6 项）
├── test_schedule.py          # 日程感知测试（7 项）
├── test_planner.py           # 规划引擎测试（7 项）
├── test_tracker.py           # 每日打卡测试（8 项）
├── README.md                 # 本文件
├── 任务规划智能体_架构与流程.ipynb  # 架构文档
├── doc_parser/               # 模块 ① 文档解析
│   ├── __init__.py
│   ├── models.py             # ParsedDocument
│   ├── parser.py             # 统一入口 + 路由
│   ├── pdf_parser.py         # PDF → 文本（PyMuPDF）
│   ├── word_parser.py        # .docx → 文本（python-docx）
│   ├── text_parser.py        # .txt/.md/手动输入 → 文本
│   └── i18n.py               # 中英文翻译字典
├── task_analyzer/            # 模块 ② 任务分析
│   ├── __init__.py
│   ├── models.py             # Task / TaskAnalysisResult
│   ├── analyzer.py           # 核心分析编排
│   ├── llm_client.py         # LLM 客户端（DeepSeek / OpenAI）
│   └── prompts.py            # Prompt 模板（含效率先验知识）
└── schedule_engine/          # 模块 ③ 日程感知
    ├── __init__.py
    ├── models.py             # DailySlot / UserSettings
    ├── engine.py             # 核心调度编排
    └── holiday_api.py        # 中国节假日 API（timor.tech）
├── planning_engine/          # 模块 ④ 规划引擎
│   ├── __init__.py
│   ├── models.py             # DailyPlan / TaskAllocation / PlanResult
│   └── engine.py             # 约束求解 + 比例分配算法
└── daily_tracker/            # 模块 ⑤ 每日打卡追踪
    ├── __init__.py
    ├── models.py             # CheckinState / TaskCheckItem / DayRecord
    ├── storage.py            # SQLite 持久化
    ├── tracker.py            # 双阶段打卡 + 结算 + 重规划
    ├── quotes.py             # 每日鸡汤 + 鼓励 + 表扬文案
    └── news_jokes.py         # 技术新闻 + 冷笑话（回顾页用）
```

---

## ✅ 已完成：模块 1 — 文档解析

### 功能说明

- **PDF** (.pdf)：通过 PyMuPDF 逐页提取文本，检测加密 PDF。
- **Word** (.docx)：通过 python-docx 提取段落和表格中的文本。
- **纯文本** (.txt, .md, 手动打字)：从文件读取或接受原始字符串输入。

### 关键设计决策

| 决策 | 原因 |
|------|------|
| 代码全部使用 **英文** | 干净、可维护、可移植 |
| UI 文案集中在 `i18n.py` | 用户通过开关切换中/英文界面 |
| `ParsedDocument` 放在 `models.py` | 避免 parser 与 sub-parser 之间的循环引用 |
| 扩展名校验**先于**文件存在校验 | 给出更准确的错误提示（类型不对 vs 文件缺失） |

### 测试结果（6/6 通过）

```
Test 1: Manual raw text input         ✅ 通过
Test 2: .txt file parsing             ✅ 通过
Test 3: Unsupported file type         ✅ 通过
Test 4: File not found                ✅ 通过
Test 5: Both params provided          ✅ 通过
Test 6: No parameters provided        ✅ 通过
```

---

## ✅ 已完成：模块 2 — 任务分析器

### 功能说明

- **LLM 调用抽象**：`LLMClient` 封装 OpenAI SDK，支持 DeepSeek / OpenAI，环境变量或 UI 输入 Key
- **结构化 Prompt**：内置效率先验知识表（背单词 20-30 个/h、数学 3-8 道/h…），让 LLM 输出标准 JSON
- **多任务识别**：自动检测一段文本中的多个任务并拆分
- **结果数据类**：`Task` 提供 `days_until_deadline`、`min_daily_amount` 等计算属性，供规划引擎直接使用

### 关键设计决策

| 决策 | 原因 |
|------|------|
| `openai` SDK 直连 + 自定义 base_url | DeepSeek API 与 OpenAI 完全兼容，无需额外适配 |
| `response_format={"type":"json_object"}` | 强制 LLM 输出合法 JSON，避免解析失败 |
| 效率先验知识写入 System Prompt | 显著提升时长估算准确度 |
| `Task` 自带 `min_daily_amount` | 规划引擎可以直接用，减少耦合 |
| 离线测试（6 项）无需 API Key | CI/CD 友好，测试模型序列化/Prompt/错误处理 |

### 测试结果（6/6 通过）

```
Test 1: Task model serialization        ✅ 通过
Test 2: Task computed properties        ✅ 通过
Test 3: TaskAnalysisResult aggregation  ✅ 通过
Test 4: Prompt building                 ✅ 通过
Test 5: LLMClient config resolution     ✅ 通过
Test 6: TaskAnalyzer error handling     ✅ 通过
```

---

## ✅ 已完成：模块 3 — 日程感知器

### 功能说明

- **用户手动设定**：工作日/周末/节假日每天可用几小时，支持按日期标记忙碌时间
- **中国法定节假日**：自动查询 timor.tech API，识别法定假日 + 调休工作日
- **三层叠加**：用户基础设定 → 节假日覆盖 → 手动忙碌扣除 = 最终可用时间
- **日期范围生成**：输入起止日期，输出每日 `DailySlot` 表

### 关键设计决策

| 决策 | 原因 |
|------|------|
| 跳过 OAuth 日历集成（P2） | 开发成本高，P0+P1 已覆盖 80% 场景 |
| API 数据按年缓存 | 同一年份只请求一次 timor.tech |
| API 不可用时优雅降级 | 按普通日历算（周一至周五工作，周末休息） |
| 手动忙碌用 `date=hours` 文本格式 | 比表单更灵活，支持批量粘贴 |

### 测试结果（7/7 通过）

```
Test 1: DailySlot dataclass          ✅ 通过
Test 2: UserSettings get_base_hours  ✅ 通过
Test 3: Holiday API functions        ✅ 通过
Test 4: ScheduleEngine.generate      ✅ 通过
Test 5: Manual busy deduction        ✅ 通过
Test 6: Invalid date range           ✅ 通过
Test 7: DailySlot serialization      ✅ 通过
```

---

## ✅ 已完成：模块 4 — 规划引擎

### 功能说明

- **两阶段分配算法**：先保证每个任务的最低 DDL 需求，再按剩余工作量比例分配空闲时间
- **DDL 优先排序**：截止日期早的 + 难度高的任务优先分配
- **每日缓冲**：每天预留 10% 时间为缓冲，防止排太满
- **任务上限**：单个任务每天不超过 4h，避免疲劳
- **不可行检测**：总需求 > 总供给或某任务 DDL 前时间不足 → 自动告警

### 关键设计决策

| 决策 | 原因 |
|------|------|
| 比例分配而非贪心 | 避免"一个任务独占所有时间" |
| Phase 1 最低保障 + Phase 2 比例 | 保证 DDL 紧迫的任务不至于落后 |
| 缓冲比率可配置 | 用户可调整（0%-30%） |
| 规划结果自带 CSV 导出 | 方便打印或导入其他日历工具 |

### 测试结果（7/7 通过）

```
Test 1: Planning models              ✅ 通过
Test 2: Basic plan generation        ✅ 通过
Test 3: DDL-based priority           ✅ 通过
Test 4: Buffer ratio                 ✅ 通过
Test 5: Single task completes        ✅ 通过
Test 6: Infeasibility detection      ✅ 通过
Test 7: PlanResult serialization     ✅ 通过
```

---

## ✅ 已完成：模块 5 — 每日打卡追踪

### 功能说明

- **无计划自动创建**：如果 `tracker_app.py` 检测不到已有计划，会直接显示简化配置界面，支持上传 PDF/Word/TXT/MD 或输入文本，一路完成解析、AI 分析、日程设置和计划生成
- **双阶段打卡**：阶段一问候+鸡汤+昨日回顾 → 确认；阶段二任务列表 → 三档打勾 → 完成
- **任务列表导入**：可在每日任务界面导入新任务，系统会合并任务、动态重规划，并保留当天已勾选的任务状态
- **均匀分配策略**：规划引擎默认限制每天普通任务数量，尽量轮换安排不同任务；临近 DDL 的紧急任务会优先安排，必要时允许突破限制
- **无 DDL 软截止期**：如果用户输入的任务没有 DDL，系统会根据任务类型、难度和预估耗时自动补一个合理软截止期，让规划引擎提高每日任务量而不是无限期拖延
- **便利贴设置**：支持透明度调整；支持删除所有当前任务，删除前需要二次确认，历史打卡记录保留
- **桌面主入口**：新增 tkinter + pystray 桌面程序，支持常驻系统托盘、显示/隐藏置顶小便签、读取 `tracker.db`、三档打卡；设置窗口内可创建初始计划、打字导入新任务、选择 PDF/Word/TXT/MD 文件、设置工作日/周末/节假日可用时间、透明度调整、删除当前任务并二次确认
- **三档目标**：最低/理想/挑战，同任务三档互斥选择，切换带确认弹窗防误触
- **每日鸡汤**：20 句中文+20 句英文，每天轮换
- **鼓励+表扬**：昨日全挑战 → 鼓励文案；今日全打勾 → 表扬+气球动画
- **回顾任务进度**：从阶段二可跳到回顾页，展示技术新闻/冷笑话+当前进度
- **每日结算**：默认 0 点，用户可自定义结算时间；有勾按档位记录，没勾记 0
- **SQLite 持久化**：打卡状态、历史记录、偏好设置全部入库

### 入口分工

| App | 运行命令 | 用途 |
|-----|----------|------|
| `dist/TaskPlannerDesktop.exe` | 双击运行 | 推荐入口：桌面便签 + 设置里创建/导入任务 + 打卡 + 重规划 |
| `desktop_app/main.py` | `python -m desktop_app.main` | 开发入口：与 exe 同功能，便于调试 |
| `app.py` | `streamlit run app.py` | 一次性配置：解析任务→LLM分析→设日程→生成计划 |
| `tracker_app.py` | `streamlit run tracker_app.py` | 日常使用：便利贴界面；无计划时可直接创建计划，已有计划时可导入新任务并重规划 |

桌面 exe 现在是主入口。Streamlit 版保留为开发/调试入口，不再是创建任务的必需步骤。

### 测试结果（8/8 通过）

```
Test 1: TaskCheckItem              ✅ 通过
Test 2: CheckinState properties    ✅ 通过
Test 3: DayRecord all_challenge    ✅ 通过
Test 4: TrackerStorage CRUD        ✅ 通过
Test 5: get_or_create_today        ✅ 通过
Test 6: Two-phase flow             ✅ 通过
Test 7: Settlement                 ✅ 通过
Test 8: Quotes and jokes           ✅ 通过
```

---

## 🚀 如何运行

### 1. 环境搭建

```powershell
cd d:\Demo
uv venv
uv pip install -r requirements.txt
```

### 2. 运行测试

```powershell
.venv\Scripts\python.exe test_parser.py
```

### 3. 启动桌面程序

```powershell
# 开发方式运行桌面程序
.venv\Scripts\python.exe -m desktop_app.main

# 打包 exe
.\scripts\build_desktop_exe.ps1

# 运行 exe
.\dist\TaskPlannerDesktop.exe
```

### 4. 可选：启动 Streamlit 调试界面

```powershell
# 可选：完整配置任务、日程、生成计划
.venv\Scripts\python.exe -m streamlit run app.py

# Web 版便利贴；保留用于调试
.venv\Scripts\python.exe -m streamlit run tracker_app.py
```

---

## 📋 实现路线图

| 模块 | 描述 | 状态 |
|------|------|------|
| **1. 文档解析** | PDF / Word / TXT → 提取文本 | ✅ 已完成 |
| **2. 任务分析** | LLM 分析任务类型、难度、预估时长、DDL | ✅ 已完成 |
| **3. 日程感知** | 节假日 API + 用户空闲设定 → 每日可用时间表 | ✅ 已完成 |
| **4. 规划引擎** | 约束求解 + 比例分配 → 每日任务计划 | ✅ 已完成 |
| **5. 输出与追踪** | 双阶段打卡 + 三档目标 + 鸡汤 + 结算 + 无计划创建 + 导入重规划 | ✅ 已完成 |

---

## 🎯 项目完成！

五个模块全部就绪，全量 **34 项测试全部通过**。

---

*最后更新：2026-05-20*

