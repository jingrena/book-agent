"""智能推荐工作流子图"""

from langchain_core.messages import HumanMessage
from langchain_core.callbacks import dispatch_custom_event
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END

from state import RecommendWorkflowState
from tools.rag import search_books_semantic


def _emit(event_type: str, data: dict, config: RunnableConfig = None):
    if config:
        dispatch_custom_event(event_type, data, config=config)


def semantic_search_node(state: dict, config: RunnableConfig) -> dict:
    """语义检索候选书目"""
    ctx = state.get("workflow_context", {})
    query = ctx.get("query", "")

    _emit("step", {"message": "Step 1: 语义检索"}, config)

    # 调用 search_books_semantic 工具
    result = search_books_semantic.invoke({"query": query, "top_k": 3})
    return {"workflow_context": {**ctx, "candidates": result}}


def personalize_node(state: dict, config: RunnableConfig, *,
                     llm=None, memory_list: list = None,
                     rag_store=None) -> dict:
    """个性化推荐：结合用户记忆筛选候选"""
    ctx = state.get("workflow_context", {})
    candidates = ctx.get("candidates", "")
    query = ctx.get("query", "")

    _emit("step", {"message": "Step 2: 个性化推荐"}, config)

    # RAG 语义检索记忆
    memory_text = ""
    if rag_store and query:
        try:
            results = rag_store.search_memories(query, top_k=5)
            if results:
                memory_text = "用户偏好：" + "；".join(text for text, _, _ in results)
        except Exception:
            pass
    if not memory_text and memory_list:
        memory_text = "用户偏好：" + "；".join(memory_list)

    prompt = (
        f"候选书目：\n{candidates}\n\n"
        f"{memory_text}\n\n"
        f"请从候选中选出最符合用户偏好的 1-2 本，给出推荐理由。用中文回复。"
    )

    if llm:
        try:
            resp = llm.invoke([HumanMessage(content=prompt)])
            reply = resp.content or "推荐生成失败"
        except Exception as e:
            reply = f"推荐生成超时({e})，以下是候选书目供参考：\n{candidates}"
    else:
        reply = candidates

    _emit("workflow_end", {"message": "工作流【智能推荐】完成"}, config)
    return {"final_reply": reply}


def build_recommend_workflow(llm=None, memory_list: list = None, rag_store=None):
    """构建智能推荐工作流子图"""
    graph = StateGraph(RecommendWorkflowState)

    graph.add_node("semantic_search", semantic_search_node)

    def personalize_wrapped(state: dict, config: RunnableConfig) -> dict:
        return personalize_node(state, config, llm=llm, memory_list=memory_list, rag_store=rag_store)

    graph.add_node("personalize", personalize_wrapped)

    graph.set_entry_point("semantic_search")
    graph.add_edge("semantic_search", "personalize")
    graph.add_edge("personalize", END)

    return graph.compile()
