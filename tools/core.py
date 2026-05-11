"""核心工具：时间、计算、书籍管理、天气"""

import json
import os

from langchain_core.tools import tool, StructuredTool

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOKS_FILE = os.path.join(BASE_DIR, "books.json")


def _load_books() -> list:
    with open(BOOKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_books(books: list):
    with open(BOOKS_FILE, "w", encoding="utf-8") as f:
        json.dump(books, f, ensure_ascii=False, indent=2)


@tool
def get_current_time(city: str) -> str:
    """获取指定城市的当前时间"""
    from datetime import datetime
    now = datetime.now()
    return f"{city} 当前时间：{now.strftime('%Y-%m-%d %H:%M:%S')}"


@tool
def calculate(expression: str) -> str:
    """计算数学表达式，支持加减乘除"""
    allowed = set("0123456789+-*/.() ")
    if not all(c in allowed for c in expression):
        return "错误：表达式包含不允许的字符"
    try:
        result = eval(expression)  # noqa: S307
        return f"计算结果：{expression} = {result}"
    except Exception as e:
        return f"计算错误：{e}"


@tool
def search_books(keyword: str, field: str = "title") -> str:
    """按关键词精确搜索书籍，支持按书名(title)、作者(author)、分类(category)搜索"""
    books = _load_books()
    results = []
    for book in books:
        if field == "category" and keyword in book.get("category", ""):
            results.append(book)
        elif field == "author" and keyword in book.get("author", ""):
            results.append(book)
        elif field == "title" and keyword in book.get("title", ""):
            results.append(book)

    if not results:
        return f"未找到与 {field}='{keyword}' 匹配的书籍"

    lines = []
    for b in results:
        lines.append(
            f"《{b.get('title', '?')}》- {b.get('author', '?')} "
            f"({b.get('category', '?')}, {b.get('publish_date', '?')})"
        )
    return "\n".join(lines)


def _add_book_func(title: str, author: str, publish_date: str, category: str) -> str:
    """上架一本新书"""
    books = _load_books()
    for b in books:
        if b.get("title") == title and b.get("author") == author:
            return f"《{title}》已存在于书库，无需重复添加"
    books.append({
        "title": title, "author": author,
        "publish_date": publish_date, "category": category,
    })
    _save_books(books)
    return f"✅ 已成功上架《{title}》（{author}，{category}）"


add_book = StructuredTool.from_function(
    func=_add_book_func,
    name="add_book",
    description="上架一本新书到书库",
)
add_book.metadata = {"need_confirm": True}


@tool
def search_weather(city: str) -> str:
    """查询指定城市的天气情况"""
    weather_db = {
        "北京": "晴天，12°C，空气质量良好",
        "上海": "多云，15°C，有轻微雾霾",
        "深圳": "阴天，22°C，可能有小雨",
    }
    return weather_db.get(city, f"暂无{city}的天气数据（当前仅支持北京、上海、深圳）")


# 所有核心工具列表
CORE_TOOLS = [get_current_time, calculate, search_books, add_book, search_weather]
