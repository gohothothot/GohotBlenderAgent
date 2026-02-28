"""
Blender Agent Chat UI - 侧边栏 + 弹窗双模式对话界面
"""

import bpy
import json
import os
import re
import time
import base64
import mimetypes
from datetime import datetime
from bpy.props import StringProperty, CollectionProperty, IntProperty, BoolProperty, EnumProperty, FloatProperty
from bpy.types import PropertyGroup, Operator, Panel, AddonPreferences, UIList


class BlenderAgentPreferences(AddonPreferences):
    bl_idname = __package__

    api_base: StringProperty(
        name="API 地址",
        description="Claude API 地址（如 https://api.anthropic.com 或中转地址）",
        default="https://api.anthropic.com",
    )

    api_key: StringProperty(
        name="API Key",
        description="你的 Claude API Key",
        default="",
        subtype='PASSWORD',
    )

    model: EnumProperty(
        name="模型",
        description="选择使用的模型",
        items=[
            ("claude-sonnet-4-5", "Claude Sonnet 4.5", "平衡性能和速度"),
            ("claude-sonnet-4-6", "Claude Sonnet 4.6", "最新 Sonnet"),
            ("claude-sonnet-4-5-kiro", "Claude Sonnet 4.5 Kiro", "Kiro 优化版"),
            ("claude-opus-4-5-kiro", "Claude Opus 4.5 Kiro", "Opus Kiro"),
            ("claude-opus-4-6-kiro", "Claude Opus 4.6 Kiro", "最新 Opus Kiro"),
            ("claude-opus-4-5-gemini", "Claude Opus 4.5 Gemini", "Opus Gemini 混合"),
            ("claude-haiku-4-5", "Claude Haiku 4.5", "最快速度"),
            ("gpt-5.2-codex", "GPT-5.2 Codex", "代码专精"),
            ("gpt-5.3-codex", "GPT-5.3 Codex", "400K上下文 代码专精"),
            ("gemini-3-flash-preview", "Gemini 3 Flash", "1M上下文 快速"),
            ("gemini-3-pro-preview", "Gemini 3 Pro", "1M上下文 强性能"),
            ("gemini-3-pro-image-preview", "Gemini 3 Pro Image", "支持图片输出"),
            ("glm-5", "GLM-5", "智谱最新"),
        ],
        default="claude-sonnet-4-5",
    )

    custom_model: StringProperty(
        name="自定义模型",
        description="如果使用中转API，可以填写自定义模型名称（留空则使用上方选择）",
        default="",
    )

    agent_mode: EnumProperty(
        name="Agent 模式",
        description="选择 Agent 工具调用模式",
        items=[
            ("native", "Native Tool Use", "使用 API 原生 tool_use（Anthropic/OpenAI 标准）"),
            ("structured", "Structured XML", "LLM 生成文本 + XML 标签，外部解析器触发工具（更省 token，兼容性更好）"),
        ],
        default="native",
    )
    conversation_mode: EnumProperty(
        name="对话通道",
        description="聊天框执行通道：Agent 负责 MCP 操作，Meshy 负责模型生成与导入",
        items=[
            ("llm_agent", "Agent", "LLM Agent 对话（材质、场景、修改器、文件等 MCP 工具）"),
            ("meshy_pipeline", "Meshy", "Meshy 一站式（文生3D/图生3D/自动导入/后处理）"),
        ],
        default="llm_agent",
    )
    auto_fallback_on_no_toolcall: BoolProperty(
        name="无工具调用自动回退",
        description="当当前模式未触发任何工具调用时，自动切换到另一种模式重试一次",
        default=True,
    )
    ui_readable_mode: BoolProperty(
        name="阅读模式（大字号）",
        description="提高插件面板可读性（不影响 Blender 全局字体）",
        default=True,
    )
    ui_scale_factor: FloatProperty(
        name="阅读缩放",
        description="面板控件纵向缩放，建议 1.1~1.5",
        default=1.2,
        min=1.0,
        max=1.8,
    )
    ui_theme_preset: EnumProperty(
        name="主题预设",
        description="插件界面风格预设（Catppuccin 低对比风格）",
        items=[
            ("system", "跟随系统", "使用 Blender 当前主题"),
            ("catppuccin_latte", "Catppuccin Latte", "浅色、柔和低对比"),
            ("catppuccin_frappe", "Catppuccin Frappe", "中暗、柔和低对比"),
            ("catppuccin_macchiato", "Catppuccin Macchiato", "暗色、柔和低对比"),
            ("catppuccin_mocha", "Catppuccin Mocha", "深暗、柔和低对比"),
        ],
        default="catppuccin_mocha",
    )

    ai_permission_level: EnumProperty(
        name="AI 权限级别",
        description="控制 Agent 执行 MCP 工具时的默认权限强度",
        items=[
            ("high", "高权限（推荐）", "默认放行大多数工具，仅高风险工具可选确认"),
            ("balanced", "平衡", "中高风险工具执行前询问"),
            ("conservative", "保守", "拦截高风险工具，仅放行低风险工具"),
        ],
        default="high",
    )

    confirm_high_risk_tools: BoolProperty(
        name="高风险工具执行前确认",
        description="高风险操作（删除、清空等）执行前弹窗确认",
        default=True,
    )

    allow_destructive_tools: BoolProperty(
        name="允许破坏性工具",
        description="允许删除对象、清空节点等不可逆操作",
        default=True,
    )

    allow_file_write_tools: BoolProperty(
        name="允许文件写入工具",
        description="允许 file_write 等写盘操作",
        default=True,
    )

    allow_network_tools: BoolProperty(
        name="允许网络/Meshy工具",
        description="允许联网检索、网页分析与 Meshy 调用",
        default=True,
    )


    meshy_api_key: StringProperty(
        name="Meshy API Key",
        description="你的 Meshy AI API Key（从 meshy.ai 获取）",
        default="",
        subtype='PASSWORD',
    )

    meshy_ai_model: EnumProperty(
        name="Meshy 模型",
        description="Meshy AI 生成模型版本",
        items=[
            ("meshy-6", "Meshy 6", "最新版本，质量最好"),
            ("meshy-5", "Meshy 5", "上一代版本"),
        ],
        default="meshy-6",
    )
    meshy_auto_postprocess: BoolProperty(
        name="Meshy导入后自动材质优化",
        description="模型导入后自动做一轮稳定的材质高光/粗糙度优化，便于后续继续编辑",
        default=True,
    )
    meshy_postprocess_preset: EnumProperty(
        name="Meshy材质优化预设",
        description="导入后自动材质优化风格",
        items=[
            ("realistic", "写实", "通用写实微调"),
            ("toon", "卡通", "更平滑、低高光、偏NPR"),
            ("metal", "金属", "高金属度、低粗糙度反射"),
            ("glass", "玻璃", "高透射、低粗糙度、IOR优化"),
        ],
        default="realistic",
    )
    meshy_postprocess_strength: EnumProperty(
        name="Meshy材质优化强度",
        description="后处理参数应用强度",
        items=[
            ("light", "轻度", "小幅微调，尽量保留原始材质"),
            ("medium", "中度", "平衡微调"),
            ("strong", "强", "更明显的风格强化"),
        ],
        default="medium",
    )

    def draw(self, context):
        layout = self.layout

        layout.label(text="🤖 Claude API 配置", icon='PREFERENCES')
        box = layout.box()
        box.prop(self, "api_base")
        box.prop(self, "api_key")
        box.prop(self, "model")
        box.prop(self, "custom_model")

        if not self.api_key:
            box.label(text="⚠️ 请填写 Claude API Key 才能使用 AI 助手", icon='ERROR')

        layout.separator()
        layout.label(text="⚙️ Agent 设置", icon='TOOL_SETTINGS')
        box = layout.box()
        box.prop(self, "conversation_mode")
        box.prop(self, "agent_mode")
        box.prop(self, "auto_fallback_on_no_toolcall")
        box.prop(self, "ui_readable_mode")
        if self.ui_readable_mode:
            box.prop(self, "ui_scale_factor")
        box.prop(self, "ui_theme_preset")
        if self.agent_mode == "structured":
            box.label(text="ℹ️ XML 模式：LLM 生成文本 + XML 标签，更省 token", icon='INFO')
        layout.separator()
        layout.label(text="🔐 权限控制", icon='LOCKED')
        sec = layout.box()
        sec.prop(self, "ai_permission_level")
        sec.prop(self, "confirm_high_risk_tools")
        sec.prop(self, "allow_destructive_tools")
        sec.prop(self, "allow_file_write_tools")
        sec.prop(self, "allow_network_tools")
        sec.label(text="说明：高风险操作会先请求授权，授权后自动继续。", icon='INFO')

        layout.separator()

        layout.label(text="🎨 Meshy AI 配置", icon='MESH_MONKEY')
        box = layout.box()
        box.prop(self, "meshy_api_key")
        box.prop(self, "meshy_ai_model")
        box.prop(self, "meshy_auto_postprocess")
        if self.meshy_auto_postprocess:
            box.prop(self, "meshy_postprocess_preset")
            box.prop(self, "meshy_postprocess_strength")

        if not self.meshy_api_key:
            box.label(text="⚠️ 请填写 Meshy API Key 才能使用 3D 生成功能", icon='INFO')
            box.operator("wm.url_open", text="获取 Meshy API Key", icon='URL').url = "https://www.meshy.ai/settings/api"


