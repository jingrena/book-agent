"""工具注册：动态收集所有 @tool 定义"""

import importlib
import os
import pkgutil

from langchain_core.tools import BaseTool

from tools.core import CORE_TOOLS
from tools.rag import RAG_TOOLS
from tools.borrow import BORROW_TOOLS


def _load_skill_tools(skills_dir: str = None) -> list:
    """动态加载 skills/ 目录下所有 @tool 函数"""
    if skills_dir is None:
        skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")

    tools = []
    if not os.path.exists(skills_dir):
        return tools

    for importer, modname, _ in pkgutil.iter_modules([skills_dir]):
        try:
            module = importlib.import_module(f"skills.{modname}")
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, BaseTool):
                    tools.append(attr)
        except Exception as e:
            print(f"  ⚠️ 加载 Skill '{modname}' 工具失败：{e}")

    return tools


def get_all_tools() -> list:
    """获取所有可用工具（核心 + RAG + Skills）"""
    tools = list(CORE_TOOLS) + list(RAG_TOOLS) + list(BORROW_TOOLS) + _load_skill_tools()
    return tools


def get_tools_by_name(tool_names: list) -> list:
    """按名称筛选工具"""
    all_tools = get_all_tools()
    name_map = {t.name: t for t in all_tools}
    return [name_map[n] for n in tool_names if n in name_map]


def get_tool_map() -> dict:
    """获取 {name: tool} 映射"""
    all_tools = get_all_tools()
    return {t.name: t for t in all_tools}
