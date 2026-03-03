"""
UI State — Blender PropertyGroup definitions and state accessors.

Centralises all bpy PropertyGroup classes so they can be imported and
registered independently of the main chat_ui module.
"""

import json
import bpy
from bpy.props import (
    StringProperty,
    CollectionProperty,
    IntProperty,
    BoolProperty,
    EnumProperty,
    FloatProperty,
)
from bpy.types import PropertyGroup


class ChatMessage(PropertyGroup):
    role: StringProperty(name="Role")
    content: StringProperty(name="Content")
    is_code: BoolProperty(name="Is Code", default=False)


class TodoItem(PropertyGroup):
    content: StringProperty(name="Content", default="")
    done: BoolProperty(name="Done", default=False)
    todo_type: EnumProperty(
        name="Type",
        items=[
            ("USER", "用户", "用户自己要做的事"),
            ("AGENT", "Agent", "让 Agent 去做的事"),
        ],
        default="USER",
    )


class AgentState(PropertyGroup):
    messages: CollectionProperty(type=ChatMessage)
    active_message_index: IntProperty(name="Active Message", default=0)
    meshy_messages: CollectionProperty(type=ChatMessage)
    meshy_active_message_index: IntProperty(name="Meshy Active Message", default=0)
    todos: CollectionProperty(type=TodoItem)
    active_todo_index: IntProperty(name="Active Todo", default=0)
    input_text: StringProperty(name="Input", default="")
    meshy_input_text: StringProperty(name="Meshy Input", default="")
    is_processing: BoolProperty(name="Processing", default=False)
    agent_is_processing: BoolProperty(name="Agent Processing", default=False)
    meshy_is_processing: BoolProperty(name="Meshy Processing", default=False)
    pending_code: StringProperty(name="Pending Code", default="")
    pending_code_desc: StringProperty(name="Pending Code Desc", default="")
    agent_pending_code: StringProperty(name="Agent Pending Code", default="")
    agent_pending_code_desc: StringProperty(name="Agent Pending Code Desc", default="")
    meshy_pending_code: StringProperty(name="Meshy Pending Code", default="")
    meshy_pending_code_desc: StringProperty(name="Meshy Pending Code Desc", default="")
    pending_permission_tool: StringProperty(name="Pending Permission Tool", default="")
    pending_permission_args: StringProperty(name="Pending Permission Args", default="")
    pending_permission_risk: StringProperty(name="Pending Permission Risk", default="")
    pending_permission_reason: StringProperty(name="Pending Permission Reason", default="")
    agent_pending_permission_tool: StringProperty(name="Agent Pending Permission Tool", default="")
    agent_pending_permission_args: StringProperty(name="Agent Pending Permission Args", default="")
    agent_pending_permission_risk: StringProperty(name="Agent Pending Permission Risk", default="")
    agent_pending_permission_reason: StringProperty(name="Agent Pending Permission Reason", default="")
    meshy_pending_permission_tool: StringProperty(name="Meshy Pending Permission Tool", default="")
    meshy_pending_permission_args: StringProperty(name="Meshy Pending Permission Args", default="")
    meshy_pending_permission_risk: StringProperty(name="Meshy Pending Permission Risk", default="")
    meshy_pending_permission_reason: StringProperty(name="Meshy Pending Permission Reason", default="")
    pending_tool_id: StringProperty(name="Pending Tool ID", default="")
    last_user_message: StringProperty(name="Last User Message", default="")
    last_exec_status: StringProperty(name="Last Exec Status", default="idle")
    last_exec_mode: StringProperty(name="Last Exec Mode", default="")
    last_route_hint: StringProperty(name="Last Route Hint", default="-")
    last_stall_reason: StringProperty(name="Last Stall Reason", default="-")
    last_skill_matches: StringProperty(name="Last Skill Matches", default="-")
    agent_last_skill_matches: StringProperty(name="Agent Last Skill Matches", default="-")
    meshy_last_skill_matches: StringProperty(name="Meshy Last Skill Matches", default="-")
    last_grounding_caps: StringProperty(name="Last Grounding Caps", default="-")
    agent_last_grounding_caps: StringProperty(name="Agent Last Grounding Caps", default="-")
    meshy_last_grounding_caps: StringProperty(name="Meshy Last Grounding Caps", default="-")
    last_grounding_tools: StringProperty(name="Last Grounding Tools", default="-")
    agent_last_grounding_tools: StringProperty(name="Agent Last Grounding Tools", default="-")
    meshy_last_grounding_tools: StringProperty(name="Meshy Last Grounding Tools", default="-")
    last_grounding_exec: StringProperty(name="Last Grounding Exec", default="-")
    agent_last_grounding_exec: StringProperty(name="Agent Last Grounding Exec", default="-")
    meshy_last_grounding_exec: StringProperty(name="Meshy Last Grounding Exec", default="-")
    agent_grounding_exec_counts_json: StringProperty(name="Agent Grounding Exec Counts JSON", default="{}")
    meshy_grounding_exec_counts_json: StringProperty(name="Meshy Grounding Exec Counts JSON", default="{}")
    fallback_attempted: BoolProperty(name="Fallback Attempted", default=False)
    request_had_tool_call: BoolProperty(name="Request Had Tool Call", default=False)
    pseudo_fallback_hits: IntProperty(name="Pseudo Fallback Hits", default=0)
    continuation_notice_shown: BoolProperty(name="Continuation Notice Shown", default=False)
    continuation_started_at: FloatProperty(name="Continuation Started At", default=0.0)
    pending_plan_question: StringProperty(name="Pending Plan Question", default="")
    pending_plan_options_json: StringProperty(name="Pending Plan Options JSON", default="[]")
    agent_pending_plan_question: StringProperty(name="Agent Pending Plan Question", default="")
    agent_pending_plan_options_json: StringProperty(name="Agent Pending Plan Options JSON", default="[]")
    meshy_pending_plan_question: StringProperty(name="Meshy Pending Plan Question", default="")
    meshy_pending_plan_options_json: StringProperty(name="Meshy Pending Plan Options JSON", default="[]")
    smoke_failures_json: StringProperty(name="Smoke Failures JSON", default="[]")
    smoke_last_summary: StringProperty(name="Smoke Last Summary", default="")
    smoke_autofix_active: BoolProperty(name="Smoke AutoFix Active", default=False)
    smoke_autofix_queue_json: StringProperty(name="Smoke AutoFix Queue JSON", default="[]")
    smoke_autofix_total: IntProperty(name="Smoke AutoFix Total", default=0)
    smoke_autofix_current_json: StringProperty(name="Smoke AutoFix Current Item JSON", default="{}")
    todo_input: StringProperty(name="Todo Input", default="")
    todo_type_input: EnumProperty(
        name="Todo Type",
        items=[
            ("USER", "👤 用户", "用户自己要做的事"),
            ("AGENT", "🤖 Agent", "让 Agent 去做的事"),
        ],
        default="USER",
    )


