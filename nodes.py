"""主图节点函数"""

import json
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.callbacks import dispatch_custom_event
from langchain_core.runnables import RunnableConfig

from guardrails import guard_input, guard_output
from memory import load_memory, update_memory_async
from tools import get_tool_map
from callbacks import emit_event


# ============================================================
# 快捷回复表
# ============================================================

QUICK_REPLIES = {
    "你好": "你好！我是智能图书助手，可以帮你推荐书籍、上架新书、查询馆藏等，请问有什么可以帮你的？",
    "您好": "您好！我是智能图书助手，可以帮你推荐书籍、上架新书、查询馆藏等，请问有什么可以帮你的？",
    "hi": "你好！我是智能图书助手，有什么可以帮你的？",
    "hello": "你好！我是智能图书助手，有什么可以帮你的？",
    "谢谢": "不客气！如果还有其他问题，随时问我。",
    "感谢": "不客气！如果还有其他问题，随时问我。",
    "再见": "再见！祝您阅读愉快！",
    "拜拜": "再见！祝您阅读愉快！",
    "你是谁": "我是智能图书助手，擅长书籍推荐、馆藏管理、书籍点评等，有需要随时问我！",
    "你能做什么": "我可以帮你：📚 推荐书籍、📦 上架新书、📊 馆藏盘点、📖 书籍点评和翻译等，试试看吧！",
    "帮我": "好的！我可以帮你推荐书籍、上架新书、查询馆藏等，请告诉我具体需求？",
}

EXACT_MATCH_KEYS = {"hi", "hello", "你好", "您好", "谢谢", "感谢", "再见", "拜拜", "你是谁", "你能做什么", "帮我"}


def _emit(event_type: str, data: dict, config: RunnableConfig = None):
    """安全地发送自定义事件，有 config 时用 dispatch_custom_event，否则静默"""
    if config:
        dispatch_custom_event(event_type, data, config=config)


# ============================================================
# 节点函数
# ============================================================

def input_guard(state: dict, config: RunnableConfig) -> dict:
    """输入护栏：检测注入攻击和超长输入"""
    user_input = state.get("user_input", "")
    safe, reason = guard_input(user_input)
    if not safe:
        _emit("blocked", {"reason": reason}, config)
        return {
            "input_blocked": True,
            "block_reason": reason,
            "final_reply": f"抱歉，您的输入未通过安全检查：{reason}",
        }
    return {"input_blocked": False, "block_reason": ""}


def quick_reply(state: dict, config: RunnableConfig) -> dict:
    """快捷回复：匹配问候语等简单输入"""
    if state.get("input_blocked"):
        return {"quick_reply": None}

    user_input = state.get("user_input", "").strip()
    lower = user_input.lower()

    for key in EXACT_MATCH_KEYS:
        if lower == key.lower():
            reply = QUICK_REPLIES.get(key)
            if reply:
                _emit("token", {"text": reply}, config)
                return {"quick_reply": reply, "final_reply": reply}

    return {"quick_reply": None}


def classify_intent(state: dict, config: RunnableConfig, *,
                    llm=None, workflow_defs: dict = None,
                    specialist_defs: dict = None, skill_specialists: dict = None,
                    skill_keywords: dict = None) -> dict:
    """意图分类：关键词匹配 + LLM 兜底"""
    if state.get("input_blocked"):
        return {"route_type": "quick_reply", "route_target": None}

    user_input = state.get("user_input", "")
    _emit("thinking", {"message": "正在分析意图..."}, config)

    lower = user_input.lower()

    # 工作流关键词
    add_keywords = ["上架", "入库", "添加书", "新增书", "录入"]
    recommend_keywords = ["推荐", "推荐书", "适合我", "想看"]
    inventory_keywords = ["盘点", "统计", "多少书", "馆藏", "书库报告"]

    for kw in add_keywords:
        if kw in lower:
            return {"route_type": "workflow", "route_target": "新书入库"}
    for kw in recommend_keywords:
        if kw in lower:
            return {"route_type": "workflow", "route_target": "智能推荐"}
    for kw in inventory_keywords:
        if kw in lower:
            return {"route_type": "workflow", "route_target": "书籍盘点"}

    # Skill 关键词匹配
    if skill_keywords:
        for kw, skill_modname in skill_keywords.items():
            if kw in lower:
                if skill_specialists:
                    matching_keys = list(skill_specialists.keys())
                    if matching_keys:
                        return {"route_type": "specialists", "route_target": matching_keys}
                return {"route_type": "specialists", "route_target": ["general"]}

    # LLM 兜底
    if llm:
        _emit("thinking", {"message": "关键词未命中，正在调用 LLM 分析意图..."}, config)
        try:
            wf_desc = "\n".join(f"- {name}: {wf['description']}" for name, wf in (workflow_defs or {}).items())
            spec_desc = "\n".join(
                f"- {key}: {spec['name']}（{spec.get('system_prompt', '')[:30]}...）"
                for key, spec in (specialist_defs or {}).items()
            )

            prompt = (
                f"根据用户输入，判断应该走工作流还是专家协作。\n\n"
                f"可用工作流：\n{wf_desc}\n\n"
                f"可用专家：\n{spec_desc}\n\n"
                f"用户输入：{user_input}\n\n"
                f'如果是上架新书、入库、盘点、推荐等结构化流程，走工作流，返回 {{"type": "workflow", "target": "工作流名称"}}\n'
                f'否则走专家协作，返回 {{"type": "specialists", "target": ["专家key列表"]}}\n'
                f"只返回 JSON，不要其他内容。"
            )
            resp = llm.invoke([HumanMessage(content=prompt)], config={"temperature": 0})
            text = resp.content.strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(text[start:end])
                if isinstance(result, dict):
                    return {
                        "route_type": result.get("type", "specialists"),
                        "route_target": result.get("target", ["general"]),
                    }
        except Exception:
            pass

    return {"route_type": "specialists", "route_target": ["general"]}


