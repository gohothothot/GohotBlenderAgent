"""
LLM Provider 基础抽象

定义统一的 LLM 调用接口、响应格式、配置结构。
所有 Provider 实现此接口，上层 Agent 只依赖抽象。
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolCall:
    """LLM 返回的工具调用"""
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """统一的 LLM 响应格式"""
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = ""  # "end_turn" | "tool_use" | "max_tokens"
    usage: dict = field(default_factory=dict)  # {"input_tokens": N, "output_tokens": N}
    raw: dict = field(default_factory=dict)  # 原始响应，调试用

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


@dataclass
class LLMConfig:
    """LLM 连接配置"""
    api_base: str = ""
    api_key: str = ""
    model: str = ""
    max_tokens: int = 4096
    timeout: int = 120

    # Provider 类型自动检测或手动指定
    # "anthropic" | "openai" | "auto"
    provider_type: str = "auto"

    def detect_provider(self) -> str:
        """根据 api_base 自动检测 provider 类型"""
        if self.provider_type != "auto":
            return self.provider_type

        base = self.api_base.lower()
        if "anthropic" in base:
            return "anthropic"
        if "openai" in base:
            return "openai"

        # 根据模型名猜测
        model = self.model.lower()
        if "claude" in model:
            return "anthropic"
        if "gpt" in model or "codex" in model:
            return "openai"

        # 默认用 OpenAI 兼容格式（大多数中转 API 兼容）
        return "openai"


class LLMProvider(ABC):
    """LLM Provider 统一接口"""

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
    ) -> LLMResponse:
        """
        发送对话请求

        Args:
            messages: [{"role": "user"|"assistant"|"tool", "content": ...}]
            system: system prompt（独立传递，不混入 messages）
            tools: 工具定义列表（Provider 自行转换格式）
            tool_choice: "auto" | "any" | "none"

        Returns:
            LLMResponse
        """
        ...

    @abstractmethod
    def format_tool_result(self, tool_call_id: str, result: str, is_error: bool = False) -> dict:
        """
        格式化工具执行结果为 Provider 特定的消息格式

        不同 Provider 的 tool result 格式不同：
        - Anthropic: {"type": "tool_result", "tool_use_id": ..., "content": ...}
        - OpenAI: {"role": "tool", "tool_call_id": ..., "content": ...}
        """
        ...

    @abstractmethod
    def format_assistant_with_tool_calls(self, response: LLMResponse) -> dict:
        """
        将包含 tool_calls 的 LLM 响应格式化为 assistant 消息

        用于构建后续对话时，需要把 assistant 的 tool_use 响应放回 messages。
        """
        ...

    def format_tool_results_as_messages(self, tool_results: list[dict]) -> list[dict]:
        """
        将 format_tool_result 返回的列表包装为可追加到 messages 的消息。

        Anthropic: 包装为 {"role": "user", "content": [...]}
        OpenAI: 每个 tool result 是独立的 {"role": "tool", ...} 消息
        """
        # 默认实现：每个 result 作为独立消息（OpenAI 风格）
        return tool_results
