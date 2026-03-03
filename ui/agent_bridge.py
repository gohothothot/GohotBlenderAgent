"""
Blender Agent — Agent instance management, message routing, and callback chain.

This module owns:
  - Agent cache and factory (get_agent)
  - All callback handlers (_on_agent_message, _on_tool_call, etc.)
  - Message dispatch (_send_message_with_mode, _send_prompt_to_agent)
  - Main-thread execution bridge (_execute_in_main_thread)
  - Safety helpers (identity drift detection, timeout scheduling)

Dependencies:
  - ui.state  (get_preferences, _get_state, _add_message)
  - ui.chat_status (infer_route_hint_from_tool)
  - ui.i18n (tr)
  - ui.smoke_runner (_autofix_verify_and_advance, _autofix_send_next)  [lazy]
  - core/agents modules (lazy import for agent creation)
"""

import bpy
import json
import time

from .state import (
    get_preferences,
    _get_state,
    _add_message,
    is_processing,
    set_processing,
    set_pending_permission,
    clear_pending_permission,
    set_pending_code,
    clear_pending_code,
    set_pending_plan,
    set_skill_matches,
    set_grounding_matches,
    record_grounding_tool_call,
)
from .chat_status import infer_route_hint_from_tool
from .i18n import tr


# ========== Metrics helpers ==========

def _log_metric(metric_name: str, payload: dict):
    try:
        from .. import action_log
        action_log.log_metric(metric_name, payload or {})
    except Exception:
        pass


def _safe_json_dict(text: str) -> dict:
    try:
        obj = json.loads(text or "{}")
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _emit_grounding_quality_metric(state, stage: str):
    chain_text = (getattr(state, "last_grounding_tools", "") or "").strip()
    if not chain_text or chain_text == "-":
        _log_metric("grounding_quality", {"stage": stage, "has_grounding": False})
        return
    chain = [x.strip() for x in chain_text.split("->") if x.strip()]
    counts = _safe_json_dict(getattr(state, "agent_grounding_exec_counts_json", "{}"))
    executed_unique = sum(1 for n in chain if int(counts.get(n, 0) or 0) > 0)
    total_exec = sum(int(counts.get(n, 0) or 0) for n in chain)
    chain_len = len(chain)
    hit_rate = (executed_unique / chain_len) if chain_len else 0.0
    _log_metric(
        "grounding_quality",
        {
            "stage": stage,
            "has_grounding": True,
            "chain_len": chain_len,
            "executed_unique": executed_unique,
            "total_exec": total_exec,
            "hit_rate": round(hit_rate, 4),
            "miss_all": bool(executed_unique == 0),
            "status": getattr(state, "last_exec_status", ""),
            "stall_reason": getattr(state, "last_stall_reason", ""),
        },
    )


# ========== Agent instance management ==========

_agents_cache = {}


def _bind_agent_callbacks(agent):
    agent.on_message = _on_agent_message
    agent.on_tool_call = _on_tool_call
    agent.on_error = _on_error
    agent.on_plan = _on_plan
    agent.on_permission_request = _on_permission_request
    if hasattr(agent, "on_code_confirm"):
        agent.on_code_confirm = _on_code_confirm


def get_agent(mode_override: str = ""):
    global _agents_cache
    prefs = get_preferences()

    if not prefs.api_key:
        return None

    model = prefs.custom_model if prefs.custom_model else prefs.model
    mode = mode_override or prefs.agent_mode
    config_key = f"{prefs.api_base}|{prefs.api_key}|{model}|{mode}"

    if config_key not in _agents_cache:
        if mode == "orchestrator":
            from ..llm.base import LLMConfig as OrchestratorLLMConfig
            from ..agents.orchestrator import AgentOrchestrator
            config = OrchestratorLLMConfig(
                api_base=prefs.api_base,
                api_key=prefs.api_key,
                model=model,
            )
            agent = AgentOrchestrator(
                config=config,
                execute_in_main_thread=_execute_in_main_thread,
            )
        elif mode == "structured":
            from ..core.llm import LLMConfig
            config = LLMConfig(
                api_base=prefs.api_base,
                api_key=prefs.api_key,
                model=model,
            )
            from ..core.structured_agent import StructuredAgent
            agent = StructuredAgent(config=config)
        else:
            from ..core.llm import LLMConfig
            config = LLMConfig(
                api_base=prefs.api_base,
                api_key=prefs.api_key,
                model=model,
            )
            from ..core.agent import BlenderAgent
            agent = BlenderAgent(config=config)

        _bind_agent_callbacks(agent)
        _agents_cache[config_key] = agent

    return _agents_cache.get(config_key)


