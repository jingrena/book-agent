"""翻译助手 Skill：多语言翻译能力

LangChain @tool 版本：用 @tool 装饰器替代 SKILL_TOOLS，用 SPECIALISTS 列表替代 SKILL_SPECIALISTS
"""

from langchain_core.tools import tool


_COMMON_TERMS = {
    "三体": "The Three-Body Problem",
    "流浪地球": "The Wandering Earth",
    "活着": "To Live",
    "围城": "Fortress Besieged",
    "红楼梦": "Dream of the Red Chamber",
    "百年孤独": "One Hundred Years of Solitude",
    "人类简史": "Sapiens: A Brief History of Humankind",
    "数学之美": "The Beauty of Mathematics",
}


@tool
def lookup_dictionary(term: str) -> str:
    """查询常用术语（书名、专有名词等）的标准翻译对照"""
    result = _COMMON_TERMS.get(term)
    if result:
        return f"「{term}」的标准翻译为：{result}"
    return f"未找到「{term}」的对照翻译，请由翻译官自行翻译"


# 专家定义
SPECIALISTS = [
    {
        "key": "translator",
        "name": "翻译官",
        "system_prompt": (
            "你是一个专业翻译官，擅长中英日韩法等多语言互译。\n"
            "翻译时保持原文风格和语气，学术文本用学术用语，文学文本保留文学性。\n"
            "翻译书名或专有名词时，先用 lookup_dictionary 查询标准译名，没有对照的自行翻译。\n"
            "请用中文回复非翻译部分。"
        ),
        "tools": ["lookup_dictionary"],
    },
]

# 路由关键词
KEYWORDS = ["翻译", "translate", "译成", "英文版", "日文版", "语言检测"]
