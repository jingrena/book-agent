"""专家定义 + create_react_agent 构建"""

from langgraph.prebuilt import create_react_agent


# 专家定义
SPECIALIST_DEFS = {
    "retriever": {
        "name": "检索员",
        "system_prompt": (
            "你是一个专业的图书检索员。\n"
            "你的唯一任务是帮用户精准找到书籍或查询借阅信息。使用搜索工具查找，不要做推荐或评价。\n"
            "如果找不到匹配的书，如实告知。请用中文回复。"
        ),
        "tools": ["search_books", "search_books_semantic", "query_borrows", "check_overdue", "check_book_availability"],
    },
    "recommender": {
        "name": "推荐官",
        "system_prompt": (
            "你是一个资深图书推荐官，擅长根据用户偏好做个性化推荐。\n"
            "**推荐前必须先调用搜索工具查询书库**，不允许凭记忆直接推荐。\n"
            "基于搜索结果，结合用户偏好给出有温度的推荐理由。请用中文回复。"
        ),
        "tools": ["search_books", "search_books_semantic"],
    },
    "general": {
        "name": "通用助手",
        "system_prompt": "你是一个智能助手，可以回答问题并使用工具获取信息。请用中文回复。",
        "tools": ["get_current_time", "calculate", "search_weather"],
    },
}

# Skill 专家在 skills/ 模块中定义，由 load_skill_specialists 动态加载


def build_specialist_agents(llm, all_tools: list):
    """为每个专家构建 create_react_agent 实例"""
    tool_map = {t.name: t for t in all_tools}
    specialists = {}

    for key, spec in SPECIALIST_DEFS.items():
        spec_tools = [tool_map[n] for n in spec["tools"] if n in tool_map]
        agent = create_react_agent(
            model=llm,
            tools=spec_tools,
            prompt=spec["system_prompt"],
        )
        specialists[key] = {
            "name": spec["name"],
            "agent": agent,
            "tools": spec["tools"],
        }

    return specialists


def load_skill_specialists():
    """动态加载 skills/ 中的专家定义"""
    import importlib
    import os
    import pkgutil

    skills_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")
    specialists = {}
    keywords = {}

    if not os.path.exists(skills_dir):
        return specialists, keywords

    for importer, modname, _ in pkgutil.iter_modules([skills_dir]):
        try:
            module = importlib.import_module(f"skills.{modname}")
            for spec_dict in getattr(module, "SPECIALISTS", []):
                key = spec_dict["key"]
                specialists[key] = spec_dict
            for kw in getattr(module, "KEYWORDS", []):
                keywords[kw] = modname
        except Exception as e:
            print(f"  ⚠️ 加载 Skill '{modname}' 专家失败：{e}")

    return specialists, keywords
