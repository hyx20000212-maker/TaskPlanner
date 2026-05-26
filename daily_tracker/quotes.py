"""
Daily motivation quotes and study/work aphorisms in Chinese and English.
Rotates daily so users see a new one each day.
"""

GREETINGS_ZH = [
    "早上好，今天也慢慢进入状态。",
    "新的一天开始了，先把节奏稳住。",
    "今天见，先从一件小事开始。",
    "欢迎回来，今天的计划已经在这里。",
    "今天也辛苦了，按自己的节奏推进就好。",
    "新的任务日开始了，先看一眼今天要做什么。",
    "准备好了就开始，今天不用一下子做到完美。",
]

GREETINGS_EN = [
    "Good morning. Ease into today's rhythm.",
    "A new day starts here. Keep the pace steady.",
    "Welcome back. Start with one small thing.",
    "Today's plan is ready when you are.",
    "Take it at your pace today.",
    "A new task day begins. Let's see what's ahead.",
    "Start when you're ready. It doesn't need to be perfect.",
]

QUOTES_ZH = [
    "今天的努力，是明天成功的伏笔。",
    "每一个不曾起舞的日子，都是对生命的辜负。",
    "不要等待机会，而要创造机会。",
    "学习就像爬山，每一步都算数。",
    "你所做的事情，可能暂时看不到成果，但不要灰心——你不是没有成长，而是在扎根。",
    "当你觉得晚了的时候，恰恰是最早的时候。",
    "世上没有白走的路，每一步都算数。",
    "把目标刻在石头上，把计划写在沙子上。",
    "专注当下，未来自会水到渠成。",
    "不是看到希望才坚持，而是坚持了才看到希望。",
    "种一棵树最好的时间是十年前，其次是现在。",
    "成功不是将来才有的，而是从决定去做的那一刻起，持续累积而成。",
    "优秀不是一种行为，而是一种习惯。",
    "今天比昨天进步一点点，就是对时间最好的尊重。",
    "行动是治愈恐惧的良药，而犹豫将不断滋养恐惧。",
    "与其仰望星空，不如脚踏实地。",
    "你有无限可能，不要辜负每一天。",
    "伟大的作品不是靠力量，而是靠坚持来完成的。",
    "怕什么真理无穷，进一寸有一寸的欢喜。",
    "路虽远，行则将至；事虽难，做则必成。",
]

QUOTES_EN = [
    "The secret of getting ahead is getting started.",
    "Don't watch the clock; do what it does. Keep going.",
    "Start where you are. Use what you have. Do what you can.",
    "It does not matter how slowly you go as long as you do not stop.",
    "Small daily improvements over time lead to stunning results.",
    "You don't have to be great to start, but you have to start to be great.",
    "The only way to do great work is to love what you do.",
    "Success is not final, failure is not fatal: it is the courage to continue that counts.",
    "Your future is created by what you do today, not tomorrow.",
    "Discipline is the bridge between goals and accomplishment.",
    "Focus on being productive instead of busy.",
    "The difference between ordinary and extraordinary is that little extra.",
    "Dream big. Start small. Act now.",
    "One day or day one. You decide.",
    "Push yourself, because no one else is going to do it for you.",
    "Consistency is what transforms average into excellence.",
    "You are what you do, not what you say you'll do.",
    "Wake up with determination. Go to bed with satisfaction.",
    "The pain of discipline is far less than the pain of regret.",
    "Don't limit your challenges. Challenge your limits.",
]

ENCOURAGEMENT_ZH = [
    "太棒了！昨天全目标达成挑战档，你是效率之王！👑",
    "昨天全最高档！这种状态继续保持下去！🔥",
    "满分通过昨天！奖励自己一杯咖啡吧，你值得！☕",
    "昨天展现了惊人的执行力，今天继续发光！✨",
]

ENCOURAGEMENT_EN = [
    "Amazing! All challenge tiers completed yesterday — you're a productivity king! 👑",
    "Perfect score yesterday! Keep this momentum going! 🔥",
    "All max tiers done! Treat yourself to a coffee, you earned it! ☕",
    "Incredible execution yesterday — keep shining today! ✨",
]

PRAISE_ZH = [
    "全部打勾！今天的任务圆满完成，太强了！🎉",
    "全部完成！你的自律让人佩服，明天继续加油！💪",
    "所有任务√！今天的你已经超越了昨天的自己！🌟",
    "完美的一天！每项任务都搞定了，享受一下成就感吧！🏆",
]

PRAISE_EN = [
    "All checked! Today's tasks are done — you're unstoppable! 🎉",
    "Everything completed! Your discipline is admirable, keep it up tomorrow! 💪",
    "All tasks done! Today you outdid yesterday's you! 🌟",
    "Perfect day! Every task crushed — enjoy that sense of achievement! 🏆",
]


def get_daily_quote(lang: str = "zh", index: int = 0) -> str:
    quotes = QUOTES_ZH if lang == "zh" else QUOTES_EN
    return quotes[index % len(quotes)]


def get_greeting(lang: str = "zh", index: int = 0) -> str:
    greetings = GREETINGS_ZH if lang == "zh" else GREETINGS_EN
    return greetings[index % len(greetings)]


def get_encouragement(lang: str = "zh", index: int = 0) -> str:
    items = ENCOURAGEMENT_ZH if lang == "zh" else ENCOURAGEMENT_EN
    return items[index % len(items)]


def get_praise(lang: str = "zh", index: int = 0) -> str:
    items = PRAISE_ZH if lang == "zh" else PRAISE_EN
    return items[index % len(items)]