def get_preferences():
    return bpy.context.preferences.addons[__package__].preferences


# ========== 数据模型 ==========


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
    todos: CollectionProperty(type=TodoItem)
    active_todo_index: IntProperty(name="Active Todo", default=0)
    input_text: StringProperty(name="Input", default="")
    is_processing: BoolProperty(name="Processing", default=False)
    pending_code: StringProperty(name="Pending Code", default="")
    pending_code_desc: StringProperty(name="Pending Code Desc", default="")
    pending_permission_tool: StringProperty(name="Pending Permission Tool", default="")
    pending_permission_args: StringProperty(name="Pending Permission Args", default="")
    pending_permission_risk: StringProperty(name="Pending Permission Risk", default="")
    pending_permission_reason: StringProperty(name="Pending Permission Reason", default="")
    pending_tool_id: StringProperty(name="Pending Tool ID", default="")
    last_user_message: StringProperty(name="Last User Message", default="")
    last_exec_status: StringProperty(name="Last Exec Status", default="idle")
    last_exec_mode: StringProperty(name="Last Exec Mode", default="")
    last_route_hint: StringProperty(name="Last Route Hint", default="-")
    last_stall_reason: StringProperty(name="Last Stall Reason", default="-")
    fallback_attempted: BoolProperty(name="Fallback Attempted", default=False)
    request_had_tool_call: BoolProperty(name="Request Had Tool Call", default=False)
    pseudo_fallback_hits: IntProperty(name="Pseudo Fallback Hits", default=0)
    continuation_notice_shown: BoolProperty(name="Continuation Notice Shown", default=False)
    continuation_started_at: FloatProperty(name="Continuation Started At", default=0.0)
    todo_input: StringProperty(name="Todo Input", default="")
    todo_type_input: EnumProperty(
        name="Todo Type",
        items=[
            ("USER", "👤 用户", "用户自己要做的事"),
            ("AGENT", "🤖 Agent", "让 Agent 去做的事"),
        ],
        default="USER",
    )


# ========== Agent 实例管理 ==========

_agents_cache = {}


def _bind_agent_callbacks(agent):
    agent.on_message = _on_agent_message
    agent.on_tool_call = _on_tool_call
    agent.on_error = _on_error
    agent.on_plan = _on_plan
    agent.on_permission_request = _on_permission_request


def get_agent(mode_override: str = ""):
    global _agents_cache
    prefs = get_preferences()

    if not prefs.api_key:
        return None

    model = prefs.custom_model if prefs.custom_model else prefs.model
    mode = mode_override or prefs.agent_mode
    config_key = f"{prefs.api_base}|{prefs.api_key}|{model}|{mode}"

    if config_key not in _agents_cache:
        from .core.llm import LLMConfig

        config = LLMConfig(
            api_base=prefs.api_base,
            api_key=prefs.api_key,
            model=model,
        )

        if mode == "structured":
            from .core.structured_agent import StructuredAgent
            agent = StructuredAgent(config=config)
        else:
            from .core.agent import BlenderAgent
            agent = BlenderAgent(config=config)

        _bind_agent_callbacks(agent)
        _agents_cache[config_key] = agent

    return _agents_cache.get(config_key)


def _fallback_mode(mode: str) -> str:
    return "structured" if mode == "native" else "native"


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


def _extract_first_url(text: str) -> str:
    m = re.search(r"https?://[^\s)>\]\"']+", text or "", flags=re.IGNORECASE)
    return m.group(0) if m else ""


