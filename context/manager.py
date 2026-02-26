"""
Context Manager - 上下文构建与 Token 优化

核心职责：
- 为每个 Agent 构建最小化上下文
- 工具结果智能摘要（替代粗暴截断）
- 步骤间上下文传递（不累积完整历史）
"""

from ..parsers.result_parser import summarize_tool_result
from .prompts import AgentPrompts


class ContextManager:

    def __init__(self):
        self._step_results: list[dict] = []

    def build_router_context(self, user_message: str) -> list[dict]:
        return [{"role": "user", "content": user_message}]

    def build_planner_context(self, user_message: str, scene_summary: str = "") -> list[dict]:
        content = user_message
        if scene_summary:
            content = f"当前场景: {scene_summary}\n\n用户需求: {user_message}"
        return [{"role": "user", "content": content}]

    def build_executor_context(
        self,
        step_description: str,
        step_params: dict,
        prev_step_summary: str = "",
        user_message: str = "",
    ) -> list[dict]:
        parts = []
        if user_message:
            parts.append(f"用户原始需求: {user_message}")
        if prev_step_summary:
            parts.append(f"上一步结果: {prev_step_summary}")
        parts.append(f"当前任务: {step_description}")
        if step_params:
            import json
            parts.append(f"参考参数: {json.dumps(step_params, ensure_ascii=False)}")

        return [{"role": "user", "content": "\n\n".join(parts)}]

    def build_simple_executor_context(self, user_message: str) -> list[dict]:
        return [{"role": "user", "content": user_message}]

    def build_validator_context(
        self,
        original_request: str,
        steps_summary: list[str],
    ) -> list[dict]:
        content = (
            f"用户需求: {original_request}\n\n"
            f"执行步骤:\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps_summary))
        )
        return [{"role": "user", "content": content}]

    def record_step_result(self, tool_name: str, result: dict):
        summary = summarize_tool_result(tool_name, result)
        self._step_results.append({
            "tool": tool_name,
            "success": result.get("success", False),
            "summary": summary,
        })

    def get_last_step_summary(self) -> str:
        if not self._step_results:
            return ""
        last = self._step_results[-1]
        status = "OK" if last["success"] else "FAIL"
        return f"[{status}] {last['tool']}: {last['summary']}"

    def get_all_steps_summary(self) -> list[str]:
        return [
            f"[{'OK' if r['success'] else 'FAIL'}] {r['tool']}: {r['summary']}"
            for r in self._step_results
        ]

    def reset(self):
        self._step_results.clear()