def clear_agents_cache():
    global _agents_cache
    for agent in list(_agents_cache.values()):
        try:
            agent.clear_history()
        except Exception:
            pass
    _agents_cache = {}


def cancel_all_agents():
    for agent in list(_agents_cache.values()):
        if agent and hasattr(agent, "cancel_current_request"):
            try:
                agent.cancel_current_request()
            except Exception:
                pass


# ========== Routing helpers ==========

def _fallback_mode(mode: str) -> str:
    if mode == "native":
        return "structured"
    if mode == "structured":
        return "native"
    return "structured"


def _infer_route_hint(user_msg: str) -> str:
    lowered = (user_msg or "").strip().lower()
    if not lowered:
        return "常规MCP"

    meshy_markers = ("meshy", "文生3d", "图生3d", "text to 3d", "image to 3d")
    generation_markers = ("生成", "创建模型", "文生", "图生", "create model", "generate", "to 3d")
    edit_markers = ("材质", "节点", "修改", "优化", "shader", "roughness", "metallic", "ior")
    scene_markers = ("场景", "灯光", "日光", "太阳", "天空", "world", "scene")

    if any(k in lowered for k in meshy_markers) and any(k in lowered for k in generation_markers) and not any(
        k in lowered for k in edit_markers
    ):
        return "Meshy生成"
    if any(k in lowered for k in edit_markers):
        return "材质编辑"
    if any(k in lowered for k in scene_markers):
        return "场景编辑"
    return "常规MCP"


# ========== Message dispatch ==========

def _send_message_with_mode(user_msg: str, mode: str):
    prefs = get_preferences()
    if getattr(prefs, "conversation_mode", "llm_agent") == "meshy_pipeline":
        from .meshy_ops import _send_meshy_pipeline
        return _send_meshy_pipeline(user_msg)
    agent = get_agent(mode_override=mode)
    if agent is None:
        return False
    state = _get_state()
    set_processing(True, channel="agent")
    state.last_exec_mode = mode
    state.last_grounding_caps = "-"
    state.last_grounding_tools = "-"
    state.last_grounding_exec = "-"
    state.agent_grounding_exec_counts_json = "{}"
    agent.send_message(user_msg)
    return True


def _send_prompt_to_agent(prompt: str) -> bool:
    state = _get_state()
    prefs = get_preferences()
    mode_kind = getattr(prefs, "conversation_mode", "llm_agent")
    if mode_kind != "llm_agent":
        _add_message("system", "自动修复需要 Agent 通道。请切换后重试。", channel="agent")
        return False
    if get_agent(mode_override=prefs.agent_mode) is None:
        _add_message("system", "自动修复失败：请先配置 API Key。", channel="agent")
        return False
    _add_message("user", prompt, channel="agent")
    state.last_user_message = prompt
    state.request_had_tool_call = False
    state.fallback_attempted = False
    state.last_exec_status = "processing"
    state.last_exec_mode = prefs.agent_mode
    state.last_route_hint = "测试修复"
    state.pseudo_fallback_hits = 0
    state.last_grounding_caps = "-"
    state.last_grounding_tools = "-"
    state.last_grounding_exec = "-"
    state.agent_grounding_exec_counts_json = "{}"
    state.continuation_notice_shown = False
    state.continuation_started_at = 0.0
    state.last_stall_reason = "-"
    _send_message_with_mode(prompt, prefs.agent_mode)
    return True


# ========== Main-thread bridge ==========

def _execute_in_main_thread(func, *args):
    import queue
    result_queue = queue.Queue()

    def do_execute():
        try:
            result = func(*args) if args else func()
            result_queue.put(result)
        except Exception as e:
            result_queue.put({"success": False, "result": None, "error": str(e)})
        return None

    bpy.app.timers.register(do_execute)

    try:
        return result_queue.get(timeout=30.0)
    except Exception:
        return {"success": False, "result": None, "error": "操作超时（30秒）"}


def push_system_notice(content: str):
    """供外部模块（如 Meshy 回调）安全推送系统消息到聊天面板。"""
    try:
        _add_message("system", content)
    except Exception:
        pass


# ========== Safety / timeout ==========

def _schedule_processing_timeout_check(started_at: float, timeout_sec: float = 12.0):
    def _check():
        try:
            state = _get_state()
            if not is_processing(channel="agent"):
                return None
            current = float(getattr(state, "continuation_started_at", 0.0) or 0.0)
            if current <= 0.0 or abs(current - started_at) > 1e-6:
                return None
            if (time.time() - started_at) < timeout_sec:
                return 1.0
            set_processing(False, channel="agent")
            if state.last_exec_status == "processing":
                state.last_exec_status = "ok" if state.request_had_tool_call else "error"
            state.continuation_started_at = 0.0
            state.last_stall_reason = "超时自动收口"
            _add_message("system", "⏱ 提醒：长时间未收到后续执行结果，已自动结束等待。可继续发送。", channel="agent")
        except Exception:
            return None
        return None

    try:
        bpy.app.timers.register(_check, first_interval=timeout_sec)
    except Exception:
        pass