def _parse_meshy_request(user_msg: str):
    msg = (user_msg or "").strip()
    lowered = msg.lower()
    if not msg:
        return None, None

    meshy_markers = ("meshy", "文生3d", "图生3d", "text to 3d", "image to 3d")
    generation_markers = ("生成", "创建模型", "文生", "图生", "create model", "generate", "to 3d")
    image_markers = ("图生", "图片", "参考图", "image", "photo", "根据这张图")

    if not any(k in lowered for k in meshy_markers):
        return None, "当前是 Meshy 模式，仅支持文生3D/图生3D。请切换到 Agent 模式执行材质/场景/MCP 操作。"

    url = _extract_first_url(msg)
    if (any(k in lowered for k in image_markers)) and (not url):
        return None, "检测到图生3D意图，但未提供图片URL。请用“图生3D（导入图片）”按钮上传本地图片。"
    if url and any(k in lowered for k in image_markers):
        return ("meshy_image_to_3d", {"image_url": url}), None

    if not any(k in lowered for k in generation_markers):
        return None, "当前是 Meshy 模式，仅支持模型生成请求（文生/图生）。该请求请切到 Agent 模式。"

    prompt = msg.replace(url, "").strip() if url else msg
    if not prompt:
        prompt = "a realistic 3d model"
    return ("meshy_text_to_3d", {"prompt": prompt, "refine": True}), None


def _send_meshy_pipeline(user_msg: str) -> bool:
    from . import tool_definitions

    state = _get_state()
    parsed, reject = _parse_meshy_request(user_msg)
    if parsed is None:
        state.is_processing = False
        state.last_exec_status = "error"
        _add_message("system", f"❌ Meshy 模式: {reject}")
        return False

    tool_name, arguments = parsed
    state.is_processing = True
    state.last_exec_mode = "meshy"
    state.last_route_hint = "Meshy生成"
    _on_tool_call(tool_name, arguments)
    result = tool_definitions.execute_tool(tool_name, arguments)

    if result.get("success") and result.get("result") == "NEEDS_PERMISSION_CONFIRMATION":
        _on_permission_request(
            result.get("tool_name") or tool_name,
            result.get("arguments") or arguments,
            result.get("risk", "high"),
            result.get("reason", "需要确认"),
        )
        return True

    if result.get("success"):
        msg = result.get("result")
        if not isinstance(msg, str):
            msg = json.dumps(msg, ensure_ascii=False)
        _add_message("assistant", msg)
        state.last_exec_status = "ok"
    else:
        err = result.get("error", "Meshy 调用失败")
        _add_message("system", f"❌ Meshy 模式错误: {err}")
        state.last_exec_status = "error"

    state.is_processing = False
    return bool(result.get("success"))


def _send_message_with_mode(user_msg: str, mode: str):
    prefs = get_preferences()
    if getattr(prefs, "conversation_mode", "llm_agent") == "meshy_pipeline":
        return _send_meshy_pipeline(user_msg)
    agent = get_agent(mode_override=mode)
    if agent is None:
        return False
    state = _get_state()
    state.is_processing = True
    state.last_exec_mode = mode
    agent.send_message(user_msg)
    return True


def _draw_health_badge(layout, state: AgentState):
    status = state.last_exec_status or "idle"
    mode = state.last_exec_mode or "-"
    if status == "ok":
        layout.label(text=f"工具执行状态: 正常（模式: {mode}）", icon="CHECKMARK")
    elif status == "fallback_running":
        layout.label(text=f"工具执行状态: 回退重试中（模式: {mode}）", icon="FILE_REFRESH")
    elif status in ("no_toolcall", "error"):
        layout.label(text=f"工具执行状态: 未执行工具（模式: {mode}）", icon="ERROR")
    elif status == "error_after_toolcall":
        layout.label(text=f"工具执行状态: 已执行工具但后续失败（模式: {mode}）", icon="ERROR")
    elif status == "processing":
        layout.label(text=f"工具执行状态: 执行中（模式: {mode}）", icon="SORTTIME")
        layout.label(text="提示: AI 可能在继续执行后续步骤，请先等待或点击中止。", icon="INFO")
    else:
        layout.label(text="工具执行状态: 待机", icon="INFO")
    try:
        prefs = get_preferences()
        layout.label(text=f"界面主题: {_theme_hint(prefs)}", icon="COLOR")
        cmode = getattr(prefs, "conversation_mode", "llm_agent")
        layout.label(text=f"对话通道: {'Meshy' if cmode == 'meshy_pipeline' else 'Agent'}", icon="INFO")
    except Exception:
        pass
    layout.label(text=f"本轮路由判定: {state.last_route_hint or '-'}", icon="OUTLINER")
    layout.label(text=f"最近卡住原因: {state.last_stall_reason or '-'}", icon="INFO")
    if int(getattr(state, "pseudo_fallback_hits", 0)) > 0:
        layout.label(text=f"伪调用兜底命中: {int(state.pseudo_fallback_hits)} 次", icon="INFO")


def _draw_quick_actions(layout, popup: bool = False):
    row = layout.row(align=True)
    row.operator("agent.open_settings", text="设置", icon="PREFERENCES")
    if popup:
        row.operator("agent.view_performance_report", text="性能", icon="GRAPH")
        row.operator("agent.export_performance_report", text="", icon="EXPORT")
    else:
        row.operator("agent.open_chat", text="弹窗", icon="WINDOW")
        row.operator("agent.view_performance_report", text="性能", icon="GRAPH")
        row.operator("agent.export_performance_report", text="", icon="EXPORT")


def _theme_label(prefs) -> str:
    mapping = {
        "system": "System",
        "catppuccin_latte": "Latte",
        "catppuccin_frappe": "Frappe",
        "catppuccin_macchiato": "Macchiato",
        "catppuccin_mocha": "Mocha",
    }
    return mapping.get(getattr(prefs, "ui_theme_preset", "system"), "System")


def _theme_hint(prefs) -> str:
    preset = getattr(prefs, "ui_theme_preset", "system")
    if preset == "system":
        return "跟随 Blender 主题"
    return f"Catppuccin · {_theme_label(prefs)} · Soft"


def _theme_mark(prefs) -> str:
    preset = getattr(prefs, "ui_theme_preset", "system")
    marks = {
        "system": "•",
        "catppuccin_latte": "☼",
        "catppuccin_frappe": "◐",
        "catppuccin_macchiato": "◑",
        "catppuccin_mocha": "☾",
    }
    return marks.get(preset, "•")


def _is_mocha(prefs) -> bool:
    return getattr(prefs, "ui_theme_preset", "system") == "catppuccin_mocha"


def _section_title(box, title: str, icon: str = "INFO", subtitle: str = ""):
    row = box.row(align=True)
    row.label(text=title, icon=icon)
    if subtitle:
        row.label(text=subtitle)


def _scaled_container(layout, prefs):
    container = layout.column(align=False)
    if getattr(prefs, "ui_readable_mode", False):
        container.scale_y = max(1.0, float(getattr(prefs, "ui_scale_factor", 1.2)))
    return container


def _draw_mode_switch(layout, prefs):
    row = layout.row(align=True)
    if hasattr(prefs, "conversation_mode"):
        row.prop(prefs, "conversation_mode", expand=True)
    else:
        # 兼容热更新/旧RNA缓存：属性未注册时降级显示，避免整块UI绘制失败
        row.label(text="Agent | Meshy（请重载插件）", icon="INFO")


