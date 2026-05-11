"""状态定义：主图 + 工作流子图"""

from typing import Annotated, List, Literal, Optional, Union

from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class BookAssistantState(TypedDict):
    """主图状态——流经每个节点"""

    messages: Annotated[List[BaseMessage], add_messages]
    user_input: str
    route_type: Optional[Literal["workflow", "specialists", "quick_reply"]]
    route_target: Optional[Union[str, List[str]]]
    workflow_context: dict
    specialist_keys: List[str]
    specialist_context: str
    final_reply: str
    input_blocked: bool
    block_reason: str
    session_id: str
    quick_reply: Optional[str]


class NewBookWorkflowState(TypedDict):
    """新书入库工作流状态"""
    messages: Annotated[List[BaseMessage], add_messages]
    workflow_context: dict
    final_reply: str
    session_id: str


class RecommendWorkflowState(TypedDict):
    """智能推荐工作流状态"""
    messages: Annotated[List[BaseMessage], add_messages]
    workflow_context: dict
    final_reply: str
    session_id: str


class InventoryWorkflowState(TypedDict):
    """书籍盘点工作流状态"""
    messages: Annotated[List[BaseMessage], add_messages]
    workflow_context: dict
    final_reply: str
    session_id: str
