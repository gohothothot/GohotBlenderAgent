"""
Blender Agent Chat UI - 侧边栏 + 弹窗双模式对话界面
"""

import bpy
import json
import os
from bpy.props import StringProperty, CollectionProperty, IntProperty, BoolProperty, EnumProperty, FloatProperty
from bpy.types import PropertyGroup, Operator, Panel, AddonPreferences, UIList
from .ui.i18n import tr
from .ui.state import (
    ChatMessage,
    TodoItem,
    AgentState,
    get_preferences,
    _get_state,
    _add_message,
    is_processing,
    set_processing,
    get_pending_permission,
    clear_pending_permission,
    get_pending_code,
    clear_pending_code,
    clear_pending_plan,
)
from .ui.draw_helpers import (
    _draw_health_badge,
    _draw_quick_actions,
    _section_title,
    _scaled_container,
    _draw_mode_switch,
    _draw_agent_mode_quick_switch,
    _draw_pending_confirmations,
    _draw_pending_code_confirmation,
    _draw_smoke_failures,
)
from .ui.operators import (
    AGENT_OT_SetAgentMode,
    AGENT_OT_CopyMessage,
    AGENT_OT_ViewFullMessage,
    AGENT_OT_AddTodo,
    AGENT_OT_RemoveTodo,
    AGENT_OT_ToggleTodo,
    AGENT_OT_ViewPerformanceReport,
    AGENT_OT_ExportPerformanceReport,
    AGENT_OT_ClearSmokeFailures,
    AGENT_OT_StopAutoFixSmokeFailures,
)
from .ui.meshy_ops import (
    AGENT_OT_MeshyImageTo3DUpload,
    init_callbacks as _meshy_init_callbacks,
)
from .ui.smoke_runner import (
    AGENT_OT_RunSmokeTests,
    AGENT_OT_SendSmokeFailureToAgent,
    AGENT_OT_AutoFixSmokeFailures,
    init_smoke_callbacks as _smoke_init_callbacks,
)
from .ui.agent_bridge import (
    get_agent,
    clear_agents_cache,
    cancel_all_agents,
    _infer_route_hint,
    _send_message_with_mode,
    _send_prompt_to_agent,
    _execute_in_main_thread,  # re-exported for external use
    push_system_notice,       # re-exported for tool_definitions
    _on_tool_call,
    _on_error,
    _on_permission_request,
    get_pending_callback,
    clear_pending_callback,
)


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
            ("orchestrator", "Plan Orchestrator", "复杂任务启用 Router/Planner/Executor/Validator 的分步执行链"),
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
    ui_language: EnumProperty(
        name=tr("settings_lang"),
        description="界面语言",
        items=[
            ("auto", tr("lang_auto"), "根据用户输入语言回复"),
            ("zh", tr("lang_zh"), "简体中文"),
            ("en", tr("lang_en"), "English"),
        ],
        default="auto",
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
        box.prop(self, "ui_language")
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


class AGENT_OT_AnswerPlanQuestion(Operator):
    bl_idname = "agent.answer_plan_question"
    bl_label = "回答规划问题"

    option_label: StringProperty(default="")

    def execute(self, context):
        state = _get_state()
        answer = (self.option_label or "").strip()
        question = (state.pending_plan_question or "").strip()
        if not question:
            return {"CANCELLED"}
        user_msg = f"关于规划问题“{question}”，我的选择是：{answer}"
        _add_message("user", user_msg, channel="agent")
        state.pending_plan_question = ""
        state.pending_plan_options_json = "[]"
        clear_pending_plan(channel="agent")
        state.last_user_message = user_msg
        state.request_had_tool_call = False
        state.fallback_attempted = False
        state.last_exec_status = "processing"
        state.last_stall_reason = "-"
        prefs = get_preferences()
        _send_message_with_mode(user_msg, prefs.agent_mode)
        return {"FINISHED"}

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

def _is_meshy_mode(prefs) -> bool:
    return getattr(prefs, "conversation_mode", "llm_agent") == "meshy_pipeline"


def _message_prop_name(prefs) -> str:
    return "meshy_messages" if _is_meshy_mode(prefs) else "messages"


def _active_message_prop_name(prefs) -> str:
    return "meshy_active_message_index" if _is_meshy_mode(prefs) else "active_message_index"


def _input_prop_name(prefs) -> str:
    return "meshy_input_text" if _is_meshy_mode(prefs) else "input_text"


class AGENT_OT_SendMessage(Operator):
    bl_idname = "agent.send_message"
    bl_label = "发送"

    def execute(self, context):
        state = _get_state()
        prefs = get_preferences()
        mode_kind = getattr(prefs, "conversation_mode", "llm_agent")
        input_attr = _input_prop_name(prefs)
        input_text = getattr(state, input_attr, "")

        if not input_text.strip():
            return {"CANCELLED"}

        if is_processing(channel=("meshy" if mode_kind == "meshy_pipeline" else "agent")):
            self.report({"WARNING"}, "Agent 正在处理中...")
            return {"CANCELLED"}

        if mode_kind == "llm_agent":
            if get_agent(mode_override=prefs.agent_mode) is None:
                self.report({"ERROR"}, "请先在插件设置中配置 API Key")
                return {"CANCELLED"}
        else:
            if not getattr(prefs, "meshy_api_key", ""):
                self.report({"ERROR"}, "请先在插件设置中配置 Meshy API Key")
                return {"CANCELLED"}

        user_msg = input_text.strip()
        _add_message("user", user_msg, channel=("meshy" if mode_kind == "meshy_pipeline" else "agent"))

        setattr(state, input_attr, "")
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
        cancel_all_agents()
        set_processing(False, channel="agent")
        set_processing(False, channel="meshy")
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
        state = _get_state()
        cb = get_pending_callback()

        if cb:
            set_processing(True, channel="agent")
            cb(self.approved)
            clear_pending_callback()

        clear_pending_code(channel="agent")

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
        prefs = get_preferences()
        channel = "meshy" if _is_meshy_mode(prefs) else "agent"
        pending = get_pending_permission(channel=channel)
        tool_name = pending.get("tool", "")
        args_text = pending.get("args", "{}") or "{}"
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
                    set_processing(True, channel="meshy")
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
                    set_processing(False, channel="meshy")
            else:
                _add_message("system", f"✅ 已授权一次：{tool_name}。Agent 将继续执行。")
                resume_mode = state.last_exec_mode or get_preferences().agent_mode
                agent = get_agent(mode_override=resume_mode)
                if agent:
                    set_processing(True, channel="agent")
                    state.last_exec_status = "processing"
                    resume_prompt = (
                        f"权限已批准。请继续完成刚才任务。"
                        f"你对工具 {tool_name} 使用参数 {args_text} 已获得一次性授权，"
                        "请立即调用 MCP 工具并继续后续步骤。"
                    )
                    agent.send_message(resume_prompt)
        else:
            _add_message("system", f"🚫 已拒绝授权：{tool_name or '未知工具'}")

        clear_pending_permission(channel=channel)
        return {"FINISHED"}


class AGENT_OT_ClearHistory(Operator):
    bl_idname = "agent.clear_history"
    bl_label = "清空对话"

    def execute(self, context):
        state = _get_state()
        prefs = get_preferences()
        mode_kind = getattr(prefs, "conversation_mode", "llm_agent")
        if mode_kind == "meshy_pipeline":
            state.meshy_messages.clear()
            state.meshy_active_message_index = 0
            _add_message("system", "Meshy 对话已清空，开始新对话", channel="meshy")
        else:
            state.messages.clear()
            state.active_message_index = 0
            clear_agents_cache()
            _add_message("system", "Agent 对话已清空，开始新对话", channel="agent")
        return {"FINISHED"}


class AGENT_OT_OpenSettings(Operator):
    bl_idname = "agent.open_settings"
    bl_label = "打开设置"

    def execute(self, context):
        bpy.ops.preferences.addon_show(module=__package__)
        return {"FINISHED"}


class AGENT_OT_SendTodoToAgent(Operator):
    bl_idname = "agent.send_todo_to_agent"
    bl_label = "让 Agent 执行"

    index: IntProperty()

    def execute(self, context):
        state = _get_state()
        if 0 <= self.index < len(state.todos):
            todo = state.todos[self.index]
            prefs = get_preferences()
            mode_kind = getattr(prefs, "conversation_mode", "llm_agent")
            if is_processing(channel=("meshy" if mode_kind == "meshy_pipeline" else "agent")):
                self.report({"WARNING"}, "Agent 正在处理中...")
                return {"CANCELLED"}
            if mode_kind == "llm_agent":
                if get_agent(mode_override=prefs.agent_mode) is None:
                    self.report({"ERROR"}, "请先配置 API Key")
                    return {"CANCELLED"}
            else:
                if not getattr(prefs, "meshy_api_key", ""):
                    self.report({"ERROR"}, "请先配置 Meshy API Key")
                    return {"CANCELLED"}
            msg = f"请帮我完成这个任务：{todo.content}"
            _add_message("user", msg, channel=("meshy" if mode_kind == "meshy_pipeline" else "agent"))
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
        is_meshy = _is_meshy_mode(prefs)
        message_prop = _message_prop_name(prefs)
        active_prop = _active_message_prop_name(prefs)
        input_prop = _input_prop_name(prefs)

        mode_kind = getattr(prefs, "conversation_mode", "llm_agent")
        missing_key = (not prefs.api_key) if mode_kind == "llm_agent" else (not getattr(prefs, "meshy_api_key", ""))
        if missing_key:
            box = ui.box()
            tip = "⚠️ 请先配置 API Key" if mode_kind == "llm_agent" else "⚠️ 请先配置 Meshy API Key"
            box.label(text=tip, icon='ERROR')
            box.operator("agent.open_settings", text="打开设置", icon='PREFERENCES')
            return

        header = ui.box()
        header.label(text=("Meshy Assistant" if is_meshy else "Blender Agent"), icon='OUTLINER_OB_LIGHT')
        _draw_mode_switch(header, prefs)
        if not is_meshy:
            _draw_agent_mode_quick_switch(header, prefs)
            _draw_health_badge(header, state)

        box = ui.box()
        _section_title(box, "会话", icon="CONSOLE")
        row = box.row(align=True)
        row.operator("agent.clear_history", text="清空", icon="TRASH")

        box.template_list(
            "AGENT_UL_message_list",
            "chat_messages_popup",
            state,
            message_prop,
            state,
            active_prop,
            rows=8,
            maxrows=12,
        )
        if not is_meshy:
            _draw_pending_code_confirmation(ui, state, channel="agent")
            _draw_pending_confirmations(ui, state, channel="agent")
        else:
            _draw_pending_confirmations(ui, state, channel="meshy")

        ui.separator()

        if is_processing(channel=("meshy" if is_meshy else "agent")):
            row = ui.row(align=True)
            row.label(text="⏳ AI 正在思考...", icon="SORTTIME")
            row.operator("agent.stop_processing", text="中止", icon="CANCEL")
        else:
            row = ui.row(align=True)
            row.prop(state, input_prop, text="")
            row.operator("agent.send_message", text="发送", icon="PLAY")

        ui.separator()
        if is_meshy:
            ui.operator("agent.meshy_image_to_3d_upload", text="图生3D（导入图片）", icon="IMAGE_DATA")
        else:
            _draw_quick_actions(ui, popup=True)
            ui.operator("agent.meshy_image_to_3d_upload", text="图生3D（导入图片）", icon="IMAGE_DATA")
            _draw_smoke_failures(ui, state)

    def invoke(self, context, event):
        prefs = get_preferences()
        if (not _is_meshy_mode(prefs)) and prefs.api_key:
            get_agent()

        state = _get_state()
        if _is_meshy_mode(prefs):
            if len(state.meshy_messages) == 0:
                _add_message("system", "你好！我是 Meshy 助手。你可以直接输入文生3D需求，或使用下方按钮上传图片做图生3D。", channel="meshy")
        else:
            if len(state.messages) == 0:
                _add_message("system", "你好！我是 Blender AI 助手。在下方输入你的需求，我会直接操作 Blender 完成。", channel="agent")

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
        is_meshy = _is_meshy_mode(prefs)
        message_prop = _message_prop_name(prefs)
        active_prop = _active_message_prop_name(prefs)
        input_prop = _input_prop_name(prefs)

        mode_kind = getattr(prefs, "conversation_mode", "llm_agent")
        missing_key = (not prefs.api_key) if mode_kind == "llm_agent" else (not getattr(prefs, "meshy_api_key", ""))
        if missing_key:
            box = ui.box()
            tip = "⚠️ 请先配置 API Key" if mode_kind == "llm_agent" else "⚠️ 请先配置 Meshy API Key"
            box.label(text=tip, icon='ERROR')
            box.operator("agent.open_settings", text="打开设置", icon='PREFERENCES')
            return

        if is_meshy:
            if len(state.meshy_messages) == 0:
                ui.label(text="你好！输入文生3D需求，或使用图生3D上传入口。", icon='INFO')
        else:
            if len(state.messages) == 0:
                ui.label(text="你好！在下方输入需求，我会直接操作 Blender。", icon='INFO')

        header = ui.box()
        header.label(text=("Meshy Assistant" if is_meshy else "Blender Agent"), icon='OUTLINER_OB_LIGHT')
        _draw_mode_switch(header, prefs)
        if not is_meshy:
            _draw_agent_mode_quick_switch(header, prefs)
            _draw_health_badge(header, state)

        box = ui.box()
        _section_title(box, "会话", icon='CONSOLE')
        row = box.row(align=True)
        row.operator("agent.clear_history", text="清空", icon='TRASH')

        box.template_list(
            "AGENT_UL_message_list",
            "chat_messages",
            state,
            message_prop,
            state,
            active_prop,
            rows=8,
            maxrows=15,
        )
        if is_processing(channel=("meshy" if is_meshy else "agent")):
            row = ui.row(align=True)
            row.label(text="⏳ AI 正在思考...", icon='SORTTIME')
            row.operator("agent.stop_processing", text="中止", icon='CANCEL')
        else:
            row = ui.row(align=True)
            row.prop(state, input_prop, text="")
            row.operator("agent.send_message", text="发送", icon='PLAY')

        if not is_meshy:
            _draw_pending_code_confirmation(ui, state, channel="agent")
            _draw_pending_confirmations(ui, state, channel="agent")
            _draw_quick_actions(ui, popup=False)
            ui.operator("agent.meshy_image_to_3d_upload", text="图生3D（导入图片）", icon="IMAGE_DATA")
            _draw_smoke_failures(ui, state)
        else:
            _draw_pending_confirmations(ui, state, channel="meshy")
            ui.operator("agent.meshy_image_to_3d_upload", text="图生3D（导入图片）", icon="IMAGE_DATA")


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
    AGENT_OT_SetAgentMode,
    AGENT_OT_SendMessage,
    AGENT_OT_StopProcessing,
    AGENT_OT_ConfirmCode,
    AGENT_OT_ConfirmPermission,
    AGENT_OT_AnswerPlanQuestion,
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
    AGENT_OT_RunSmokeTests,
    AGENT_OT_SendSmokeFailureToAgent,
    AGENT_OT_ClearSmokeFailures,
    AGENT_OT_AutoFixSmokeFailures,
    AGENT_OT_StopAutoFixSmokeFailures,
    AGENT_PT_MainPanel,
    AGENT_PT_TodoPanel,
]


def register():
    _meshy_init_callbacks(_on_tool_call, _on_error, _on_permission_request)
    _smoke_init_callbacks(_send_prompt_to_agent)
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.blender_agent = bpy.props.PointerProperty(type=AgentState)


def unregister():
    clear_agents_cache()

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.blender_agent
