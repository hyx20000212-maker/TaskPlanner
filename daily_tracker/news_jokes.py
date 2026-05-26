"""
Tech / study-related news blurbs and light jokes for the "Review Progress" view.
Rotates content when users revisit the progress summary.
"""

NEWS_JOKES_ZH = [
    "📰 最新研究：番茄工作法搭配AI助手，效率提升47%。",
    "📰 DeepSeek发布新版模型，长文本理解能力再次突破。",
    "📰 2026年GitHub年度报告：Python超越JavaScript成为最活跃语言。",
    "😄 程序员为什么喜欢dark mode？因为光会吸引bug。",
    "😄 有一个bug活了三年，不是因为修不好，是因为每次看到它都觉得很可爱。",
    "😄 AI问我：你要咖啡还是茶？我说来杯咖啡——结果它帮我写了三小时的代码。",
    "📰 Notion发布AI原生笔记功能，学习效率工具又进化了。",
    "📰 研究表明：把大目标拆成小任务，完成率提升3倍。",
    "😄 背单词最好的方法：假装第二天要考试。",
    "😄 学习数学的秘诀：假装每道题都值100万。",
    "📰 认知科学新发现：间隔重复比连续学习记忆效果高2.8倍。",
    "😄 问：什么时候复习效果最好？答：考试前十分钟。问：认真的呢？答：每天十分钟。",
]

NEWS_JOKES_EN = [
    "📰 Study: Pomodoro technique combined with AI assistants boosts efficiency by 47%.",
    "📰 DeepSeek launches new model with breakthrough long-context understanding.",
    "📰 GitHub 2026 report: Python overtakes JavaScript as the most active language.",
    "😄 Why do programmers prefer dark mode? Because light attracts bugs.",
    "😄 That bug lived 3 years — not because it was hard, but because it was cute.",
    "😄 AI asked me: coffee or tea? I said coffee — it wrote 3 hours of code instead.",
    "📰 Notion releases AI-native notes — learning tools evolve again.",
    "📰 Research shows breaking big goals into small tasks triples completion rate.",
    "😄 Best way to memorize vocabulary: pretend the exam is tomorrow.",
    "😄 The secret to math: pretend every problem is worth 1 million dollars.",
    "📰 Cognitive science: spaced repetition is 2.8x more effective than cramming.",
    "😄 Q: When's the best time to review? A: 10 minutes before the exam. Q: Seriously? A: 10 minutes every day.",
]


def get_news_joke(lang: str = "zh", index: int = 0) -> str:
    items = NEWS_JOKES_ZH if lang == "zh" else NEWS_JOKES_EN
    return items[index % len(items)]
