"""还书工作流子图"""

from langchain_core.callbacks import dispatch_custom_event
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END

from state import ReturnWorkflowState


def _emit(event_type: str, data: dict, config: RunnableConfig = None):
    if config:
        dispatch_custom_event(event_type, data, config=config)


def find_record_node(state: dict, config: RunnableConfig) -> dict:
    """查找借阅记录"""
    ctx = state.get("workflow_context", {})
    book_title = ctx.get("book_title", "")
    borrower = ctx.get("borrower", "")

    _emit("step", {"message": "Step 1: 查找借阅记录"}, config)

    from tools.borrow import _load_borrows
    borrows = _load_borrows()
    found = any(
        b["book_title"] == book_title and b["borrower"] == borrower and not b["returned"]
        for b in borrows
    )
    return {"workflow_context": {**ctx, "record_found": found}}


def record_return_node(state: dict, config: RunnableConfig) -> dict:
    """更新还书状态"""
    ctx = state.get("workflow_context", {})
    book_title = ctx.get("book_title", "")
    borrower = ctx.get("borrower", "")

    _emit("step", {"message": "Step 2: 办理还书"}, config)

    from tools.borrow import return_book
    result = return_book.invoke({"book_title": book_title, "borrower": borrower})
    return {"workflow_context": {**ctx, "return_result": result}}


def return_notify_node(state: dict, config: RunnableConfig) -> dict:
    """生成最终回复"""
    ctx = state.get("workflow_context", {})
    book_title = ctx.get("book_title", "")
    borrower = ctx.get("borrower", "")

    if not ctx.get("record_found"):
        msg = f"未找到 {borrower} 借阅《{book_title}》的记录，请确认姓名和书名是否正确"
    else:
        msg = ctx.get("return_result", "还书处理完成")

    _emit("workflow_end", {"message": "工作流【还书】完成"}, config)
    return {"final_reply": msg}


def after_find_record(state: dict) -> str:
    if state.get("workflow_context", {}).get("record_found"):
        return "record_return"
    return "notify"


def build_return_workflow():
    graph = StateGraph(ReturnWorkflowState)

    graph.add_node("find_record", find_record_node)
    graph.add_node("record_return", record_return_node)
    graph.add_node("notify", return_notify_node)

    graph.set_entry_point("find_record")
    graph.add_conditional_edges("find_record", after_find_record,
                                {"record_return": "record_return", "notify": "notify"})
    graph.add_edge("record_return", "notify")
    graph.add_edge("notify", END)

    return graph.compile()
