"""书评生成 Skill：为书籍生成专业书评

LangChain @tool 版本：用 @tool 装饰器替代 SKILL_TOOLS，用 SPECIALISTS 列表替代 SKILL_SPECIALISTS
"""

import os
import json

from langchain_core.tools import tool

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_books() -> list:
    with open(os.path.join(BASE_DIR, "books.json"), "r", encoding="utf-8") as f:
        return json.load(f)


@tool
def get_book_info(book_title: str) -> str:
    """查询指定书籍的详细信息（书名、作者、分类、出版日期），供书评参考"""
    books = _load_books()
    for b in books:
        if book_title in b.get("title", ""):
            return (
                f"书名：《{b['title']}》\n"
                f"作者：{b['author']}\n"
                f"分类：{b['category']}\n"
                f"出版：{b['publish_date']}"
            )
    return f"未找到《{book_title}》，请确认书名是否正确"


@tool
def compare_books_info(book1: str, book2: str) -> str:
    """查询两本书的详细信息，供比较分析使用"""
    books = _load_books()
    info1 = info2 = None
    for b in books:
        if book1 in b.get("title", ""):
            info1 = b
        if book2 in b.get("title", ""):
            info2 = b

    lines = []
    if info1:
        lines.append(f"书籍A：《{info1['title']}》（{info1['author']}）分类：{info1['category']} 出版：{info1['publish_date']}")
    else:
        lines.append(f"未找到《{book1}》")
    if info2:
        lines.append(f"书籍B：《{info2['title']}》（{info2['author']}）分类：{info2['category']} 出版：{info2['publish_date']}")
    else:
        lines.append(f"未找到《{book2}》")
    return "\n".join(lines)


# 专家定义（由 specialists.py 的 load_skill_specialists 加载）
SPECIALISTS = [
    {
        "key": "critic",
        "name": "书评家",
        "system_prompt": (
            "你是一位资深书评家，擅长深入分析书籍的主题、叙事手法和文学价值。\n"
            "写书评时兼顾学术性和可读性，给出有深度的见解。\n"
            "先用 get_book_info 工具查询书籍信息，再基于这些信息撰写书评。\n"
            "书评风格根据用户要求调整（中性/推荐/批评），默认200-300字。\n"
            "如果用户要求比较两本书，用 compare_books_info 查询后进行比较分析。\n"
            "请用中文回复。"
        ),
        "tools": ["get_book_info", "compare_books_info", "search_books"],
    },
]

# 路由关键词
KEYWORDS = ["书评", "评价", "评论", "比较.*书", "推荐理由"]