# ---------- state accessors ----------

def get_preferences():
    root_package = __package__.split(".")[0]
    return bpy.context.preferences.addons[root_package].preferences


def _get_state() -> AgentState:
    return bpy.context.scene.blender_agent


def _resolve_channel(channel: str = "auto") -> str:
    if channel in ("agent", "meshy"):
        return channel
    try:
        prefs = get_preferences()
        return "meshy" if getattr(prefs, "conversation_mode", "llm_agent") == "meshy_pipeline" else "agent"
    except Exception:
        return "agent"


def _channel_prefix(channel: str = "auto") -> str:
    return "meshy" if _resolve_channel(channel) == "meshy" else "agent"


def is_processing(channel: str = "auto") -> bool:
    state = _get_state()
    attr = f"{_channel_prefix(channel)}_is_processing"
    return bool(getattr(state, attr, False))


def set_processing(value: bool, channel: str = "auto"):
    state = _get_state()
    prefix = _channel_prefix(channel)
    setattr(state, f"{prefix}_is_processing", bool(value))
    # 兼容旧字段：任一通道处理中即视为处理中
    state.is_processing = bool(state.agent_is_processing or state.meshy_is_processing)


def get_pending_permission(channel: str = "auto") -> dict:
    state = _get_state()
    prefix = _channel_prefix(channel)
    return {
        "tool": getattr(state, f"{prefix}_pending_permission_tool", ""),
        "args": getattr(state, f"{prefix}_pending_permission_args", "{}"),
        "risk": getattr(state, f"{prefix}_pending_permission_risk", ""),
        "reason": getattr(state, f"{prefix}_pending_permission_reason", ""),
    }


def set_pending_permission(tool: str, args_json: str, risk: str, reason: str, channel: str = "auto"):
    state = _get_state()
    prefix = _channel_prefix(channel)
    setattr(state, f"{prefix}_pending_permission_tool", tool or "")
    setattr(state, f"{prefix}_pending_permission_args", args_json or "{}")
    setattr(state, f"{prefix}_pending_permission_risk", risk or "high")
    setattr(state, f"{prefix}_pending_permission_reason", reason or "该操作需要授权")
    if prefix == "agent":
        state.pending_permission_tool = state.agent_pending_permission_tool
        state.pending_permission_args = state.agent_pending_permission_args
        state.pending_permission_risk = state.agent_pending_permission_risk
        state.pending_permission_reason = state.agent_pending_permission_reason


def clear_pending_permission(channel: str = "auto"):
    state = _get_state()
    prefix = _channel_prefix(channel)
    setattr(state, f"{prefix}_pending_permission_tool", "")
    setattr(state, f"{prefix}_pending_permission_args", "")
    setattr(state, f"{prefix}_pending_permission_risk", "")
    setattr(state, f"{prefix}_pending_permission_reason", "")
    if prefix == "agent":
        state.pending_permission_tool = ""
        state.pending_permission_args = ""
        state.pending_permission_risk = ""
        state.pending_permission_reason = ""


