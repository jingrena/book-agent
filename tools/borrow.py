"""借阅管理工具"""

import json
import os
import uuid
from datetime import datetime, timedelta

from langchain_core.tools import tool

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BORROWS_FILE = os.path.join(BASE_DIR, "borrows.json")
STOCK_PER_BOOK = 3


def _load_borrows() -> list:
    if not os.path.exists(BORROWS_FILE):
        return []
    with open(BORROWS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_borrows(borrows: list):
    with open(BORROWS_FILE, "w", encoding="utf-8") as f:
        json.dump(borrows, f, ensure_ascii=False, indent=2)


def _active_count(borrows: list, book_title: str) -> int:
    return sum(1 for b in borrows if b["book_title"] == book_title and not b["returned"])


@tool
def check_book_availability(book_title: str) -> str:
    """查询指定书籍的剩余可借册数"""
    borrows = _load_borrows()
    borrowed = _active_count(borrows, book_title)
    available = STOCK_PER_BOOK - borrowed
    return f"《{book_title}》总库存 {STOCK_PER_BOOK} 册，当前可借 {available} 册，已借出 {borrowed} 册"


@tool
def borrow_book(book_title: str, borrower: str, days: int = 30) -> str:
    """为借阅人办理借书，每本书库存3册，借期默认30天"""
    borrows = _load_borrows()
    if _active_count(borrows, book_title) >= STOCK_PER_BOOK:
        return f"抱歉，《{book_title}》全部 {STOCK_PER_BOOK} 册均已借出，暂无库存"

    today = datetime.now().date()
    due = today + timedelta(days=days)
    record = {
        "id": str(uuid.uuid4()),
        "book_title": book_title,
        "borrower": borrower,
        "borrow_date": str(today),
        "due_date": str(due),
        "returned": False,
        "return_date": None,
    }
    borrows.append(record)
    _save_borrows(borrows)
    return f"✅ 借阅成功！{borrower} 借走《{book_title}》，应还日期：{due}"


@tool
def return_book(book_title: str, borrower: str) -> str:
    """为借阅人办理还书"""
    borrows = _load_borrows()
    for record in borrows:
        if record["book_title"] == book_title and record["borrower"] == borrower and not record["returned"]:
            record["returned"] = True
            record["return_date"] = str(datetime.now().date())
            _save_borrows(borrows)
            return f"✅ 还书成功！{borrower} 已归还《{book_title}》"
    return f"未找到 {borrower} 借阅《{book_title}》的记录，请确认姓名和书名是否正确"


@tool
def query_borrows(borrower: str = "") -> str:
    """查询借阅记录，传入借阅人姓名查个人记录，不传则查所有未还记录"""
    borrows = _load_borrows()
    if borrower:
        records = [b for b in borrows if b["borrower"] == borrower and not b["returned"]]
        label = f"{borrower} 的未还借阅"
    else:
        records = [b for b in borrows if not b["returned"]]
        label = "所有未还借阅"

    if not records:
        return f"暂无{label}记录"

    lines = [f"共 {len(records)} 条{label}记录："]
    for r in records:
        lines.append(f"  《{r['book_title']}》借阅人：{r['borrower']}，应还日期：{r['due_date']}")
    return "\n".join(lines)


@tool
def check_overdue() -> str:
    """查询所有逾期未还的借阅记录"""
    borrows = _load_borrows()
    today = str(datetime.now().date())
    overdue = [b for b in borrows if not b["returned"] and b["due_date"] < today]

    if not overdue:
        return "当前没有逾期未还的书籍"

    lines = [f"共 {len(overdue)} 条逾期记录："]
    for r in overdue:
        lines.append(f"  《{r['book_title']}》借阅人：{r['borrower']}，应还日期：{r['due_date']}（已逾期）")
    return "\n".join(lines)


BORROW_TOOLS = [check_book_availability, borrow_book, return_book, query_borrows, check_overdue]
