"""
Executor Agent - 工具执行

每步只看到相关工具子集，独立上下文，不累积历史。
支持两种模式：
1. 有计划模式：按 PlanStep 逐步执行
2. 直接模式：简单任务直接让 LLM 调用工具
"""

import json
from ..llm.base import LLMProvider, LLMResponse
from ..parsers.plan_parser import PlanStep
from ..parsers.result_parser import summarize_tool_result
from ..context.prompts import AgentPrompts
from ..context.manager import ContextManager
from ..tools.registry import get_registry


def _log(msg: str):
    print(f"[Executor] {msg}")


class ExecutorAgent:

    def __init__(self, llm: LLMProvider, execute_in_main_thread=None):
        self._llm = llm
        self._execute_in_main_thread = execute_in_main_thread

    def execute_step(
        self,
        step: PlanStep,
        domain: str,
        prev_summary: str = "",
        user_message: str = "",
    ) -> dict:
        if step.tool and step.params:
            _log(f"execute_direct: tool={step.tool}")
            return self._execute_direct(step)

        _log(f"execute_with_llm: step={step.step}, desc={step.description[:60] if step.description else 'N/A'}")
        return self._execute_with_llm(step, domain, prev_summary, user_message)

    def execute_simple(self, user_message: str, domain: str, intent: str) -> dict:
        registry = get_registry()
        tools = registry.get_for_intent(intent)
        tool_schemas = registry.get_schemas(tools)
        _log(f"execute_simple: domain={domain}, intent={intent}, tools_count={len(tools)}, registry_total={registry.count}")

        system = AgentPrompts.get_executor_prompt(domain)
        # 强化工具使用指令（与旧 BlenderAgent 一致）
        preflight = "[系统提醒] 你是 Blender 操作者，必须使用提供的工具执行操作。禁止纯文字回复，立即调用工具。\n\n"
        messages = [{"role": "user", "content": preflight + user_message}]

        # 如果意图筛选后工具为空，回退到全部工具
        if not tools and registry.count > 0:
            _log(f"WARNING: intent '{intent}' returned 0 tools, falling back to ALL {registry.count} tools")
            tools = registry.get_all()
            tool_schemas = registry.get_schemas(tools)
        
        if not tool_schemas:
            _log("CRITICAL: Registry empty! Trying direct import fallback...")
            try:
                from .. import tool_definitions
                tool_schemas = tool_definitions.TOOLS  # 直接用原始 TOOLS 列表（已是 Anthropic 格式）
                _log(f"Direct import fallback: {len(tool_schemas)} tools loaded")
            except Exception as e:
                _log(f"Direct import also failed: {e}")
        return self._llm_tool_loop(messages, system, tool_schemas, max_rounds=5)

    def _execute_direct(self, step: PlanStep) -> dict:
        result = self._run_tool(step.tool, step.params)
        step.status = "success" if result.get("success") else "failed"
        step.result = result
        step.error = result.get("error", "")
        return result

    def _execute_with_llm(
        self, step: PlanStep, domain: str,
        prev_summary: str, user_message: str,
    ) -> dict:
        registry = get_registry()
        intent_groups = {
            "shader": "shader_complex",
            "scene": "modify",
            "animation": "animation",
            "toon": "toon",
        }
        intent = intent_groups.get(domain, "general")
        tools = registry.get_for_intent(intent)
        tool_schemas = registry.get_schemas(tools)

        system = AgentPrompts.get_executor_prompt(domain)
        ctx = ContextManager()
        messages = ctx.build_executor_context(
            step.description, step.params, prev_summary, user_message,
        )

        result = self._llm_tool_loop(messages, system, tool_schemas, max_rounds=3)
        step.status = "success" if result.get("success") else "failed"
        step.result = result
        return result

    def _llm_tool_loop(
        self,
        messages: list,
        system: str,
        tool_schemas: list,
        max_rounds: int = 5,
    ) -> dict:
        all_results = []
        final_text = ""

        for round_i in range(max_rounds):
            _log(f"LLM call round {round_i + 1}/{max_rounds}, msgs={len(messages)}, tools={len(tool_schemas)}")
            try:
                response = self._llm.chat(
                    messages=messages, system=system, tools=tool_schemas if tool_schemas else None,
                )
            except Exception as e:
                _log(f"LLM call failed: {type(e).__name__}: {e}")
                return {
                    "success": False,
                    "result": None,
                    "tool_results": all_results,
                    "error": f"LLM 调用失败: {e}",
                }

            _log(f"LLM response: text_len={len(response.text)}, tool_calls={len(response.tool_calls)}, stop={response.stop_reason}")

            if response.text:
                final_text = response.text

            if not response.has_tool_calls:
                break

            assistant_msg = self._llm.format_assistant_with_tool_calls(response)
            messages.append(assistant_msg)

            tool_result_msgs = []
            for tc in response.tool_calls:
                _log(f"Running tool: {tc.name}({list(tc.arguments.keys()) if tc.arguments else []})")
                result = self._run_tool(tc.name, tc.arguments)
                _log(f"Tool result: {tc.name} → success={result.get('success')}")
                all_results.append({"tool": tc.name, "result": result})

                summary = summarize_tool_result(tc.name, result, max_chars=2000)

                tool_msg = self._llm.format_tool_result(
                    tc.id, summary, is_error=not result.get("success"),
                )
                tool_result_msgs.append(tool_msg)

            messages.extend(self._llm.format_tool_results_as_messages(tool_result_msgs))

        last_success = all(r["result"].get("success", False) for r in all_results) if all_results else True
        return {
            "success": last_success,
            "result": final_text or "执行完成",
            "tool_results": all_results,
            "error": None if last_success else "部分工具执行失败",
        }

    def _run_tool(self, name: str, arguments: dict) -> dict:
        registry = get_registry()
        # 先尝试通过 registry 执行
        if registry.count > 0:
            if self._execute_in_main_thread:
                return self._execute_in_main_thread(registry.execute, name, arguments)
            return registry.execute(name, arguments)
        # 回退：直接调用 tool_definitions.execute_tool
        _log(f"_run_tool fallback: {name}")
        try:
            from .. import tool_definitions
            if self._execute_in_main_thread:
                return self._execute_in_main_thread(tool_definitions.execute_tool, name, arguments)
            return tool_definitions.execute_tool(name, arguments)
        except Exception as e:
            return {"success": False, "result": None, "error": f"工具执行失败: {e}"}
