"""
Orchestrator - Agent 编排器

协调 Router → Planner → Executor → Validator 的完整流程。
这是多 Agent 系统的入口点，替代原来的 BlenderAgent。
"""

import threading
import traceback
from typing import Callable, Optional

from ..llm.base import LLMConfig
from ..llm.factory import create_provider
from ..context.manager import ContextManager
from .router import RouterAgent
from .planner import PlannerAgent
from .executor import ExecutorAgent
from .validator import ValidatorAgent


def _log(msg: str):
    print(f"[Orchestrator] {msg}")


class AgentOrchestrator:

    def __init__(
        self,
        config: LLMConfig,
        execute_in_main_thread: Callable = None,
    ):
        self._config = config
        self._execute_in_main_thread = execute_in_main_thread

        provider = create_provider(config)
        self._router = RouterAgent(llm=provider, use_llm=False)
        self._planner = PlannerAgent(llm=provider)
        self._executor = ExecutorAgent(llm=provider, execute_in_main_thread=execute_in_main_thread)
        self._validator = ValidatorAgent(llm=None)
        self._context = ContextManager()

        self.on_message: Optional[Callable[[str, str], None]] = None
        self.on_tool_call: Optional[Callable[[str, dict], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_plan: Optional[Callable[[str], None]] = None

    def send_message(self, user_message: str):
        thread = threading.Thread(target=self._process, args=(user_message,))
        thread.daemon = True
        thread.start()

    def _process(self, user_message: str):
        try:
            from .. import action_log
            action_log.start_session(user_message)
            action_log.log_agent_message("user", user_message)
        except Exception:
            pass

        try:
            self._context.reset()

            _log(f"Routing: {user_message[:60]}...")
            route = self._router.route(user_message)
            _log(f"Route result: intent={route.intent}, domain={route.domain}, complexity={route.complexity}")

            if route.is_complex:
                _log("→ _process_complex")
                self._process_complex(user_message, route)
            else:
                _log("→ _process_simple")
                self._process_simple(user_message, route)

            _log("Processing complete.")

        except Exception as e:
            tb = traceback.format_exc()
            error_msg = f"{type(e).__name__}: {e}"
            _log(f"FATAL ERROR:\n{tb}")
            # 尝试回退到纯文本 LLM 调用
            try:
                _log("Attempting fallback (no tools)...")
                response = self._executor._llm.chat(
                    messages=[{"role": "user", "content": user_message}],
                    system="你是 Blender AI 助手。简洁中文回复。",
                )
                if response.text:
                    self._emit_message("assistant", response.text)
                    _log("Fallback succeeded.")
                    return
            except Exception as fallback_err:
                _log(f"Fallback also failed: {fallback_err}")
            self._emit_error(error_msg)
            try:
                from .. import action_log
                action_log.log_error("orchestrator", f"{error_msg}\n{tb}")
                action_log.end_session(f"错误: {error_msg}")
            except Exception:
                pass

    def _process_simple(self, user_message: str, route):
        _log(f"execute_simple: domain={route.domain}, intent={route.intent}")
        result = self._executor.execute_simple(
            user_message, route.domain, route.intent,
        )
        _log(f"execute_simple done: success={result.get('success')}, result_len={len(str(result.get('result', '')))}")

        if result.get("result"):
            self._emit_message("assistant", result["result"])

        self._end_session(result.get("result", ""))

    def _process_complex(self, user_message: str, route):
        _log(f"Planning: intent={route.intent}")
        plan = self._planner.plan(user_message, route.intent)
        _log(f"Plan result: {plan.total_steps} steps, summary={plan.summary[:80] if plan.summary else 'N/A'}")

        if not plan.steps:
            _log("Empty plan, falling back to simple")
            self._emit_message("assistant", "无法分解任务，尝试直接执行...")
            self._process_simple(user_message, route)
            return

        if self.on_plan:
            steps_preview = "\n".join(
                f"  {s.step}. {s.description or s.tool}" for s in plan.steps
            )
            self._fire_callback(self.on_plan, f"执行计划 ({plan.total_steps} 步):\n{steps_preview}")

        prev_summary = ""
        while True:
            next_step = plan.get_next_step()
            if next_step is None:
                break

            _log(f"Step {next_step.step}: tool={next_step.tool}, params_keys={list(next_step.params.keys()) if next_step.params else []}")

            if self.on_tool_call:
                self._fire_callback(self.on_tool_call, next_step.tool, next_step.params)

            result = self._executor.execute_step(
                next_step, route.domain, prev_summary, user_message,
            )
            _log(f"Step {next_step.step} result: success={result.get('success')}")

            self._context.record_step_result(next_step.tool or "unknown", result)
            prev_summary = self._context.get_last_step_summary()

            try:
                from .. import action_log
                action_log.log_tool_call(
                    next_step.tool or "plan_step",
                    next_step.params,
                    result,
                )
            except Exception:
                pass

            validation = self._validator.validate_tool_result(
                next_step.tool or "unknown", result,
            )
            if not validation.passed:
                _log(f"Step {next_step.step} validation failed: {validation.issues}")

        final_validation = self._validator.validate_plan_execution(
            user_message, self._context.get_all_steps_summary(),
        )

        final_text = self._build_final_response(plan, final_validation)
        self._emit_message("assistant", final_text)
        self._end_session(final_text)

    def _build_final_response(self, plan, validation) -> str:
        completed = plan.completed_steps
        total = plan.total_steps
        failed = plan.failed_steps

        if not failed:
            return f"已完成全部 {total} 个步骤。"

        fail_info = "; ".join(f"步骤{s.step}({s.tool}): {s.error}" for s in failed[:3])
        return f"完成 {completed}/{total} 步。失败: {fail_info}"

    def _emit_message(self, role: str, content: str):
        """发送消息到 UI（非阻塞）"""
        if self.on_message:
            self._fire_callback(self.on_message, role, content)
        try:
            from .. import action_log
            action_log.log_agent_message(role, content)
        except Exception:
            pass

    def _emit_error(self, error: str):
        """发送错误到 UI（非阻塞）"""
        if self.on_error:
            self._fire_callback(self.on_error, error)

    def _end_session(self, result: str):
        try:
            from .. import action_log
            action_log.end_session(result[:200])
        except Exception:
            pass

    def _fire_callback(self, callback, *args):
        """
        非阻塞地在 Blender 主线程执行 UI 回调。
        
        关键：不能用 _execute_in_main_thread（会阻塞30秒等待结果），
        必须用 bpy.app.timers.register 做 fire-and-forget。
        """
        try:
            import bpy

            def do_callback():
                try:
                    callback(*args)
                except Exception as e:
                    _log(f"Callback error: {e}")
                return None  # 不重复执行

            bpy.app.timers.register(do_callback)
        except Exception:
            # bpy 不可用时直接调用
            try:
                callback(*args)
            except Exception:
                pass

    def clear_history(self):
        self._context.reset()