def _execute_in_main_thread(func, *args):
    """在 Blender 主线程执行函数"""
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

def _get_state() -> AgentState:
    return bpy.context.scene.blender_agent


def _add_message(role: str, content: str, is_code: bool = False):
    state = _get_state()
    msg = state.messages.add()
    msg.role = role
    msg.content = content
    msg.is_code = is_code
    state.active_message_index = len(state.messages) - 1

    for area in bpy.context.screen.areas:
        area.tag_redraw()


def push_system_notice(content: str):
    """供外部模块（如 Meshy 回调）安全推送系统消息到聊天面板。"""
    try:
        _add_message("system", content)
    except Exception:
        pass


def _schedule_processing_timeout_check(started_at: float, timeout_sec: float = 12.0):
    """继续执行提示的兜底超时：长时间无后续回调时自动结束等待态。"""

    def _check():
        try:
            state = _get_state()
            if not state.is_processing:
                return None
            current = float(getattr(state, "continuation_started_at", 0.0) or 0.0)
            if current <= 0.0 or abs(current - started_at) > 1e-6:
                return None
            if (time.time() - started_at) < timeout_sec:
                return 1.0
            state.is_processing = False
            if state.last_exec_status == "processing":
                state.last_exec_status = "ok" if state.request_had_tool_call else "error"
            state.continuation_started_at = 0.0
            state.last_stall_reason = "超时自动收口"
            _add_message("system", "⏱ 提醒：长时间未收到后续执行结果，已自动结束等待。可继续发送。")
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
        from .core.safety_guard import references_foreign_toolset
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


def _on_agent_message(role: str, content: str):
    if role == "assistant" and _looks_like_identity_drift_text(content):
        _on_error("[WRONG_TOOLSET] 检测到模型身份漂移文本，已拦截并触发重试。")
        return
    _add_message(role, content)
    state = _get_state()
    if role != "assistant":
        return

    # 防止“中间总结文本”被误判为结束：仅当明显是最终总结时才结束处理态
    is_final = True
    try:
        from .core.safety_guard import looks_like_final_summary
        is_final = looks_like_final_summary(content)
    except Exception:
        is_final = True

    if not is_final and (state.request_had_tool_call or state.last_exec_status in ("processing", "fallback_running")):
        state.is_processing = True
        state.last_exec_status = "processing"
        state.last_stall_reason = "继续执行中"
        state.continuation_started_at = time.time()
        _schedule_processing_timeout_check(state.continuation_started_at, timeout_sec=12.0)
        if not state.continuation_notice_shown:
            state.continuation_notice_shown = True
            _add_message("system", "⏳ 提醒：AI 还在继续执行后续步骤，不要急着发送下一条。若要打断请点“中止”。")
        return

    state.is_processing = False
    state.continuation_started_at = 0.0
    state.last_stall_reason = "-"


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
    if shown_name.startswith("meshy_"):
        state.last_route_hint = "Meshy生成"
    elif shown_name.startswith("shader_"):
        state.last_route_hint = "材质编辑"
    elif shown_name.startswith("scene_"):
        state.last_route_hint = "场景编辑"
    else:
        state.last_route_hint = "常规MCP"
    args_preview = json.dumps(args, ensure_ascii=False)[:200] if args else ""
    _add_message("system", f"🔧 调用工具: {shown_name}\n{args_preview}")


def _on_plan(plan_text: str):
    _add_message("system", f"📋 {plan_text}")

def _on_code_confirm(code: str, description: str, callback):
    state = _get_state()
    state.pending_code = code
    state.pending_code_desc = description
    state.is_processing = False

    global _pending_callback
    _pending_callback = callback

    _add_message("system", f"⚠️ 请确认执行以下代码:\n{description}")

    for area in bpy.context.screen.areas:
        area.tag_redraw()


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
            _add_message("system", f"♻️ 检测到模型工具集漂移，自动切换到 {retry_mode} 模式重试一次。")
        else:
            _add_message("system", f"♻️ 当前模式未触发工具调用，自动切换到 {retry_mode} 模式重试一次。")
        if _send_message_with_mode(state.last_user_message, retry_mode):
            return
        _add_message("system", "❌ 自动回退失败：无法创建回退 Agent 实例。")

    _add_message("system", f"❌ 错误: {error}")
    state.is_processing = False
    state.continuation_started_at = 0.0
    if no_toolcall_error:
        state.last_exec_status = "no_toolcall"
        state.last_stall_reason = "无工具调用"
    elif wrong_toolset_error:
        state.last_stall_reason = "工具集漂移"
    else:
        state.last_exec_status = "error_after_toolcall" if state.request_had_tool_call else "error"
        state.last_stall_reason = "一般错误"


def _on_permission_request(tool_name: str, args: dict, risk: str, reason: str):
    state = _get_state()
    state.pending_permission_tool = tool_name or ""
    state.pending_permission_args = json.dumps(args or {}, ensure_ascii=False)
    state.pending_permission_risk = risk or "high"
    state.pending_permission_reason = reason or "该操作需要授权"
    state.is_processing = False
    state.last_stall_reason = "权限等待"
    _add_message(
        "system",
        f"🔐 需要权限确认：{state.pending_permission_tool}（风险: {state.pending_permission_risk}）\n{state.pending_permission_reason}\n请点击“允许一次”或“拒绝”。",
    )


_pending_callback = None


def _build_performance_report_lines(max_sessions: int = 5) -> list:
    lines = []
    try:
        from . import action_log
        logs = action_log.get_recent_logs(max_sessions)
        if not logs:
            return ["暂无性能日志。先执行几次任务后再查看。"]

        lines.append(f"最近 {len(logs)} 次会话性能摘要")
        lines.append("-" * 60)
        for log in logs:
            sid = log.get("session_id", "?")
            req = (log.get("user_request", "") or "").replace("\n", " ")[:80]
            brief = log.get("performance_brief", "无性能摘要")
            lines.append(f"[{sid}] {req}")
            lines.append(f"  {brief}")
            lines.append("")
        return lines
    except Exception as e:
        return [f"读取性能日志失败: {e}"]


# ========== UIList ==========


