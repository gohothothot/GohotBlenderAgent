"""
Planner Agent - 任务分解

将复杂用户需求分解为结构化的工具调用步骤。
只在 complexity=complex 时激活。
"""

from ..llm.base import LLMProvider
from ..parsers.plan_parser import ExecutionPlan, parse_plan
from ..context.prompts import AgentPrompts
from ..context.manager import ContextManager
from ..tools.registry import get_registry


class PlannerAgent:

    def __init__(self, llm: LLMProvider):
        self._llm = llm

    def plan(self, user_message: str, intent: str, scene_summary: str = "") -> ExecutionPlan:
        registry = get_registry()
        relevant_tools = registry.get_for_intent(intent)
        tools_summary = registry.get_summaries(relevant_tools)

        system = AgentPrompts.get_planner_prompt(tools_summary)
        ctx = ContextManager()
        messages = ctx.build_planner_context(user_message, scene_summary)

        try:
            response = self._llm.chat(messages=messages, system=system)
            plan = parse_plan(response.text)

            if not plan.summary:
                plan.summary = user_message[:100]

            return plan

        except Exception as e:
            return ExecutionPlan(
                summary=f"规划失败: {e}",
                steps=[],
            )
