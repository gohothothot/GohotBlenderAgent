"""
上下文管理层

控制每个 Agent 看到的上下文，优化 token 消耗。
"""

from .manager import ContextManager
from .prompts import AgentPrompts

__all__ = ["ContextManager", "AgentPrompts"]