class AGENT_UL_MessageList(UIList):
    bl_idname = "AGENT_UL_message_list"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)

            if item.role == "user":
                row.label(text="", icon='USER')
            elif item.role == "assistant":
                row.label(text="", icon='OUTLINER_OB_LIGHT')
            else:
                if "❌" in item.content or "错误" in item.content:
                    row.label(text="", icon='ERROR')
                elif "🔧" in item.content or "调用工具" in item.content:
                    row.label(text="", icon='TOOL_SETTINGS')
                else:
                    row.label(text="", icon='INFO')

            content_preview = item.content.replace('\n', ' ')[:200]
            row.label(text=content_preview)

            op = row.operator("agent.copy_message", text="", icon='COPYDOWN')
            op.index = index

            if len(item.content) > 100:
                op2 = row.operator("agent.view_full_message", text="", icon='TEXT')
                op2.index = index

        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon='CONSOLE')


# ========== Operators ==========


class AGENT_OT_SendMessage(Operator):
    bl_idname = "agent.send_message"
    bl_label = "发送"

    def execute(self, context):
        state = _get_state()

        if not state.input_text.strip():
            return {"CANCELLED"}

        if state.is_processing:
            self.report({"WARNING"}, "Agent 正在处理中...")
            return {"CANCELLED"}

        prefs = get_preferences()
        mode_kind = getattr(prefs, "conversation_mode", "llm_agent")
        if mode_kind == "llm_agent":
            if get_agent(mode_override=prefs.agent_mode) is None:
                self.report({"ERROR"}, "请先在插件设置中配置 API Key")
                return {"CANCELLED"}
        else:
            if not getattr(prefs, "meshy_api_key", ""):
                self.report({"ERROR"}, "请先在插件设置中配置 Meshy API Key")
                return {"CANCELLED"}

        user_msg = state.input_text.strip()
        _add_message("user", user_msg)

        state.input_text = ""
        state.last_user_message = user_msg
        state.request_had_tool_call = False
        state.fallback_attempted = False
        state.last_exec_status = "processing"
        state.last_exec_mode = "meshy" if mode_kind == "meshy_pipeline" else prefs.agent_mode
        state.last_route_hint = "Meshy生成" if mode_kind == "meshy_pipeline" else _infer_route_hint(user_msg)
        state.pseudo_fallback_hits = 0
        state.continuation_notice_shown = False
        state.continuation_started_at = 0.0
        state.last_stall_reason = "-"
        _send_message_with_mode(user_msg, prefs.agent_mode)

        return {"FINISHED"}


class AGENT_OT_StopProcessing(Operator):
    bl_idname = "agent.stop_processing"
    bl_label = "中止"
    bl_description = "中止当前 AI 请求（网络返回后立即丢弃结果）"

    def execute(self, context):
        state = _get_state()
        for agent in list(_agents_cache.values()):
            if agent and hasattr(agent, "cancel_current_request"):
                try:
                    agent.cancel_current_request()
                except Exception:
                    pass

        state.is_processing = False
        state.last_exec_status = "idle"
        state.last_stall_reason = "用户中止"
        _add_message("system", "⏹️ 已请求中止当前任务。")
        self.report({"INFO"}, "已发送中止请求")
        return {"FINISHED"}


class AGENT_OT_ConfirmCode(Operator):
    bl_idname = "agent.confirm_code"
    bl_label = "确认执行"

    approved: BoolProperty(default=True)

    def execute(self, context):
        global _pending_callback
        state = _get_state()

        if _pending_callback:
            state.is_processing = True
            _pending_callback(self.approved)
            _pending_callback = None

        state.pending_code = ""
        state.pending_code_desc = ""

        if self.approved:
            _add_message("system", "✅ 代码已执行")
        else:
            _add_message("system", "🚫 已取消执行")

        return {"FINISHED"}


class AGENT_OT_ConfirmPermission(Operator):
    bl_idname = "agent.confirm_permission"
    bl_label = "确认权限"

    approved: BoolProperty(default=True)

    def execute(self, context):
        state = _get_state()
        tool_name = state.pending_permission_tool
        args_text = state.pending_permission_args or "{}"
        args = {}
        try:
            args = json.loads(args_text)
        except Exception:
            args = {}

        if self.approved and tool_name:
            try:
                from .permission_guard import approve_tool_once
                approve_tool_once(tool_name, args)
            except Exception as e:
                self.report({"ERROR"}, f"授权失败: {e}")
                return {"CANCELLED"}

            if state.last_exec_mode == "meshy":
                _add_message("system", f"✅ 已授权一次：{tool_name}。Meshy 流程继续执行。")
                try:
                    from . import tool_definitions
                    state.is_processing = True
                    state.last_exec_status = "processing"
                    result = tool_definitions.execute_tool(tool_name, args)
                    if result.get("success"):
                        msg = result.get("result")
                        if not isinstance(msg, str):
                            msg = json.dumps(msg, ensure_ascii=False)
                        _add_message("assistant", msg)
                        state.last_exec_status = "ok"
                    else:
                        _add_message("system", f"❌ Meshy 模式错误: {result.get('error', '执行失败')}")
                        state.last_exec_status = "error"
                finally:
                    state.is_processing = False
            else:
                _add_message("system", f"✅ 已授权一次：{tool_name}。Agent 将继续执行。")
                resume_mode = state.last_exec_mode or get_preferences().agent_mode
                agent = get_agent(mode_override=resume_mode)
                if agent:
                    state.is_processing = True
                    state.last_exec_status = "processing"
                    resume_prompt = (
                        f"权限已批准。请继续完成刚才任务。"
                        f"你对工具 {tool_name} 使用参数 {args_text} 已获得一次性授权，"
                        "请立即调用 MCP 工具并继续后续步骤。"
                    )
                    agent.send_message(resume_prompt)
        else:
            _add_message("system", f"🚫 已拒绝授权：{tool_name or '未知工具'}")

        state.pending_permission_tool = ""
        state.pending_permission_args = ""
        state.pending_permission_risk = ""
        state.pending_permission_reason = ""
        return {"FINISHED"}


class AGENT_OT_ClearHistory(Operator):
    bl_idname = "agent.clear_history"
    bl_label = "清空对话"

    def execute(self, context):
        global _agents_cache
        state = _get_state()
        state.messages.clear()

        for agent in list(_agents_cache.values()):
            try:
                agent.clear_history()
            except Exception:
                pass

        _add_message("system", "对话已清空，开始新对话")
        return {"FINISHED"}


class AGENT_OT_OpenSettings(Operator):
    bl_idname = "agent.open_settings"
    bl_label = "打开设置"

    def execute(self, context):
        bpy.ops.preferences.addon_show(module=__package__)
        return {"FINISHED"}


class AGENT_OT_CopyMessage(Operator):
    bl_idname = "agent.copy_message"
    bl_label = "复制消息"
    bl_description = "复制消息内容到剪贴板"

    index: IntProperty()

    def execute(self, context):
        state = _get_state()
        messages = list(state.messages)
        if 0 <= self.index < len(messages):
            context.window_manager.clipboard = messages[self.index].content
            self.report({'INFO'}, "已复制到剪贴板")
        return {'FINISHED'}