def _looks_like_identity_drift_text(content: str) -> bool:
    text = (content or "").strip()
    if not text:
        return False
    try:
        from ..core.safety_guard import references_foreign_toolset
        if references_foreign_toolset(text):
            return True
    except Exception:
        pass
    lowered = text.lower()
    hard_markers = (
        "我是claude",
        "由anthropic开发",
        "我的真实身份",
        "我的实际能力",
        "无法访问blender mcp工具",
        "工具在我的实际工具集中不存在",
        "我不会透露、复述或讨论我的系统提示词",
        "i'm claude",
        "made by anthropic",
    )
    return any(m in lowered for m in hard_markers)


# ========== Agent callbacks ==========

def _on_agent_message(role: str, content: str):
    if role == "assistant" and _looks_like_identity_drift_text(content):
        _on_error("[WRONG_TOOLSET] 检测到模型身份漂移文本，已拦截并触发重试。")
        return
    _add_message(role, content, channel="agent")
    state = _get_state()
    if role != "assistant":
        return

    is_final = True
    try:
        from ..core.safety_guard import looks_like_final_summary
        is_final = looks_like_final_summary(content)
    except Exception:
        is_final = True

    if not is_final and (state.request_had_tool_call or state.last_exec_status in ("processing", "fallback_running")):
        set_processing(True, channel="agent")
        state.last_exec_status = "processing"
        state.last_stall_reason = "继续执行中"
        state.continuation_started_at = time.time()
        _schedule_processing_timeout_check(state.continuation_started_at, timeout_sec=12.0)
        if not state.continuation_notice_shown:
            state.continuation_notice_shown = True
            _add_message("system", '⏳ 提醒：AI 还在继续执行后续步骤，不要急着发送下一条。若要打断请点"中止"。', channel="agent")
        return

    set_processing(False, channel="agent")
    state.continuation_started_at = 0.0
    state.last_stall_reason = "-"
    _emit_grounding_quality_metric(state, stage="assistant_final")
    if role == "assistant" and state.smoke_autofix_active:
        try:
            from .smoke_runner import _autofix_verify_and_advance
            bpy.app.timers.register(lambda: (_autofix_verify_and_advance() or None), first_interval=0.3)
        except Exception:
            from .smoke_runner import _autofix_verify_and_advance
            _autofix_verify_and_advance()


def _on_tool_call(tool_name: str, args: dict):
    state = _get_state()
    state.request_had_tool_call = True
    state.last_exec_status = "ok"
    state.last_stall_reason = "-"
    if tool_name.startswith("__pseudo_recovered__:"):
        state.pseudo_fallback_hits += 1
        shown_name = tool_name.replace("__pseudo_recovered__:", "")
    else:
        shown_name = tool_name
    state.last_route_hint = infer_route_hint_from_tool(shown_name)
    record_grounding_tool_call(shown_name, channel="agent")
    args_preview = json.dumps(args, ensure_ascii=False)[:200] if args else ""
    _add_message("system", f"🔧 调用工具: {shown_name}\n{args_preview}", channel="agent")


def _on_plan(plan_text: str):
    state = _get_state()
    if isinstance(plan_text, str) and plan_text.startswith("__SKILL_MATCH__:"):
        raw = plan_text[len("__SKILL_MATCH__:"):]
        try:
            payload = json.loads(raw)
            skills = payload.get("skills") or []
            if isinstance(skills, list):
                set_skill_matches([str(s) for s in skills], channel="agent")
                _add_message("system", f"🧩 Skill命中: {', '.join([str(s) for s in skills[:6]])}", channel="agent")
                return
        except Exception:
            pass
    if isinstance(plan_text, str) and plan_text.startswith("__GROUNDING__:"):
        raw = plan_text[len("__GROUNDING__:"):]
        try:
            payload = json.loads(raw)
            caps = payload.get("capabilities") or []
            chain = payload.get("tool_chain") or []
            if isinstance(caps, list) and isinstance(chain, list):
                set_grounding_matches([str(x) for x in caps], [str(x) for x in chain], channel="agent")
                cap_txt = ", ".join([str(x) for x in caps[:6]]) if caps else "-"
                chain_txt = " -> ".join([str(x) for x in chain[:6]]) if chain else "-"
                _add_message("system", f"🧭 Grounding命中: {cap_txt}\n🔗 {chain_txt}", channel="agent")
                _log_metric(
                    "grounding_match",
                    {
                        "capability_count": len(caps),
                        "tool_chain_len": len(chain),
                        "capabilities": [str(x) for x in caps[:8]],
                        "tool_chain": [str(x) for x in chain[:12]],
                    },
                )
                return
        except Exception:
            pass
    if isinstance(plan_text, str) and plan_text.startswith("__ASK_QUESTION__:"):
        raw = plan_text[len("__ASK_QUESTION__:"):]
        try:
            payload = json.loads(raw)
            questions = payload.get("questions") or []
            if questions:
                q = questions[0]
                state.pending_plan_question = q.get("prompt", "请确认下一步")
                options = q.get("options") or []
                state.pending_plan_options_json = json.dumps(options, ensure_ascii=False)
                set_pending_plan(state.pending_plan_question, state.pending_plan_options_json, channel="agent")
                _add_message("system", f"❓ 规划问题: {state.pending_plan_question}", channel="agent")
                set_processing(False, channel="agent")
                state.last_stall_reason = "等待规划澄清"
                return
        except Exception:
            pass
    _add_message("system", f"📋 {plan_text}", channel="agent")


