"""自定义回调：事件分发、追踪"""

import time
from dataclasses import dataclass, field
from typing import Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.callbacks.manager import dispatch_custom_event


def emit_event(event_type: str, data: dict):
    """从图节点内发出自定义事件（供 astream_events 捕获）"""
    dispatch_custom_event(event_type, data)


# ============================================================
# 追踪系统（保留原有功能）
# ============================================================

@dataclass
class Span:
    name: str
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: int = 0
    token_in: int = 0
    token_out: int = 0
    status: str = "ok"
    detail: str = ""


@dataclass
class Trace:
    user_input: str
    spans: list = field(default_factory=list)
    start_time: float = 0.0
    total_duration_ms: int = 0

    def add_span(self, name: str) -> Span:
        span = Span(name=name, start_time=time.time())
        self.spans.append(span)
        return span

    def finish(self):
        self.total_duration_ms = int((time.time() - self.start_time) * 1000)

    @property
    def total_tokens(self) -> int:
        return sum(s.token_in + s.token_out for s in self.spans)


class Tracer:
    def __init__(self, max_history: int = 50):
        self.current_trace: Optional[Trace] = None
        self.history: list = []
        self.max_history = max_history

    def start_trace(self, user_input: str) -> Trace:
        trace = Trace(user_input=user_input, start_time=time.time())
        self.current_trace = trace
        return trace

    def end_trace(self):
        if self.current_trace:
            self.current_trace.finish()
            self.history.append(self.current_trace)
            if len(self.history) > self.max_history:
                self.history = self.history[-self.max_history:]
        self.current_trace = None


tracer = Tracer()


# ============================================================
# LLM 回调（用于 Token 流式 + 追踪）
# ============================================================

class StreamingCallbackHandler(BaseCallbackHandler):
    """捕获 LLM token 流和自定义事件"""

    def __init__(self, event_callback=None):
        self._event_callback = event_callback

    def on_llm_new_token(self, token: str, **kwargs):
        if self._event_callback:
            self._event_callback("token", {"text": token})
