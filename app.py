"""FastAPI + LangServe 入口（替换原 Flask app.py）

- LangServe 标准路由 /graph/invoke, /graph/stream
- 自定义 /stream SSE 端点（兼容现有前端事件格式）
- /confirm 端点（interrupt 恢复）
- CRUD 端点 /memory, /books, /history, /workflows, /skills, /trace
"""

import json
import os
import queue
import threading
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from langserve import add_routes
from langgraph.types import Command

# Workaround: langchain-core 0.3.86 _StreamingCallbackHandler 继承 Protocol 导致
# _AstreamEventsCallbackHandler.__init__ 的 super().__init__() 触发
# "Protocols cannot be instantiated"
from langchain_core.tracers.event_stream import _StreamingCallbackHandler
_StreamingCallbackHandler.__init__ = lambda self, *args, **kwargs: None

from graph import get_graph
from memory import load_memory, save_memory
from tools.core import _load_books
from callbacks import tracer

app = FastAPI(title="智能图书助手")

# 静态文件和模板
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# 初始化图
compiled_graph, app_context = get_graph()

# LangServe 标准路由
add_routes(app, compiled_graph, path="/graph")

# 对话历史持久化
CHAT_HISTORY_FILE = os.path.join(BASE_DIR, "chat_history.json")
chat_histories: dict = {}


def _load_chat_histories() -> dict:
    if not os.path.exists(CHAT_HISTORY_FILE):
        return {}
    try:
        with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        migrated = {}
        for sid, val in raw.items():
            if isinstance(val, list):
                title = ""
                for msg in val:
                    if msg.get("role") == "user":
                        title = msg["content"][:20]
                        break
                migrated[sid] = {"title": title, "updated_at": 0, "messages": val}
            else:
                migrated[sid] = val
        return migrated
    except Exception:
        return {}


