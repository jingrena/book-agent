"""新书入库工作流子图"""

import json

from langchain_core.messages import HumanMessage
from langchain_core.callbacks import dispatch_custom_event
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt

from state import NewBookWorkflowState
from tools.core import _load_books, _save_books


def _emit(event_type: str, data: dict, config: RunnableConfig = None):
    if config:
        dispatch_custom_event(event_type, data, config=config)


def check_duplicate_node(state: dict, config: RunnableConfig) -> dict:
    """查重：检查书籍是否已存在"""
    ctx = state.get("workflow_context", {})
    title = ctx.get("title", "")
    author = ctx.get("author", "")

    books = _load_books()
    duplicate = False
    for b in books:
        if b.get("title") == title and b.get("author") == author:
            duplicate = True
            break

    ctx["duplicate"] = duplicate
    if duplicate:
        _emit("step", {"message": f"发现重复：《{title}》已存在于书库"}, config)
    else:
        _emit("step", {"message": f"查重通过：《{title}》不存在重复"}, config)

    return {"workflow_context": ctx}


def auto_classify_node(state: dict, config: RunnableConfig, *, llm=None) -> dict:
    """智能分类：用户指定优先，否则关键词匹配，最后 LLM"""
    ctx = state.get("workflow_context", {})
    if ctx.get("duplicate"):
        return {"workflow_context": {**ctx, "_classify_result": "已存在，跳过分类"}}
    if ctx.get("category"):
        return {"workflow_context": {**ctx, "_classify_result": f"使用用户指定分类：{ctx['category']}"}}

    title = ctx.get("title", "")
    author = ctx.get("author", "")

    category_hints = {
        "科幻": ["三体", "银河", "星球", "太空", "宇宙", "基地", "流浪地球"],
        "文学": ["活着", "围城", "百年", "孤独", "苏菲", "红楼", "人间"],
        "计算机": ["算法", "深度学习", "设计模式", "编程", "代码", "数学之美"],
        "历史": ["人类简史", "枪炮", "钢铁", "文明", "帝国"],
        "哲学": ["苏菲的世界", "存在", "思想", "沉思"],
    }
    for cat, keywords in category_hints.items():
        for kw in keywords:
            if kw in title or kw in author:
                ctx["category"] = cat
                return {"workflow_context": {**ctx, "_classify_result": f"快速分类结果：{cat}"}}

    # LLM 分类
    if llm:
        _emit("step", {"message": "正在智能分类（调用 LLM）..."}, config)
        prompt = (
            f"请为以下书籍分一个类别，只能从这些类别中选：文学、科幻、计算机、历史、哲学、经济、其他。\n"
            f"书名：{title}\n作者：{author}\n\n"
            f"只返回类别名称，不要其他内容。"
        )
        try:
            resp = llm.invoke([HumanMessage(content=prompt)], config={"temperature": 0})
            category = resp.content.strip()
            valid = {"文学", "科幻", "计算机", "历史", "哲学", "经济", "其他"}
            if category not in valid:
                category = "其他"
            ctx["category"] = category
            return {"workflow_context": {**ctx, "_classify_result": f"智能分类结果：{category}"}}
        except Exception as e:
            ctx["category"] = ctx.get("category", "其他")
            return {"workflow_context": {**ctx, "_classify_result": f"分类超时，使用默认分类：{ctx['category']}"}}

    ctx["category"] = ctx.get("category", "其他")
    return {"workflow_context": {**ctx, "_classify_result": f"默认分类：{ctx['category']}"}}


def confirm_and_add_node(state: dict, config: RunnableConfig) -> dict:
    """确认上架：通过 interrupt 暂停等待用户确认"""
    ctx = state.get("workflow_context", {})
    if ctx.get("duplicate"):
        return {"workflow_context": {**ctx, "_add_result": "跳过上架（重复书籍）"}}

    title = ctx.get("title", "")
    author = ctx.get("author", "")
    publish_date = ctx.get("publish_date", "")
    category = ctx.get("category", "其他")

    fields = {
        "书名": title,
        "作者": author,
        "出版日期": publish_date,
        "分类": category,
    }

    # 暂停图执行，等待人类确认
    confirmation = interrupt({
        "confirm_type": "add_book",
        "detail": f"书名：《{title}》\n作者：{author}\n出版日期：{publish_date}\n分类：{category}",
        "fields": fields,
    })

    if not confirmation.get("confirmed"):
        ctx["cancelled"] = True
        return {"workflow_context": {**ctx, "_add_result": "用户取消上架"}}

    # 应用修改
    modifications = confirmation.get("modifications", {})
    field_map = {"书名": "title", "作者": "author", "出版日期": "publish_date", "分类": "category"}
    for label, key in field_map.items():
        val = modifications.get(label, "").strip()
        if val:
            ctx[key] = val

    # 上架
    from tools.core import _add_book_func
    result = _add_book_func(
        title=ctx["title"], author=ctx["author"],
        publish_date=ctx["publish_date"], category=ctx["category"],
    )
    return {"workflow_context": {**ctx, "_add_result": result}}


def notify_node(state: dict, config: RunnableConfig) -> dict:
    """通知"""
    ctx = state.get("workflow_context", {})
    title = ctx.get("title", "")
    author = ctx.get("author", "")

    if ctx.get("duplicate"):
        msg = f"📢 通知：《{title}》（{author}）已存在，未重复入库"
    elif ctx.get("cancelled"):
        msg = f"📢 通知：《{title}》（{author}）上架已取消"
    else:
        msg = f"📢 通知：新书《{title}》（{author}）已成功入库！"

    _emit("workflow_end", {"message": f"工作流【新书入库】完成"}, config)
    return {"final_reply": msg}


# 条件边
def after_check_duplicate(state: dict) -> str:
    if state.get("workflow_context", {}).get("duplicate"):
        return "notify"
    return "auto_classify"


def after_confirm(state: dict) -> str:
    return "notify"


def build_new_book_workflow(llm=None):
    """构建新书入库工作流子图"""
    graph = StateGraph(NewBookWorkflowState)

    def auto_classify_wrapped(state: dict, config: RunnableConfig) -> dict:
        return auto_classify_node(state, config, llm=llm)

    graph.add_node("check_duplicate", check_duplicate_node)
    graph.add_node("auto_classify", auto_classify_wrapped)
    graph.add_node("confirm_and_add", confirm_and_add_node)
    graph.add_node("notify", notify_node)

    graph.set_entry_point("check_duplicate")
    graph.add_conditional_edges("check_duplicate", after_check_duplicate,
                                {"auto_classify": "auto_classify", "notify": "notify"})
    graph.add_edge("auto_classify", "confirm_and_add")
    graph.add_edge("confirm_and_add", "notify")
    graph.add_edge("notify", END)

    return graph.compile()