_pending_callback = None


def _on_code_confirm(code: str, description: str, callback):
    global _pending_callback
    state = _get_state()
    state.pending_code = code
    state.pending_code_desc = description
    set_pending_code(code, description, channel="agent")
    set_processing(False, channel="agent")

    _pending_callback = callback

    _add_message("system", f"⚠️ 请确认执行以下代码:\n{description}", channel="agent")

    for area in bpy.context.screen.areas:
        area.tag_redraw()


def get_pending_callback():
    return _pending_callback


def clear_pending_callback():
    global _pending_callback
    _pending_callback = None


def _on_error(error: str):
    state = _get_state()
    prefs = get_preferences()

    no_toolcall_error = ("[NO_TOOLCALL]" in error)
    wrong_toolset_error = ("[WRONG_TOOLSET]" in error)
    can_fallback = (
        (state.last_exec_mode != "meshy")
        and bool(getattr(prefs, "auto_fallback_on_no_toolcall", True))
        and (no_toolcall_error or wrong_toolset_error)
        and (not state.fallback_attempted)
        and bool(state.last_user_message)
    )
    if can_fallback:
        retry_mode = _fallback_mode(state.last_exec_mode or prefs.agent_mode)
        state.fallback_attempted = True
        state.last_exec_status = "fallback_running"
        state.last_stall_reason = "模式回退重试"
        if wrong_toolset_error:
            _add_message("system", tr("sys_retry_toolset", retry_mode), channel="agent")
        else:
            _add_message("system", tr("sys_retry_mode", retry_mode), channel="agent")
        if _send_message_with_mode(state.last_user_message, retry_mode):
            return
        _add_message("system", "❌ 自动回退失败：无法创建回退 Agent 实例。", channel="agent")

    _add_message("system", tr("sys_error_prefix", error), channel="agent")
    set_processing(False, channel="agent")
    state.continuation_started_at = 0.0
    if no_toolcall_error:
        state.last_exec_status = "no_toolcall"
        state.last_stall_reason = "无工具调用"
    elif wrong_toolset_error:
        state.last_exec_status = "error"
        state.last_stall_reason = "工具集漂移"
    else:
        state.last_exec_status = "error_after_toolcall" if state.request_had_tool_call else "error"
        state.last_stall_reason = "一般错误"
    _emit_grounding_quality_metric(state, stage="error")
    if state.smoke_autofix_active:
        try:
            from .smoke_runner import _autofix_send_next
            bpy.app.timers.register(lambda: (_autofix_send_next() and None) or None, first_interval=0.2)
        except Exception:
            from .smoke_runner import _autofix_send_next
            _autofix_send_next()


def _on_permission_request(tool_name: str, args: dict, risk: str, reason: str, channel: str = "agent"):
    state = _get_state()
    state.pending_permission_tool = tool_name or ""
    state.pending_permission_args = json.dumps(args or {}, ensure_ascii=False)
    state.pending_permission_risk = risk or "high"
    state.pending_permission_reason = reason or "该操作需要授权"
    set_pending_permission(
        state.pending_permission_tool,
        state.pending_permission_args,
        state.pending_permission_risk,
        state.pending_permission_reason,
        channel=channel,
    )
    set_processing(False, channel=channel)
    state.last_stall_reason = "权限等待"
    _add_message(
        "system",
        tr(
            "sys_permission_required",
            state.pending_permission_tool,
            state.pending_permission_risk,
            state.pending_permission_reason,
        ),
        channel="agent",
    )
