"""
Router Agent - 意图分类

默认使用规则引擎（零 LLM 调用），可选 LLM 增强。
"""

from ..parsers.route_parser import RouteDecision, parse_route, parse_route_from_llm
from ..llm.base import LLMProvider, LLMConfig
from ..context.prompts import AgentPrompts


class RouterAgent:

    def __init__(self, llm: LLMProvider = None, use_llm: bool = False):
        self._llm = llm
        self._use_llm = use_llm and llm is not None

    def route(self, user_message: str) -> RouteDecision:
        if self._use_llm:
            return self._route_with_llm(user_message)
        return parse_route(user_message)

    def _route_with_llm(self, user_message: str) -> RouteDecision:
        try:
            response = self._llm.chat(
                messages=[{"role": "user", "content": user_message}],
                system=AgentPrompts.ROUTER,
            )
            return parse_route_from_llm(response.text)
        except Exception:
            return parse_route(user_message)