class AGENT_OT_ViewFullMessage(Operator):
    bl_idname = "agent.view_full_message"
    bl_label = "查看完整消息"
    bl_description = "在弹窗中查看完整消息内容"

    index: IntProperty()

    def execute(self, context):
        return context.window_manager.invoke_props_dialog(self, width=600)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=600)

    def draw(self, context):
        layout = self.layout
        state = _get_state()
        messages = list(state.messages)
        if 0 <= self.index < len(messages):
            msg = messages[self.index]
            if msg.role == "user":
                layout.label(text="👤 你的消息", icon='USER')
            elif msg.role == "assistant":
                layout.label(text="🤖 AI 回复", icon='OUTLINER_OB_LIGHT')
            else:
                layout.label(text="ℹ️ 系统消息", icon='INFO')

            layout.separator()

            box = layout.box()
            col = box.column(align=True)
            lines = msg.content.split('\n')
            for line in lines:
                while len(line) > 100:
                    col.label(text=line[:100])
                    line = line[100:]
                col.label(text=line if line else " ")

            layout.separator()
            op = layout.operator("agent.copy_message", text="📋 复制全部内容", icon='COPYDOWN')
            op.index = self.index


class AGENT_OT_AddTodo(Operator):
    bl_idname = "agent.add_todo"
    bl_label = "添加 TODO"

    def execute(self, context):
        state = _get_state()
        text = state.todo_input.strip()
        if not text:
            return {"CANCELLED"}
        item = state.todos.add()
        item.content = text
        item.todo_type = state.todo_type_input
        item.done = False
        state.todo_input = ""
        state.active_todo_index = len(state.todos) - 1
        for area in context.screen.areas:
            area.tag_redraw()
        return {"FINISHED"}


class AGENT_OT_RemoveTodo(Operator):
    bl_idname = "agent.remove_todo"
    bl_label = "删除 TODO"

    index: IntProperty()

    def execute(self, context):
        state = _get_state()
        if 0 <= self.index < len(state.todos):
            state.todos.remove(self.index)
            if state.active_todo_index >= len(state.todos):
                state.active_todo_index = max(0, len(state.todos) - 1)
        for area in context.screen.areas:
            area.tag_redraw()
        return {"FINISHED"}


class AGENT_OT_ToggleTodo(Operator):
    bl_idname = "agent.toggle_todo"
    bl_label = "切换完成状态"

    index: IntProperty()

    def execute(self, context):
        state = _get_state()
        if 0 <= self.index < len(state.todos):
            state.todos[self.index].done = not state.todos[self.index].done
        for area in context.screen.areas:
            area.tag_redraw()
        return {"FINISHED"}


class AGENT_OT_SendTodoToAgent(Operator):
    bl_idname = "agent.send_todo_to_agent"
    bl_label = "让 Agent 执行"

    index: IntProperty()

    def execute(self, context):
        state = _get_state()
        if 0 <= self.index < len(state.todos):
            todo = state.todos[self.index]
            if state.is_processing:
                self.report({"WARNING"}, "Agent 正在处理中...")
                return {"CANCELLED"}
            prefs = get_preferences()
            mode_kind = getattr(prefs, "conversation_mode", "llm_agent")
            if mode_kind == "llm_agent":
                if get_agent(mode_override=prefs.agent_mode) is None:
                    self.report({"ERROR"}, "请先配置 API Key")
                    return {"CANCELLED"}
            else:
                if not getattr(prefs, "meshy_api_key", ""):
                    self.report({"ERROR"}, "请先配置 Meshy API Key")
                    return {"CANCELLED"}
            msg = f"请帮我完成这个任务：{todo.content}"
            _add_message("user", msg)
            state.last_user_message = msg
            state.request_had_tool_call = False
            state.fallback_attempted = False
            state.last_exec_status = "processing"
            state.last_exec_mode = "meshy" if mode_kind == "meshy_pipeline" else prefs.agent_mode
            state.last_route_hint = "Meshy生成" if mode_kind == "meshy_pipeline" else _infer_route_hint(msg)
            state.pseudo_fallback_hits = 0
            state.continuation_notice_shown = False
            state.continuation_started_at = 0.0
            state.last_stall_reason = "-"
            _send_message_with_mode(msg, prefs.agent_mode)
        return {"FINISHED"}


class AGENT_OT_MeshyImageTo3DUpload(Operator):
    bl_idname = "agent.meshy_image_to_3d_upload"
    bl_label = "图生3D（导入图片）"
    bl_description = "选择本地图片并直接调用 Meshy 图生3D"

    filepath: StringProperty(subtype="FILE_PATH")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        state = _get_state()
        if state.is_processing:
            self.report({"WARNING"}, "Agent 正在处理中，请稍后")
            return {"CANCELLED"}

        if not self.filepath or not os.path.isfile(self.filepath):
            self.report({"ERROR"}, "请选择有效图片文件")
            return {"CANCELLED"}

        try:
            with open(self.filepath, "rb") as f:
                raw = f.read()
            if not raw:
                self.report({"ERROR"}, "图片文件为空")
                return {"CANCELLED"}

            mime, _ = mimetypes.guess_type(self.filepath)
            if not mime or not mime.startswith("image/"):
                ext = os.path.splitext(self.filepath)[1].lower()
                mime = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".webp": "image/webp",
                    ".gif": "image/gif",
                    ".bmp": "image/bmp",
                }.get(ext, "image/png")

            b64 = base64.b64encode(raw).decode("ascii")
            data_uri = f"data:{mime};base64,{b64}"

            _add_message("user", f"🖼️ 图生3D上传图片: {os.path.basename(self.filepath)}")
            state.is_processing = True
            state.last_exec_status = "processing"
            state.last_exec_mode = "meshy"
            state.continuation_notice_shown = False
            _on_tool_call("meshy_image_to_3d", {"image_url": f"data-uri://local-upload ({len(raw)} bytes)"})

            from . import tool_definitions
            # 这里已经在 Blender 主线程中，直接调用可避免 30s 队列等待超时
            result = tool_definitions.execute_tool(
                "meshy_image_to_3d",
                {"image_url": data_uri},
            )

            if result.get("success"):
                msg = result.get("result")
                if not isinstance(msg, str):
                    msg = json.dumps(msg, ensure_ascii=False)
                _add_message("assistant", msg)
                state.last_exec_status = "ok"
                self.report({"INFO"}, "已创建 Meshy 图生3D 任务")
            else:
                err = result.get("error", "调用 Meshy 图生3D 失败")
                _on_error(f"Meshy 图生3D失败: {err}")
                self.report({"ERROR"}, str(err)[:120])
        except Exception as e:
            _on_error(f"图生3D上传失败: {e}")
            self.report({"ERROR"}, f"上传失败: {e}")
            return {"CANCELLED"}
        finally:
            state.is_processing = False

        return {"FINISHED"}