def set_pending_code(code: str, desc: str, channel: str = "agent"):
    state = _get_state()
    prefix = _channel_prefix(channel)
    setattr(state, f"{prefix}_pending_code", code or "")
    setattr(state, f"{prefix}_pending_code_desc", desc or "")
    if prefix == "agent":
        state.pending_code = state.agent_pending_code
        state.pending_code_desc = state.agent_pending_code_desc


def get_pending_code(channel: str = "agent") -> dict:
    state = _get_state()
    prefix = _channel_prefix(channel)
    return {
        "code": getattr(state, f"{prefix}_pending_code", ""),
        "desc": getattr(state, f"{prefix}_pending_code_desc", ""),
    }


def clear_pending_code(channel: str = "agent"):
    state = _get_state()
    prefix = _channel_prefix(channel)
    setattr(state, f"{prefix}_pending_code", "")
    setattr(state, f"{prefix}_pending_code_desc", "")
    if prefix == "agent":
        state.pending_code = ""
        state.pending_code_desc = ""


def set_pending_plan(question: str, options_json: str, channel: str = "agent"):
    state = _get_state()
    prefix = _channel_prefix(channel)
    setattr(state, f"{prefix}_pending_plan_question", question or "")
    setattr(state, f"{prefix}_pending_plan_options_json", options_json or "[]")
    if prefix == "agent":
        state.pending_plan_question = state.agent_pending_plan_question
        state.pending_plan_options_json = state.agent_pending_plan_options_json


def get_pending_plan(channel: str = "agent") -> dict:
    state = _get_state()
    prefix = _channel_prefix(channel)
    return {
        "question": getattr(state, f"{prefix}_pending_plan_question", ""),
        "options_json": getattr(state, f"{prefix}_pending_plan_options_json", "[]"),
    }


def clear_pending_plan(channel: str = "agent"):
    state = _get_state()
    prefix = _channel_prefix(channel)
    setattr(state, f"{prefix}_pending_plan_question", "")
    setattr(state, f"{prefix}_pending_plan_options_json", "[]")
    if prefix == "agent":
        state.pending_plan_question = ""
        state.pending_plan_options_json = "[]"


def set_skill_matches(skill_ids: list[str], channel: str = "agent"):
    state = _get_state()
    prefix = _channel_prefix(channel)
    text = ", ".join(skill_ids[:6]) if skill_ids else "-"
    setattr(state, f"{prefix}_last_skill_matches", text)
    if prefix == "agent":
        state.last_skill_matches = text


def set_grounding_matches(capability_ids: list[str], tool_chain: list[str], channel: str = "agent"):
    state = _get_state()
    prefix = _channel_prefix(channel)
    cap_text = ", ".join([str(x) for x in (capability_ids or [])[:6]]) if capability_ids else "-"
    tool_text = " -> ".join([str(x) for x in (tool_chain or [])[:6]]) if tool_chain else "-"
    setattr(state, f"{prefix}_last_grounding_caps", cap_text)
    setattr(state, f"{prefix}_last_grounding_tools", tool_text)
    setattr(state, f"{prefix}_grounding_exec_counts_json", "{}")
    setattr(state, f"{prefix}_last_grounding_exec", "-")
    if prefix == "agent":
        state.last_grounding_caps = cap_text
        state.last_grounding_tools = tool_text
        state.last_grounding_exec = "-"


def record_grounding_tool_call(tool_name: str, channel: str = "agent"):
    state = _get_state()
    prefix = _channel_prefix(channel)
    chain_text = getattr(state, f"{prefix}_last_grounding_tools", "") or ""
    if not chain_text or chain_text == "-":
        return
    chain = [x.strip() for x in chain_text.split("->") if x.strip()]
    if not chain:
        return
    tname = str(tool_name or "").strip()
    if tname not in chain:
        return
    counts_attr = f"{prefix}_grounding_exec_counts_json"
    counts_raw = getattr(state, counts_attr, "{}") or "{}"
    try:
        counts = json.loads(counts_raw)
        if not isinstance(counts, dict):
            counts = {}
    except Exception:
        counts = {}
    counts[tname] = int(counts.get(tname, 0)) + 1
    setattr(state, counts_attr, json.dumps(counts, ensure_ascii=False))
    parts = []
    for n in chain[:6]:
        c = int(counts.get(n, 0))
        if c > 0:
            parts.append(f"{n}({c})")
    text = " -> ".join(parts) if parts else "-"
    setattr(state, f"{prefix}_last_grounding_exec", text)
    if prefix == "agent":
        state.last_grounding_exec = text


def _add_message(role: str, content: str, is_code: bool = False, channel: str = "auto"):
    state = _get_state()
    resolved = _resolve_channel(channel)
    if resolved == "meshy":
        target = state.meshy_messages
        active_attr = "meshy_active_message_index"
    else:
        target = state.messages
        active_attr = "active_message_index"
    msg = target.add()
    msg.role = role
    msg.content = content
    msg.is_code = is_code
    setattr(state, active_attr, len(target) - 1)

    for area in bpy.context.screen.areas:
        area.tag_redraw()


# Classes to register (ChatMessage and TodoItem must be before AgentState).
STATE_CLASSES = [ChatMessage, TodoItem, AgentState]
