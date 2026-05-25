"""借书工作流子图"""

from langchain_core.callbacks import dispatch_custom_event
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END

from state import BorrowWorkflowState


def _emit(event_type: str, data: dict, config: RunnableConfig = None):
    if config:
        dispatch_custom_event(event_type, data, config=config)


def check_availability_node(state: dict, config: RunnableConfig) -> dict:
    """检查库存是否充足"""
    ctx = state.get("workflow_context", {})
    book_title = ctx.get("book_title", "")

    _emit("step", {"message": "Step 1: 检查库存"}, config)

    from tools.borrow import _load_borrows, _active_count, STOCK_PER_BOOK
    borrows = _load_borrows()
    available = STOCK_PER_BOOK - _active_count(borrows, book_title)
    return {"workflow_context": {**ctx, "available": available}}


def record_borrow_node(state: dict, config: RunnableConfig) -> dict:
    """写入借阅记录"""
    ctx = state.get("workflow_context", {})
    book_title = ctx.get("book_title", "")
    borrower = ctx.get("borrower", "")

    _emit("step", {"message": "Step 2: 办理借阅"}, config)

    from tools.borrow import borrow_book
    result = borrow_book.invoke({"book_title": book_title, "borrower": borrower})
    return {"workflow_context": {**ctx, "borrow_result": result}}


def borrow_notify_node(state: dict, config: RunnableConfig) -> dict:
    """生成最终回复"""
    ctx = state.get("workflow_context", {})
    book_title = ctx.get("book_title", "")

    if ctx.get("available", 0) <= 0:
        msg = f"抱歉，《{book_title}》全部库存均已借出，暂无可借册数"
    else:
        msg = ctx.get("borrow_result", "借阅处理完成")

    _emit("workflow_end", {"message": "工作流【借书】完成"}, config)
    return {"final_reply": msg}


def after_check_availability(state: dict) -> str:
    if state.get("workflow_context", {}).get("available", 0) <= 0:
        return "notify"
    return "record_borrow"


def build_borrow_workflow():
    graph = StateGraph(BorrowWorkflowState)

    graph.add_node("check_availability", check_availability_node)
    graph.add_node("record_borrow", record_borrow_node)
    graph.add_node("notify", borrow_notify_node)

    graph.set_entry_point("check_availability")
    graph.add_conditional_edges("check_availability", after_check_availability,
                                {"record_borrow": "record_borrow", "notify": "notify"})
    graph.add_edge("record_borrow", "notify")
    graph.add_edge("notify", END)

    return graph.compile()