def _save_chat_histories():
    try:
        with open(CHAT_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(chat_histories, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


chat_histories = _load_chat_histories()
MAX_HISTORY_TURNS = 10


# ============================================================
# 页面路由
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ============================================================
# 自定义 SSE 流式端点（兼容现有前端）
# ============================================================

@app.post("/stream")
async def stream_chat(request: Request):
    data = await request.json()
    user_input = data.get("message", "").strip()
    if not user_input:
        return {"error": "消息不能为空"}

    browser_session = data.get("session_id", "")
    if not browser_session:
        browser_session = str(uuid.uuid4())

    session_id = browser_session

    async def event_generator():
        final_text = ""
        try:
            # 发送 reply_start 事件，前端据此创建流式气泡
            yield f"event: reply_start\ndata: {json.dumps({})}\n\n"

            # 使用 astream_events 获取流式输出
            async for event in compiled_graph.astream_events(
                {
                    "user_input": user_input,
                    "messages": [],
                    "session_id": session_id,
                    "workflow_context": {},
                    "specialist_keys": [],
                    "specialist_context": "",
                    "final_reply": "",
                    "input_blocked": False,
                    "block_reason": "",
                    "quick_reply": None,
                },
                config={"configurable": {"thread_id": session_id}},
                version="v2",
            ):
                kind = event["event"]

                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    content = chunk.content if hasattr(chunk, "content") else str(chunk)
                    if content:
                        final_text += content
                        yield f"event: token\ndata: {json.dumps({'text': content}, ensure_ascii=False)}\n\n"

                elif kind == "on_custom_event":
                    event_name = event["name"]
                    event_data = event["data"]
                    if event_name == "token":
                        final_text += event_data.get("text", "")
                    yield f"event: {event_name}\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"

            # 保存对话历史
            session_data = chat_histories.get(browser_session, {})
            history = session_data.get("messages", [])
            history.append({"role": "user", "content": user_input})
            if final_text:
                history.append({"role": "assistant", "content": final_text})
            # 获取最终回复
            title = session_data.get("title", "")
            if not title:
                for msg in history:
                    if msg.get("role") == "user":
                        title = msg["content"][:20]
                        break
            chat_histories[browser_session] = {
                "title": title,
                "updated_at": time.time(),
                "messages": history[-MAX_HISTORY_TURNS * 2:],
            }
            _save_chat_histories()

            # 追踪摘要
            trace_summary = {}
            if tracer.history:
                last = tracer.history[-1]
                trace_summary = {
                    "total_ms": last.total_duration_ms,
                    "total_tokens": last.total_tokens,
                    "spans": [
                        {"name": s.name, "duration_ms": s.duration_ms,
                         "token_in": s.token_in, "token_out": s.token_out, "status": s.status}
                        for s in last.spans
                    ],
                }

            yield f"event: done\ndata: {json.dumps({'trace': trace_summary}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ============================================================
# 确认端点（interrupt 恢复）
# ============================================================

@app.post("/confirm")
async def handle_confirm(request: Request):
    data = await request.json()
    session_id = data.get("session_id", "")
    confirmed = data.get("confirmed", False)
    modifications = data.get("modifications", {})

    # 恢复被 interrupt 暂停的图
    result = compiled_graph.invoke(
        Command(resume={"confirmed": confirmed, "modifications": modifications}),
        config={"configurable": {"thread_id": session_id}},
    )
    return {"status": "ok", "result": result.get("final_reply", "")}


# ============================================================
# 非流式聊天端点
# ============================================================

@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    user_input = data.get("message", "").strip()
    if not user_input:
        return {"error": "消息不能为空"}

    session_id = data.get("session_id", str(uuid.uuid4()))

    result = compiled_graph.invoke(
        {
            "user_input": user_input,
            "messages": [],
            "session_id": session_id,
            "workflow_context": {},
            "specialist_keys": [],
            "specialist_context": "",
            "final_reply": "",
            "input_blocked": False,
            "block_reason": "",
            "quick_reply": None,
        },
        config={"configurable": {"thread_id": session_id}},
    )

    reply = result.get("final_reply", "")
    return {"reply": reply, "session_id": session_id}


# ============================================================
# CRUD 端点
# ============================================================

@app.get("/memory")
async def get_memory():
    return {"memories": load_memory()}


@app.delete("/memory")
async def clear_memory():
    app_context["long_term_memory"][:] = []
    save_memory([])
    return {"status": "ok"}


@app.get("/books")
async def get_books():
    return {"books": _load_books()}


@app.get("/history")
async def list_chat_histories():
    sessions = []
    for sid, data in chat_histories.items():
        if isinstance(data, dict):
            sessions.append({
                "id": sid,
                "title": data.get("title", "未命名对话"),
                "updated_at": data.get("updated_at", 0),
                "message_count": len(data.get("messages", [])),
            })
    sessions.sort(key=lambda x: x["updated_at"], reverse=True)
    return {"sessions": sessions}


@app.get("/history/{session_id}")
async def get_chat_history(session_id: str):
    session_data = chat_histories.get(session_id, {})
    messages = session_data.get("messages", []) if isinstance(session_data, dict) else session_data
    return {"messages": messages}


@app.delete("/history/{session_id}")
async def clear_chat_history(session_id: str):
    chat_histories.pop(session_id, None)
    _save_chat_histories()
    return {"status": "ok"}


@app.get("/workflows")
async def get_workflows():
    result = {}
    for name, wf in app_context["workflow_defs"].items():
        result[name] = {"description": wf["description"]}
    return {"workflows": result}


@app.get("/skills")
async def get_skills():
    from specialists import load_skill_specialists
    skill_specs, _ = load_skill_specialists()

    installed = []
    for key, spec in skill_specs.items():
        installed.append({
            "id": key,
            "name": spec["name"],
            "tools": spec["tools"],
        })
    return {"installed": installed}


@app.get("/trace")
async def get_trace():
    history = []
    for t in tracer.history[-10:]:
        history.append({
            "input": t.user_input[:50],
            "total_ms": t.total_duration_ms,
            "total_tokens": t.total_tokens,
            "spans": [
                {"name": s.name, "duration_ms": s.duration_ms,
                 "token_in": s.token_in, "token_out": s.token_out, "status": s.status}
                for s in t.spans
            ],
        })
    return {"history": history}


if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("📚 智能图书助手 Web UI (FastAPI + LangServe)")
    print("打开浏览器访问: http://localhost:8000")
    print("按 Ctrl+C 停止服务")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