class AGENT_OT_OpenChat(Operator):
    bl_idname = "agent.open_chat"
    bl_label = "打开 AI 助手"
    bl_options = {"REGISTER"}

    def execute(self, context):
        return context.window_manager.invoke_props_dialog(self, width=700)

    def draw(self, context):
        layout = self.layout
        state = _get_state()
        prefs = get_preferences()
        ui = _scaled_container(layout, prefs)

        mode_kind = getattr(prefs, "conversation_mode", "llm_agent")
        missing_key = (not prefs.api_key) if mode_kind == "llm_agent" else (not getattr(prefs, "meshy_api_key", ""))
        if missing_key:
            box = ui.box()
            tip = "⚠️ 请先配置 API Key" if mode_kind == "llm_agent" else "⚠️ 请先配置 Meshy API Key"
            box.label(text=tip, icon='ERROR')
            box.operator("agent.open_settings", text="打开设置", icon='PREFERENCES')
            return

        header = ui.box()
        header.label(text=f"{_theme_mark(prefs)} Blender Agent", icon='OUTLINER_OB_LIGHT')
        _draw_mode_switch(header, prefs)
        _draw_health_badge(header, state)

        box = ui.box()
        _section_title(box, "会话", icon="CONSOLE", subtitle="Soft" if _is_mocha(prefs) else "")
        row = box.row(align=True)
        row.operator("agent.clear_history", text="清空", icon="TRASH")

        box.template_list(
            "AGENT_UL_message_list",
            "chat_messages_popup",
            state,
            "messages",
            state,
            "active_message_index",
            rows=8,
            maxrows=12,
        )
        if state.pending_code:
            code_box = ui.box()
            code_box.label(text="⚠️ 待确认代码:", icon="ERROR")
            code_box.label(text=state.pending_code_desc)
            code_preview = state.pending_code[:500]
            for line in code_preview.split("\n")[:10]:
                code_box.label(text=f"  {line}")
            if len(state.pending_code) > 500:
                code_box.label(text="  ...")
            row = code_box.row()
            op_yes = row.operator("agent.confirm_code", text="✅ 执行", icon="CHECKMARK")
            op_yes.approved = True
            op_no = row.operator("agent.confirm_code", text="❌ 取消", icon="X")
            op_no.approved = False

        if state.pending_permission_tool:
            perm_box = ui.box()
            perm_box.label(text="🔐 待确认高权限操作:", icon="LOCKED")
            perm_box.label(text=f"工具: {state.pending_permission_tool}")
            perm_box.label(text=f"风险: {state.pending_permission_risk}")
            perm_box.label(text=state.pending_permission_reason[:180])
            row = perm_box.row()
            op_yes = row.operator("agent.confirm_permission", text="✅ 允许一次", icon="CHECKMARK")
            op_yes.approved = True
            op_no = row.operator("agent.confirm_permission", text="❌ 拒绝", icon="X")
            op_no.approved = False

        ui.separator()

        if state.is_processing:
            row = ui.row(align=True)
            row.label(text="⏳ AI 正在思考...", icon="SORTTIME")
            row.operator("agent.stop_processing", text="中止", icon="CANCEL")
        else:
            input_box = ui.box() if _is_mocha(prefs) else ui
            if _is_mocha(prefs):
                _section_title(input_box, "输入", icon="GREASEPENCIL")
            row = input_box.row(align=True)
            row.prop(state, "input_text", text="")
            row.operator("agent.send_message", text="发送", icon="PLAY")

        ui.separator()
        actions = ui.box() if _is_mocha(prefs) else ui
        if _is_mocha(prefs):
            _section_title(actions, "操作", icon="TOOL_SETTINGS")
        _draw_quick_actions(actions, popup=True)
        actions.operator("agent.meshy_image_to_3d_upload", text="图生3D（导入图片）", icon="IMAGE_DATA")

    def invoke(self, context, event):
        prefs = get_preferences()
        if prefs.api_key:
            get_agent()

        state = _get_state()
        if len(state.messages) == 0:
            _add_message("system", "你好！我是 Blender AI 助手。在下方输入你的需求，我会直接操作 Blender 完成。")

        return context.window_manager.invoke_props_dialog(self, width=700)


# ========== N Panel 侧边栏 ==========


class AGENT_PT_MainPanel(Panel):
    bl_label = "🤖 Blender Agent"
    bl_idname = "AGENT_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Agent"

    def draw(self, context):
        layout = self.layout
        state = _get_state()
        prefs = get_preferences()
        ui = _scaled_container(layout, prefs)

        mode_kind = getattr(prefs, "conversation_mode", "llm_agent")
        missing_key = (not prefs.api_key) if mode_kind == "llm_agent" else (not getattr(prefs, "meshy_api_key", ""))
        if missing_key:
            box = ui.box()
            tip = "⚠️ 请先配置 API Key" if mode_kind == "llm_agent" else "⚠️ 请先配置 Meshy API Key"
            box.label(text=tip, icon='ERROR')
            box.operator("agent.open_settings", text="打开设置", icon='PREFERENCES')
            return

        if len(state.messages) == 0:
            ui.label(text="你好！在下方输入需求，我会直接操作 Blender。", icon='INFO')

        header = ui.box()
        header.label(text=f"{_theme_mark(prefs)} Blender Agent", icon='OUTLINER_OB_LIGHT')
        _draw_mode_switch(header, prefs)
        _draw_health_badge(header, state)

        box = ui.box()
        _section_title(box, "会话", icon='CONSOLE', subtitle="Soft" if _is_mocha(prefs) else "")
        row = box.row(align=True)
        row.operator("agent.clear_history", text="清空", icon='TRASH')

        box.template_list(
            "AGENT_UL_message_list",
            "chat_messages",
            state,
            "messages",
            state,
            "active_message_index",
            rows=8,
            maxrows=15,
        )
        if state.is_processing:
            row = ui.row(align=True)
            row.label(text="⏳ AI 正在思考...", icon='SORTTIME')
            row.operator("agent.stop_processing", text="中止", icon='CANCEL')
        else:
            input_box = ui.box() if _is_mocha(prefs) else ui
            if _is_mocha(prefs):
                _section_title(input_box, "输入", icon="GREASEPENCIL")
            row = input_box.row(align=True)
            row.prop(state, "input_text", text="")
            row.operator("agent.send_message", text="发送", icon='PLAY')

        if state.pending_code:
            code_box = ui.box()
            code_box.label(text="⚠️ 待确认代码:", icon='ERROR')
            code_box.label(text=state.pending_code_desc)
            code_preview = state.pending_code[:500]
            for line in code_preview.split("\n")[:10]:
                code_box.label(text=f"  {line}")
            if len(state.pending_code) > 500:
                code_box.label(text="  ...")
            row = code_box.row()
            op_yes = row.operator("agent.confirm_code", text="✅ 执行", icon='CHECKMARK')
            op_yes.approved = True
            op_no = row.operator("agent.confirm_code", text="❌ 取消", icon='X')
            op_no.approved = False

        if state.pending_permission_tool:
            perm_box = ui.box()
            perm_box.label(text="🔐 待确认高权限操作:", icon='LOCKED')
            perm_box.label(text=f"工具: {state.pending_permission_tool}")
            perm_box.label(text=f"风险: {state.pending_permission_risk}")
            perm_box.label(text=state.pending_permission_reason[:180])
            row = perm_box.row()
            op_yes = row.operator("agent.confirm_permission", text="✅ 允许一次", icon='CHECKMARK')
            op_yes.approved = True
            op_no = row.operator("agent.confirm_permission", text="❌ 拒绝", icon='X')
            op_no.approved = False

        actions = ui.box() if _is_mocha(prefs) else ui
        if _is_mocha(prefs):
            _section_title(actions, "操作", icon="TOOL_SETTINGS")
        _draw_quick_actions(actions, popup=False)
        actions.operator("agent.meshy_image_to_3d_upload", text="图生3D（导入图片）", icon="IMAGE_DATA")


