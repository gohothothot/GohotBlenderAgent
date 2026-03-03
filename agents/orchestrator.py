"""
Orchestrator - Agent 编排器

协调 Router → Planner → Executor → Validator 的完整流程。
这是多 Agent 系统的入口点，替代原来的 BlenderAgent。
"""

import threading
import traceback
import time
import json
from typing import Callable, Optional

from ..llm.base import LLMConfig
from ..llm.factory import create_provider
from ..context.manager import ContextManager
from ..context.rag_retriever import retrieve_context, build_rag_prompt_block
from ..core.mini_rewrite import mini_rewrite
from .router import RouterAgent
from .planner import PlannerAgent
from .executor import ExecutorAgent
from .validator import ValidatorAgent
from ..core.runtime_core import RuntimeCoreMixin
from ..core.skill_registry import build_skill_guidance

try:
    from ..backend.core.mini_rewrite import MiniRewriter
    from ..backend.rag.stores import auto_retrieve
    from ..backend.core.context_builder import ContextBuilder, ContextBuildInput
    from ..backend.utils.token_optimizer import CompressionStrategy
    from ..backend.memory.store import get_memory_store
    from ..backend.memory.reflection import ReflectionModule
    _BACKEND_V2_READY = True
except Exception:
    MiniRewriter = None
    auto_retrieve = None
    ContextBuilder = None
    ContextBuildInput = None
    CompressionStrategy = None
    get_memory_store = None
    ReflectionModule = None
    _BACKEND_V2_READY = False


def _log(msg: str):
    print(f"[Orchestrator] {msg}")


