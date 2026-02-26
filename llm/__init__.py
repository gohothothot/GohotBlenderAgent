"""
LLM Provider 抽象层

统一接口支持 Anthropic / OpenAI / 中转API，
让上层 Agent 不关心底层 LLM 差异。
"""

from .base import LLMProvider, LLMResponse, LLMConfig, ToolCall
from .factory import create_provider

__all__ = ["LLMProvider", "LLMResponse", "LLMConfig", "ToolCall", "create_provider"]