class AGENT_OT_ViewPerformanceReport(Operator):
    bl_idname = "agent.view_performance_report"
    bl_label = "查看性能报告"
    bl_description = "查看最近会话的性能摘要（命中率、预热耗时、检索成功率）"

    def invoke(self, context, event):
        self._lines = _build_performance_report_lines(max_sessions=5)
        return context.window_manager.invoke_props_dialog(self, width=760)

    def execute(self, context):
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        col = box.column(align=True)
        for line in getattr(self, "_lines", ["暂无数据"]):
            col.label(text=line if line else " ")


class AGENT_OT_ExportPerformanceReport(Operator):
    bl_idname = "agent.export_performance_report"
    bl_label = "导出性能报告"
    bl_description = "导出最近会话性能报告到 logs 目录"

    export_format: EnumProperty(
        name="格式",
        items=[
            ("json", "JSON", "导出完整 JSON 报告"),
            ("csv", "CSV", "导出简化 CSV 报告"),
        ],
        default="json",
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=380)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "export_format")
        layout.label(text="文件将导出到插件 logs 目录", icon='INFO')

    def execute(self, context):
        try:
            from . import action_log

            logs = action_log.get_recent_logs(20)
            if not logs:
                self.report({'WARNING'}, "暂无性能日志可导出")
                return {'CANCELLED'}

            log_dir = os.path.join(os.path.dirname(__file__), "logs")
            os.makedirs(log_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")

            if self.export_format == "json":
                out_path = os.path.join(log_dir, f"performance_report_{ts}.json")
                payload = []
                for log in logs:
                    payload.append({
                        "session_id": log.get("session_id"),
                        "user_request": log.get("user_request"),
                        "performance_brief": log.get("performance_brief"),
                        "performance_summary": log.get("performance_summary", {}),
                    })
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
            else:
                out_path = os.path.join(log_dir, f"performance_report_{ts}.csv")
                header = "session_id,user_request,metric_events,prewarm_hit_rate,search_success_rate,avg_estimated_output_tokens\n"
                rows = [header]
                for log in logs:
                    summary = log.get("performance_summary", {}) or {}
                    attach = summary.get("shader_context_attach", {}) or {}
                    search = summary.get("shader_search_index_result", {}) or {}
                    plan = summary.get("shader_read_plan", {}) or {}
                    request = (log.get("user_request", "") or "").replace('"', "'").replace("\n", " ")[:120]
                    rows.append(
                        f"\"{log.get('session_id', '')}\",\"{request}\",{summary.get('metric_events', 0)},"
                        f"{attach.get('prewarm_hit_rate', 0)},{search.get('success_rate', 0)},"
                        f"{plan.get('avg_estimated_output_tokens', 0)}\n"
                    )
                with open(out_path, "w", encoding="utf-8") as f:
                    f.writelines(rows)

            self.report({'INFO'}, f"已导出: {out_path}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"导出失败: {e}")
            return {'CANCELLED'}


class AGENT_PT_TodoPanel(Panel):
    bl_label = "📋 TODO List"
    bl_idname = "AGENT_PT_todo_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Agent"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        state = _get_state()

        for i, todo in enumerate(state.todos):
            row = layout.row(align=True)
            icon = "CHECKMARK" if todo.done else "CHECKBOX_DEHLT"
            op_toggle = row.operator("agent.toggle_todo", text="", icon=icon)
            op_toggle.index = i

            type_icon = "🤖" if todo.todo_type == "AGENT" else "👤"
            strike = "✓ " if todo.done else ""
            row.label(text=f"{type_icon} {strike}{todo.content[:80]}")

            if todo.todo_type == "AGENT" and not todo.done:
                op_send = row.operator("agent.send_todo_to_agent", text="", icon='PLAY')
                op_send.index = i

            op_del = row.operator("agent.remove_todo", text="", icon='X')
            op_del.index = i

        if len(state.todos) == 0:
            layout.label(text="暂无待办事项", icon='INFO')

        add_row = layout.row(align=True)
        add_row.prop(state, "todo_type_input", text="")
        add_row.prop(state, "todo_input", text="")
        add_row.operator("agent.add_todo", text="", icon='ADD')


# ========== 注册 ==========

classes = [
    BlenderAgentPreferences,
    ChatMessage,
    TodoItem,
    AgentState,
    AGENT_UL_MessageList,
    AGENT_OT_SendMessage,
    AGENT_OT_StopProcessing,
    AGENT_OT_ConfirmCode,
    AGENT_OT_ConfirmPermission,
    AGENT_OT_ClearHistory,
    AGENT_OT_OpenSettings,
    AGENT_OT_CopyMessage,
    AGENT_OT_ViewFullMessage,
    AGENT_OT_AddTodo,
    AGENT_OT_RemoveTodo,
    AGENT_OT_ToggleTodo,
    AGENT_OT_SendTodoToAgent,
    AGENT_OT_MeshyImageTo3DUpload,
    AGENT_OT_OpenChat,
    AGENT_OT_ViewPerformanceReport,
    AGENT_OT_ExportPerformanceReport,
    AGENT_PT_MainPanel,
    AGENT_PT_TodoPanel,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.blender_agent = bpy.props.PointerProperty(type=AgentState)


def unregister():
    global _agents_cache
    _agents_cache = {}

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.blender_agent
