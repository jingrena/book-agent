"""书籍盘点工作流子图"""

from langchain_core.messages import HumanMessage
from langchain_core.callbacks import dispatch_custom_event
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END

from state import InventoryWorkflowState
from tools.core import _load_books


def _emit(event_type: str, data: dict, config: RunnableConfig = None):
    if config:
        dispatch_custom_event(event_type, data, config=config)


def statistics_node(state: dict, config: RunnableConfig) -> dict:
    """统计馆藏数据"""
    _emit("step", {"message": "Step 1: 统计"}, config)

    books = _load_books()
    total = len(books)
    categories = {}
    for b in books:
        cat = b.get("category", "未分类")
        categories[cat] = categories.get(cat, 0) + 1

    lines = [f"总藏书：{total} 本"]
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        lines.append(f"  {cat}：{count} 本")

    stats = "\n".join(lines)
    return {"workflow_context": {"statistics": stats}}


def report_node(state: dict, config: RunnableConfig, *, llm=None) -> dict:
    """生成馆藏报告"""
    ctx = state.get("workflow_context", {})
    stats = ctx.get("statistics", "")

    _emit("step", {"message": "Step 2: 生成报告"}, config)

    prompt = (
        f"以下是书库统计数据：\n{stats}\n\n"
        f"请生成一份简短的馆藏报告，包含总览和各类别分析建议。用中文回复。"
    )

    if llm:
        try:
            resp = llm.invoke([HumanMessage(content=prompt)])
            reply = resp.content or "报告生成失败"
        except Exception as e:
            reply = f"报告生成超时({e})，以下是原始统计数据：\n{stats}"
    else:
        reply = stats

    _emit("workflow_end", {"message": "工作流【书籍盘点】完成"}, config)
    return {"final_reply": reply}


def build_inventory_workflow(llm=None):
    """构建书籍盘点工作流子图"""
    graph = StateGraph(InventoryWorkflowState)

    def report_wrapped(state: dict, config: RunnableConfig) -> dict:
        return report_node(state, config, llm=llm)

    graph.add_node("statistics", statistics_node)
    graph.add_node("report", report_wrapped)

    graph.set_entry_point("statistics")
    graph.add_edge("statistics", "report")
    graph.add_edge("report", END)

    return graph.compile()
