"""长期记忆：JSON 文件持久化 + LLM 提取"""

import json
import os
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(BASE_DIR, "agent_memory.json")


def load_memory() -> list:
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_memory(memories: list):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)


def extract_memories_sync(llm, user_input: str, assistant_reply: str) -> list:
    """同步提取长期记忆"""
    from langchain_core.messages import HumanMessage

    prompt = (
        f"从以下对话中提取值得长期记住的用户信息（偏好、事实等），返回 JSON 数组。\n"
        f"如果没有值得记住的信息，返回空数组 []。\n\n"
        f"用户：{user_input}\n助手：{assistant_reply}\n\n"
        f"只返回 JSON 数组，不要其他内容。"
    )
    try:
        resp = llm.invoke([HumanMessage(content=prompt)], config={"temperature": 0})
        text = resp.content.strip()
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            result = json.loads(text[start:end])
            if isinstance(result, list):
                return [str(m) if not isinstance(m, str) else m for m in result]
    except Exception:
        pass
    return []


def update_memory_async(llm, user_input: str, assistant_reply: str,
                        current_memory: list, rag_store=None):
    """异步提取记忆并持久化，不阻塞主流程"""
    def _worker():
        try:
            new_memories = extract_memories_sync(llm, user_input, assistant_reply)
            if new_memories:
                current_memory.extend(new_memories)
                current_memory[:] = list(dict.fromkeys(current_memory))
                save_memory(current_memory)
                if rag_store and hasattr(rag_store, 'add_memories'):
                    rag_store.add_memories(new_memories)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()
