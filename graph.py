"""主 StateGraph 定义 + 编译"""

import os

from langchain_core.callbacks import dispatch_custom_event
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from state import BookAssistantState
from nodes import (
    input_guard, quick_reply, classify_intent,
    specialist_chain, output_guard, memory_update,
    after_input_guard, after_quick_reply, after_classify,
    extract_book_info, extract_borrow_info,
)
from specialists import build_specialist_agents, load_skill_specialists
from tools import get_all_tools
from llm import create_llm
from memory import load_memory
from rag import init_rag_store, get_rag_store


def _emit(event_type: str, data: dict, config: RunnableConfig = None):
    if config:
        dispatch_custom_event(event_type, data, config=config)


def build_graph():
    """构建完整的图书助手 StateGraph"""
    # 初始化 LLM
    llm = create_llm()

    # 加载记忆
    long_term_memory = load_memory()

    # 初始化 RAG
    rag_store = init_rag_store(memory_list=long_term_memory)

    # 加载所有工具
    all_tools = get_all_tools()

    # 构建专家
    specialist_agents = build_specialist_agents(llm, all_tools)

    # 加载 Skill 专家和关键词
    skill_specialists_map, skill_keywords = load_skill_specialists()

    # 将 Skill 专家添加到 specialist_agents
    tool_map = {t.name: t for t in all_tools}
    for key, spec in skill_specialists_map.items():
        if key not in specialist_agents:
            from langgraph.prebuilt import create_react_agent
            spec_tools = [tool_map[n] for n in spec["tools"] if n in tool_map]
            agent = create_react_agent(
                model=llm,
                tools=spec_tools,
                prompt=spec["system_prompt"],
            )
            specialist_agents[key] = {
                "name": spec["name"],
                "agent": agent,
                "tools": spec["tools"],
            }

    # 构建工作流
    from workflows import build_all_workflows
    workflow_defs = build_all_workflows(llm)

    # 为了让推荐工作流能访问 memory 和 rag_store，需要传入
    from workflows.recommend import build_recommend_workflow
    workflow_defs["智能推荐"]["graph"] = build_recommend_workflow(
        llm=llm, memory_list=long_term_memory, rag_store=rag_store,
    )

    # ---- 构建图 ----

    graph = StateGraph(BookAssistantState)

    # 节点：直接传函数引用，LangGraph 自动传 (state, config)
    graph.add_node("input_guard", input_guard)
    graph.add_node("quick_reply", quick_reply)

    def classify_intent_node(state: dict, config: RunnableConfig) -> dict:
        return classify_intent(
            state, config,
            llm=llm, workflow_defs=workflow_defs,
            specialist_defs=specialist_agents,
            skill_specialists=skill_specialists_map,
            skill_keywords=skill_keywords,
        )

    def workflow_router_node(state: dict, config: RunnableConfig) -> dict:
        target = state.get("route_target", "")
        wf = workflow_defs.get(target)
        if not wf:
            return {"final_reply": f"未找到工作流：{target}"}

        _emit("route", {"message": f"路由到工作流：【{target}】{wf['description']}"}, config)
        _emit("workflow_start", {"message": f"工作流【{target}】启动"}, config)

        ctx = {"workflow_context": {}, "session_id": state.get("session_id", "")}
        if target == "新书入库":
            from nodes import extract_book_info
            from langchain_core.messages import HumanMessage as HumanMsg
            # 聚合所有用户消息，解决多轮补全信息时找不到前几轮内容的问题
            all_msgs = state.get("messages", [])
            user_texts = [m.content for m in all_msgs if isinstance(m, HumanMsg)]
            combined = "\n".join(user_texts) if user_texts else state.get("user_input", "")
            book_info = extract_book_info(combined, llm=llm)
            ctx["workflow_context"].update(book_info)
            ctx["workflow_context"]["user_input"] = state.get("user_input", "")
            missing = []
            if not book_info.get("title"):
                missing.append("书名")
            if not book_info.get("author"):
                missing.append("作者")
            if not book_info.get("publish_date"):
                missing.append("出版日期")
            if missing:
                hint = "、".join(missing)
                return {"final_reply": f"请补充以下信息：{hint}。例如：上架《数学之美》作者吴军 2012-05-01"}
        elif target == "智能推荐":
            ctx["workflow_context"]["query"] = state.get("user_input", "")
        elif target in ("借书", "还书"):
            borrow_info = extract_borrow_info(state.get("user_input", ""), llm=llm)
            ctx["workflow_context"].update(borrow_info)
            missing = []
            if not borrow_info.get("book_title"):
                missing.append("书名")
            if not borrow_info.get("borrower"):
                missing.append("借阅人姓名")
            if missing:
                hint = "、".join(missing)
                return {"final_reply": f"请提供：{hint}。例如：我叫张三，想借《三体》"}

        result = wf["graph"].invoke(ctx, config=config)
        return {"final_reply": result.get("final_reply", ""), "workflow_context": result.get("workflow_context", {})}

    def specialist_chain_node(state: dict, config: RunnableConfig) -> dict:
        return specialist_chain(
            state, config,
            specialist_agents=specialist_agents, long_term_memory=long_term_memory,
        )

    def memory_update_node(state: dict, config: RunnableConfig) -> dict:
        return memory_update(
            state, config,
            llm=llm, long_term_memory=long_term_memory, rag_store=rag_store,
        )

    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("workflow_router", workflow_router_node)
    graph.add_node("specialist_chain", specialist_chain_node)
    graph.add_node("output_guard", output_guard)
    graph.add_node("memory_update", memory_update_node)

    # 边
    graph.set_entry_point("input_guard")
    graph.add_conditional_edges("input_guard", after_input_guard,
                                {"quick_reply": "quick_reply", "output_guard": "output_guard"})
    graph.add_conditional_edges("quick_reply", after_quick_reply,
                                {"classify_intent": "classify_intent", "output_guard": "output_guard"})
    graph.add_conditional_edges("classify_intent", after_classify,
                                {"workflow_router": "workflow_router",
                                 "specialist_chain": "specialist_chain",
                                 "output_guard": "output_guard"})
    graph.add_edge("workflow_router", "output_guard")
    graph.add_edge("specialist_chain", "output_guard")
    graph.add_edge("output_guard", "memory_update")
    graph.add_edge("memory_update", END)

    # 编译（带检查点支持 interrupt）
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer), {
        "llm": llm,
        "specialist_agents": specialist_agents,
        "workflow_defs": workflow_defs,
        "long_term_memory": long_term_memory,
        "rag_store": rag_store,
    }


# 全局实例（延迟初始化）
_compiled_graph = None
_app_context = None


def get_graph():
    """获取编译后的图实例"""
    global _compiled_graph, _app_context
    if _compiled_graph is None:
        _compiled_graph, _app_context = build_graph()
    return _compiled_graph, _app_context