def specialist_chain(state: dict, config: RunnableConfig, *,
                     specialist_agents: dict = None,
                     long_term_memory: list = None) -> dict:
    """专家链：顺序调用专家，上一个的输出传给下一个"""
    specialist_keys = state.get("route_target", ["general"])
    if isinstance(specialist_keys, str):
        specialist_keys = [specialist_keys]

    # 过滤有效专家
    valid_keys = [k for k in specialist_keys if k in (specialist_agents or {})]
    if not valid_keys:
        valid_keys = ["general"]

    names = [specialist_agents[k]["name"] for k in valid_keys]
    _emit("route", {"message": f"调度方案：{' → '.join(names)}"}, config)

    context = state.get("user_input", "")
    user_input = state.get("user_input", "")

    # 注入记忆
    memory_text = ""
    if long_term_memory:
        memory_text = "\n\n你记住的关于用户的信息：\n" + "\n".join(f"  - {m}" for m in long_term_memory[:10])

    for i, key in enumerate(valid_keys):
        is_last = (i == len(valid_keys) - 1)
        spec = specialist_agents[key]
        agent = spec["agent"]

        _emit("specialist", {"message": f"[{spec['name']}] 开始工作..."}, config)

        task = context
        if key == "recommender" and len(valid_keys) > 1:
            task = (
                f"用户需求：{user_input}\n\n"
                f"以下是检索员提供的候选书目：\n{context}\n\n"
                f"请基于以上信息，给用户做个性化推荐。"
            )

        if memory_text:
            task += memory_text

        result = agent.invoke(
            {"messages": [HumanMessage(content=task)]},
        )
        # 提取最后一条 AI 消息
        last_msg = result["messages"][-1]
        context = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        _emit("specialist", {"message": f"[{spec['name']}] 完成"}, config)

    return {"final_reply": context, "specialist_context": context}


def output_guard(state: dict, config: RunnableConfig) -> dict:
    """输出护栏：脱敏敏感信息，并将最终回复作为 token 事件推送"""
    reply = state.get("final_reply", "")
    if reply:
        reply = guard_output(reply)
        # 快捷回复已经在 quick_reply 节点发过 token，跳过
        if not state.get("quick_reply"):
            _emit("token", {"text": reply}, config)
    return {"final_reply": reply}


def memory_update(state: dict, config: RunnableConfig, *,
                  llm=None, long_term_memory: list = None,
                  rag_store=None) -> dict:
    """异步提取记忆"""
    reply = state.get("final_reply", "")
    user_input = state.get("user_input", "")

    if reply and user_input and llm and long_term_memory is not None:
        update_memory_async(llm, user_input, reply, long_term_memory, rag_store)

    return {}


# ============================================================
# 条件边函数
# ============================================================

def after_input_guard(state: dict) -> str:
    if state.get("input_blocked"):
        return "output_guard"
    return "quick_reply"


def after_quick_reply(state: dict) -> str:
    if state.get("quick_reply") is not None:
        return "output_guard"
    return "classify_intent"


def after_classify(state: dict) -> str:
    route_type = state.get("route_type", "specialists")
    if route_type == "workflow":
        return "workflow_router"
    if route_type == "quick_reply":
        return "output_guard"
    return "specialist_chain"


# ============================================================
# 书籍信息提取（工作流用）
# ============================================================

def extract_book_info(user_input: str, llm=None) -> dict:
    """从用户输入提取书籍信息"""
    title = ""
    title_match = re.search(r"《(.+?)》", user_input)
    if title_match:
        title = title_match.group(1)
    else:
        title_match2 = re.search(r"书名[是为：:]\s*(.+?)(?:，|,|作者|分类|日期|$)", user_input)
        if title_match2:
            title = title_match2.group(1).strip()

    author = ""
    author_match = re.search(r"作者[是为：:]?\s*(.+?)(?:，|,|分类|日期|$)", user_input)
    if author_match:
        author = author_match.group(1).strip()

    publish_date = ""
    date_match = re.search(r"(\d{4})\s*年\s*(\d{1,2})?\s*月?", user_input)
    if date_match:
        month = date_match.group(2) or "01"
        publish_date = f"{date_match.group(1)}-{int(month):02d}-01"
    else:
        date_match2 = re.search(r"(\d{4})-(\d{2})", user_input)
        if date_match2:
            publish_date = f"{date_match2.group(1)}-{date_match2.group(2)}-01"

    category = ""
    cat_match = re.search(r"分类[是为：:]\s*(.+?)(?:，|,|$)", user_input)
    if cat_match:
        category = cat_match.group(1).strip()

    if title:
        return {"title": title, "author": author, "publish_date": publish_date, "category": category}

    # LLM 兜底
    if llm:
        prompt = (
            f"从用户输入中提取书籍信息，返回 JSON：\n"
            f'{{"title": "书名", "author": "作者", "publish_date": "出版日期"}}\n'
            f"缺少的字段填空字符串。\n\n"
            f"用户输入：{user_input}\n\n"
            f"只返回 JSON，不要其他内容。"
        )
        try:
            resp = llm.invoke([HumanMessage(content=prompt)], config={"temperature": 0})
            text = resp.content.strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(text[start:end])
                if isinstance(result, dict):
                    return result
        except Exception:
            pass

    return {}
