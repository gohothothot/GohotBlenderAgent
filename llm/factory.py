"""
LLM Provider 工厂

根据配置自动创建对应的 Provider 实例。
"""

from .base import LLMProvider, LLMConfig


def create_provider(config: LLMConfig) -> LLMProvider:
    """根据配置创建 LLM Provider"""
    provider_type = config.detect_provider()

    if provider_type == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(config)
    else:
        # OpenAI 兼容格式（包括中转 API）
        from .openai_provider import OpenAIProvider
        return OpenAIProvider(config)
