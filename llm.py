"""LLM 工厂：统一创建 ChatOpenAI 实例

DeepSeek 的 thinking 模型（deepseek-v4-pro）返回 reasoning_content，
ChatOpenAI 不支持回传 reasoning_content，多轮工具调用会报 400 错误。
默认使用 deepseek-chat（非 thinking 模型）。如需 thinking 模型，
可通过环境变量 MODEL_NAME=deepseek-reasoner 切换。
"""

import os

from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv(override=True)

DEFAULT_MODEL = "deepseek-chat"


def create_llm(model: str = None, streaming: bool = True, temperature: float = 0.7) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=os.environ.get("OPENAI_BASE_URL"),
        api_key=os.environ.get("OPENAI_API_KEY"),
        model=model or os.environ.get("MODEL_NAME", DEFAULT_MODEL),
        streaming=streaming,
        temperature=temperature,
    )