class AgentOrchestrator(RuntimeCoreMixin):

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
        self._executor.on_tool_call = self._emit_tool_call
        self._executor.on_plan = self._emit_plan
        self._validator = ValidatorAgent(llm=None)
        self._context = ContextManager()
        self._session_id = f"orch_{int(time.time() * 1000)}"
        self._last_user_message = ""
        self._last_normalized = ""
        self._last_task_type = "general"
        self._last_task_success = False
        self._current_tool_calls = []

        self._mini_rewriter = None
        self._context_builder = None
        self._memory_store = None
        self._reflection = None
        if _BACKEND_V2_READY:
            try:
                self._mini_rewriter = MiniRewriter()
                self._memory_store = get_memory_store() if get_memory_store else None
                self._reflection = ReflectionModule.create(store=self._memory_store) if ReflectionModule and self._memory_store else None
                self._context_builder = ContextBuilder(
                    deep_sleep_callback=self._on_pre_compression_deep_sleep
                ) if ContextBuilder else None
                _log("Backend 2.0 modules enabled in orchestrator.")
            except Exception as e:
                _log(f"Backend 2.0 init failed, fallback to legacy pipeline: {e}")
                self._mini_rewriter = None
                self._context_builder = None
                self._memory_store = None
                self._reflection = None

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
            self._last_user_message = user_message
            self._current_tool_calls = []
            prep = self._prepare_input_context(user_message)
            normalized = prep.get("normalized", user_message)
            extracted_terms = prep.get("extracted_terms", [])
            task_type = prep.get("task_type", "general")
            rag_meta = prep.get("rag_meta", {})
            memory_hits = prep.get("memory_hits", 0)
            enriched_message = prep.get("enriched_message", normalized)
            capability_tool_chain = prep.get("capability_tool_chain", [])
            capability_ids = prep.get("capability_ids", [])
            self._last_normalized = normalized
            self._last_task_type = task_type
            try:
                self._executor.set_grounding_tools(capability_tool_chain)
            except Exception:
                pass

            if self.on_plan:
                self._fire_callback(
                    self.on_plan,
                    (
                        f"[Mini改写] {normalized}\n"
                        f"[RAG命中] glossary={rag_meta.get('glossary_count', 0)}, "
                        f"recipe={rag_meta.get('recipe_count', 0)}, "
                        f"capability={rag_meta.get('capability_count', 0)}\n"
                        f"[Memory命中] {memory_hits}"
                    ),
                )
                if capability_tool_chain:
                    self._fire_callback(
                        self.on_plan,
                        f"__GROUNDING__:{json.dumps({'capabilities': capability_ids, 'tool_chain': capability_tool_chain}, ensure_ascii=False)}",
                    )

            _log(f"Routing: {normalized[:60]}...")
            route = self._router.route(normalized)
            _log(f"Route result: intent={route.intent}, domain={route.domain}, complexity={route.complexity}")

            # Plan 模式兜底：在 orchestrator 层主动做一次 skill 匹配与上报，
            # 避免步骤直接执行时未经过 executor-llm 分支导致 UI 看不到 skill 命中。
            skill_hint = ""
            try:
                skill_hint, matched_skill_ids = build_skill_guidance(
                    query=normalized,
                    intent=route.intent,
                    domain=route.domain,
                    top_k=5,
                )
                if matched_skill_ids and self.on_plan:
                    self._fire_callback(
                        self.on_plan,
                        f"__SKILL_MATCH__:{json.dumps({'skills': matched_skill_ids}, ensure_ascii=False)}",
                    )
            except Exception as e:
                _log(f"orchestrator skill match failed: {e}")

            if skill_hint:
                enriched_message = f"{enriched_message}\n\n{skill_hint}"

            if route.is_complex:
                _log("→ _process_complex")
                self._process_complex(
                    enriched_message,
                    route,
                    raw_user_message=user_message,
                    capability_tool_chain=capability_tool_chain,
                )
            else:
                _log("→ _process_simple")
                self._process_simple(enriched_message, route, raw_user_message=user_message)

            if self._reflection:
                try:
                    self._reflection.on_turn_completed_async(
                        session_id=self._session_id,
                        recent_messages=[
                            {"role": "user", "content": user_message},
                            {"role": "assistant", "content": "turn_completed"},
                        ],
                        llm=self._executor._llm,
                    )
                except Exception:
                    pass

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

    def _process_simple(self, user_message: str, route, raw_user_message: str = ""):
        _log(f"execute_simple: domain={route.domain}, intent={route.intent}")
        result = self._executor.execute_simple(
            user_message, route.domain, route.intent,
        )
        self._current_tool_calls.extend(result.get("tool_results", []) or [])
        _log(f"execute_simple done: success={result.get('success')}, result_len={len(str(result.get('result', '')))}")

        if not result.get("success"):
            err = result.get("error") or "[NO_TOOLCALL] 执行失败"
            self._emit_error(err)
            healed = self._attempt_self_heal(raw_user_message or user_message, route, result)
            if healed.get("success"):
                if healed.get("result"):
                    self._emit_message("assistant", healed["result"])
                self._last_task_success = True
                self._end_session(healed.get("result", ""))
                return
            self._last_task_success = False
        else:
            self._last_task_success = True

        if result.get("result"):
            self._emit_message("assistant", result["result"])

        self._end_session(result.get("result", ""))

    def _process_complex(
        self,
        user_message: str,
        route,
        raw_user_message: str = "",
        capability_tool_chain: list[str] | None = None,
    ):
        prewarm_thread = None
        if route.domain == "shader":
            _log("Starting shader prewarm in parallel with planning")
            prewarm_thread = threading.Thread(
                target=self._executor.prewarm_shader_context,
                args=(user_message,),
                daemon=True,
            )
            prewarm_thread.start()

        _log(f"Planning: intent={route.intent}")
        plan = self._planner.plan(user_message, route.intent)
        _log(f"Plan result: {plan.total_steps} steps, summary={plan.summary[:80] if plan.summary else 'N/A'}")
        plan = self._enforce_capability_tool_grounding(
            plan=plan,
            raw_user_message=raw_user_message or user_message,
            route=route,
            capability_tool_chain=capability_tool_chain or [],
        )

        if prewarm_thread:
            prewarm_thread.join(timeout=2.0)
            _log("Shader prewarm join complete (timeout=2s)")

        if not plan.steps:
            _log("Empty plan, falling back to simple")
            self._emit_message("assistant", "无法分解任务，尝试直接执行...")
            self._process_simple(user_message, route, raw_user_message=raw_user_message)
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

            result = self._execute_plan_step_with_policy(
                step=next_step,
                route=route,
                prev_summary=prev_summary,
                user_message=user_message,
            )
            self._current_tool_calls.append({"tool": next_step.tool, "result": result})
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
        self._last_task_success = len(plan.failed_steps) == 0
        self._emit_message("assistant", final_text)
        self._end_session(final_text)

    def _enforce_capability_tool_grounding(self, plan, raw_user_message: str, route, capability_tool_chain: list[str]):
        """
        Plan 级工具约束：
        1) 若计划使用了 capability 工具链之外的工具，先做一次带约束重规划。
        2) 若仍有越界工具，则剔除越界步骤（保留无 tool 的描述步骤）。
        """
        if not capability_tool_chain:
            return plan
        allow = set(capability_tool_chain)
        allow.update({"get_scene_info", "scene.get_summary", "get_object_info", "gn_get_summary"})

        def _invalid_tools(cur_plan):
            bad = []
            for s in (cur_plan.steps or []):
                tool_name = str(getattr(s, "tool", "") or "").strip()
                if tool_name and tool_name not in allow:
                    bad.append(tool_name)
            return sorted(set(bad))

        invalid = _invalid_tools(plan)
        if not invalid:
            return plan

        if self.on_plan:
            self._fire_callback(
                self.on_plan,
                "⚠️ 计划工具超出 grounding 范围，触发一次约束重规划："
                + ", ".join(invalid[:8]),
            )

        constrained_prompt = (
            f"{raw_user_message}\n\n"
            "[计划约束]\n"
            "每一步 tool 必须从以下列表中选择：\n- "
            + "\n- ".join(capability_tool_chain[:20])
            + "\n可选验证工具：get_scene_info, scene.get_summary, get_object_info, gn_get_summary\n"
            "若无法完成，请把 tool 留空并在 description 写明缺失能力，不要编造工具名。"
        )
        try:
            replanned = self._planner.plan(constrained_prompt, route.intent)
            invalid2 = _invalid_tools(replanned)
            if replanned.steps and not invalid2:
                if self.on_plan:
                    self._fire_callback(self.on_plan, "✅ 约束重规划成功，已切换到 grounded 计划。")
                return replanned
            if self.on_plan and replanned.steps:
                self._fire_callback(
                    self.on_plan,
                    "⚠️ 重规划仍含越界工具，执行前自动剔除："
                    + ", ".join(invalid2[:8]),
                )
            # 最终兜底：剔除越界工具步骤，保留空工具描述步骤
            safe_steps = []
            for s in (replanned.steps or plan.steps or []):
                tool_name = str(getattr(s, "tool", "") or "").strip()
                if (not tool_name) or tool_name in allow:
                    safe_steps.append(s)
            if safe_steps:
                replanned.steps = safe_steps
                return replanned
        except Exception as e:
            _log(f"grounded replanning failed: {e}")

        # 回退：使用原计划中可执行的安全步骤
        safe_steps = []
        for s in (plan.steps or []):
            tool_name = str(getattr(s, "tool", "") or "").strip()
            if (not tool_name) or tool_name in allow:
                safe_steps.append(s)
        if safe_steps:
            plan.steps = safe_steps
        return plan

    def _execute_plan_step_with_policy(self, step, route, prev_summary: str, user_message: str) -> dict:
        on_fail = step.on_fail or {}
        retry_budget = int(on_fail.get("retry", 0) or 0)
        strategy = str(on_fail.get("strategy", "retry_same")).strip() or "retry_same"
        attempts = 0
        last_result = {"success": False, "result": None, "error": "not executed"}

        while attempts <= retry_budget:
            attempts += 1
            result = self._executor.execute_step(step, route.domain, prev_summary, user_message)
            check_ok, check_reason = self._run_step_check(step, result)
            if result.get("success") and check_ok:
                if attempts > 1 and self.on_plan:
                    self._fire_callback(self.on_plan, f"✅ Step {step.step} 在第 {attempts} 次尝试成功")
                return result

            last_result = result
            if attempts > retry_budget:
                break

            if self.on_plan:
                self._fire_callback(
                    self.on_plan,
                    f"⚠️ Step {step.step} 失败，按策略 {strategy} 重试 ({attempts}/{retry_budget})：{check_reason or result.get('error', 'unknown')}",
                )

            if strategy == "revise_args" and isinstance(step.params, dict):
                # 轻量参数修复：常见数值参数做保护，避免无效值重复失败
                if "size_m" in step.params and isinstance(step.params.get("size_m"), (int, float)):
                    step.params["size_m"] = max(0.001, float(step.params["size_m"]))
                if "segments" in step.params and isinstance(step.params.get("segments"), int):
                    step.params["segments"] = max(1, int(step.params["segments"]))

        step.status = "failed"
        step.error = last_result.get("error") or "step policy exhausted"
        return last_result

    def _run_step_check(self, step, result: dict) -> tuple[bool, str]:
        if not result.get("success"):
            return False, result.get("error", "tool execution failed")
        check = step.check or {}
        if not isinstance(check, dict) or not check:
            return True, ""

        check_tool = check.get("tool")
        expect_contains = check.get("expect_contains") or []
        if not check_tool:
            return True, ""

        check_result = self._executor._run_tool(check_tool, {})
        if not check_result.get("success"):
            return False, f"check tool failed: {check_result.get('error', 'unknown')}"
        if expect_contains:
            text = str(check_result.get("result", ""))
            missing = [s for s in expect_contains if str(s) not in text]
            if missing:
                return False, f"check missing: {missing}"
        return True, ""

    def _attempt_self_heal(self, user_message: str, route, failed_result: dict) -> dict:
        """
        简易自愈：把最近错误 + 场景摘要回灌给执行器再跑一次。
        """
        try:
            scene = self._executor._run_tool("get_scene_info", {})
            scene_text = ""
            if scene.get("success"):
                scene_text = str(scene.get("result", ""))[:1200]
            error_text = str(failed_result.get("error", "unknown"))[:600]
            repair_prompt = (
                f"原始需求：{user_message}\n"
                f"上次失败错误：{error_text}\n"
                f"当前场景摘要：{scene_text}\n"
                "请修复参数并重新执行，必须调用 MCP 工具，不要输出脚本。"
            )
            if self.on_plan:
                self._fire_callback(self.on_plan, "♻️ 检测到失败，启动一次自动自愈重试。")
            return self._executor.execute_simple(repair_prompt, route.domain, route.intent)
        except Exception as e:
            return {"success": False, "result": None, "error": f"self-heal failed: {e}"}

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

    def _emit_tool_call(self, tool_name: str, args: dict):
        if self.on_tool_call:
            self._fire_callback(self.on_tool_call, tool_name, args)

    def _emit_plan(self, text: str):
        if self.on_plan:
            self._fire_callback(self.on_plan, text)

    def _end_session(self, result: str):
        if self._reflection:
            try:
                self._reflection.reflect_task_outcome(
                    session_id=self._session_id,
                    user_input=self._last_user_message,
                    normalized_input=self._last_normalized or self._last_user_message,
                    tool_calls=self._current_tool_calls,
                    result_text=result or "",
                    success=bool(self._last_task_success),
                    corrected_after_error=False,
                )
            except Exception as e:
                _log(f"reflection task outcome failed: {e}")
        try:
            from .. import action_log
            action_log.end_session(result[:200])
        except Exception:
            pass

    def _fire_callback(self, callback, *args):
        self._runtime_fire_callback(callback, *args)

    def clear_history(self):
        self._context.reset()

    def _prepare_input_context(self, user_message: str) -> dict:
        normalized = user_message
        extracted_terms = []
        task_type = "general"
        rag_meta = {"glossary_count": 0, "recipe_count": 0, "capability_count": 0}
        memory_hits = 0
        enriched_message = user_message
        capability_tool_chain = []
        capability_ids = []

        # Backend 2.0 path
        if self._mini_rewriter and auto_retrieve:
            try:
                rewrite = self._mini_rewriter.rewrite(user_message, llm=self._executor._llm)
                normalized = rewrite.get("normalized_instruction", user_message)
                extracted_terms = rewrite.get("extracted_terms", [])
                task_type = rewrite.get("task_type", "general")

                rag = auto_retrieve(
                    normalized_instruction=normalized,
                    extracted_terms=extracted_terms,
                    task_type=task_type,
                )
                rag_text = rag.get("context_text", "")
                rag_meta = rag.get("meta", rag_meta) or rag_meta
                for cap in (rag.get("capability_hits", []) or []):
                    sid = str(cap.get("skill_id", "")).strip()
                    if sid and sid not in capability_ids:
                        capability_ids.append(sid)
                    for tool_name in (cap.get("tool_chain", []) or []):
                        tn = str(tool_name).strip()
                        if tn and tn not in capability_tool_chain:
                            capability_tool_chain.append(tn)

                mem_results = []
                if self._memory_store:
                    mem_results = self._memory_store.search_similar(normalized, top_k=5)
                memory_hits = len(mem_results)

                if self._context_builder and ContextBuildInput and CompressionStrategy:
                    build_in = ContextBuildInput(
                        system_prompt="You are Blender Agent Orchestrator context build helper.",
                        history_messages=[{"role": "user", "content": user_message}],
                        rag_context=rag_text,
                        long_term_memories=mem_results,
                        normalized_instruction=normalized,
                        scene_summary="",
                        token_warning="",
                    )
                    built = self._context_builder.build(
                        build_in,
                        strategy=CompressionStrategy.BALANCED,
                    )
                    # 对 Executor/Planner 保持字符串输入：抽取 RAG + memory 摘要拼接
                    dynamic = []
                    if rag_text:
                        dynamic.append(rag_text[:1200])
                    if mem_results:
                        hints = [str(x.get("content", ""))[:160] for x in mem_results[:3]]
                        dynamic.append("[Memory Recall]\n- " + "\n- ".join(hints))
                    enriched_message = normalized + ("\n\n" + "\n\n".join(dynamic) if dynamic else "")
                    if built.get("deep_sleep_triggered") and self.on_plan:
                        self._fire_callback(self.on_plan, "💤 已在上下文压缩前触发 Deep Sleep。")
                else:
                    enriched_message = normalized + (f"\n\n{rag_text}" if rag_text else "")
                return {
                    "normalized": normalized,
                    "extracted_terms": extracted_terms,
                    "task_type": task_type,
                    "rag_meta": rag_meta,
                    "memory_hits": memory_hits,
                    "enriched_message": enriched_message,
                    "capability_tool_chain": capability_tool_chain,
                    "capability_ids": capability_ids,
                }
            except Exception as e:
                _log(f"backend v2 preprocess failed, fallback legacy: {e}")

        # Legacy fallback path
        rewrite = mini_rewrite(user_message, llm=self._executor._llm)
        normalized = rewrite.get("normalized_instruction", user_message)
        extracted_terms = rewrite.get("extracted_terms", [])
        task_type = rewrite.get("task_type", "general")
        rag = retrieve_context(
            normalized_instruction=normalized,
            extracted_terms=extracted_terms,
            task_type=task_type,
        )
        rag_block, rag_meta = build_rag_prompt_block(rag)
        enriched_message = normalized
        if rag_block:
            enriched_message = f"{normalized}\n\n{rag_block}"
        return {
            "normalized": normalized,
            "extracted_terms": extracted_terms,
            "task_type": task_type,
            "rag_meta": rag_meta,
            "memory_hits": memory_hits,
            "enriched_message": enriched_message,
            "capability_tool_chain": capability_tool_chain,
            "capability_ids": capability_ids,
        }

    def _on_pre_compression_deep_sleep(self, payload: dict):
        if not self._reflection:
            return
        try:
            self._reflection.deep_sleep(
                session_id=self._session_id,
                full_context_messages=[
                    {"role": "user", "content": self._last_user_message},
                    {"role": "assistant", "content": json.dumps(payload or {}, ensure_ascii=False)},
                ],
                task_pattern=self._last_task_type or "general",
                llm=self._executor._llm,
            )
        except Exception as e:
            _log(f"deep sleep hook failed: {e}")
