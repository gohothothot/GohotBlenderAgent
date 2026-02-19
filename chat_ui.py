"""
Blender Agent Chat UI - 弹窗对话界面

在 Blender 中显示一个对话窗口，与 Agent 交互
"""

import bpy
from bpy.props import StringProperty, CollectionProperty, IntProperty, BoolProperty, EnumProperty
from bpy.types import PropertyGroup, Operator, Panel, AddonPreferences


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
            ("claude-opus-4-5-20251101", "Claude Opus 4.5", "最强性能"),
            ("claude-haiku-4-5", "Claude Haiku 4.5", "最快速度"),
        ],
        default="claude-sonnet-4-5",
    )
    
    custom_model: StringProperty(
        name="自定义模型",
        description="如果使用中转API，可以填写自定义模型名称（留空则使用上方选择）",
        default="",
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
        
        layout.label(text="🎨 Meshy AI 配置", icon='MESH_MONKEY')
        box = layout.box()
        box.prop(self, "meshy_api_key")
        box.prop(self, "meshy_ai_model")
        
        if not self.meshy_api_key:
            box.label(text="⚠️ 请填写 Meshy API Key 才能使用 3D 生成功能", icon='INFO')
            box.operator("wm.url_open", text="获取 Meshy API Key", icon='URL').url = "https://www.meshy.ai/settings/api"


def get_preferences():
    return bpy.context.preferences.addons[__package__].preferences


class ChatMessage(PropertyGroup):
    role: StringProperty(name="Role")
    content: StringProperty(name="Content")
    is_code: BoolProperty(name="Is Code", default=False)


class AgentState(PropertyGroup):
    """Agent 状态"""

    messages: CollectionProperty(type=ChatMessage)
    input_text: StringProperty(name="Input", default="")
    is_processing: BoolProperty(name="Processing", default=False)
    pending_code: StringProperty(name="Pending Code", default="")
    pending_code_desc: StringProperty(name="Pending Code Desc", default="")
    pending_tool_id: StringProperty(name="Pending Tool ID", default="")


# ========== 全局 Agent 实例 ==========
_agent = None


def get_agent():
    global _agent
    prefs = get_preferences()
    
    if not prefs.api_key:
        return None
    
    model = prefs.custom_model if prefs.custom_model else prefs.model
    
    if _agent is None or _agent.api_base != prefs.api_base or _agent.api_key != prefs.api_key or _agent.model != model:
        from .agent_core import BlenderAgent
        _agent = BlenderAgent(
            api_base=prefs.api_base,
            api_key=prefs.api_key,
            model=model,
        )
        _agent.on_message = _on_agent_message
        _agent.on_tool_call = _on_tool_call
        _agent.on_code_confirm = _on_code_confirm
        _agent.on_error = _on_error

    return _agent


def _get_state() -> AgentState:
    return bpy.context.scene.blender_agent


def _add_message(role: str, content: str, is_code: bool = False):
    state = _get_state()
    msg = state.messages.add()
    msg.role = role
    msg.content = content
    msg.is_code = is_code

    for area in bpy.context.screen.areas:
        area.tag_redraw()


def _on_agent_message(role: str, content: str):
    _add_message(role, content)
    state = _get_state()
    state.is_processing = False


def _on_tool_call(tool_name: str, args: dict):
    _add_message("system", f"🔧 调用工具: {tool_name}")


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
    _add_message("system", f"❌ 错误: {error}")
    state = _get_state()
    state.is_processing = False


_pending_callback = None


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

        agent = get_agent()
        if agent is None:
            self.report({"ERROR"}, "请先在插件设置中配置 API Key")
            return {"CANCELLED"}

        user_msg = state.input_text.strip()
        _add_message("user", user_msg)

        state.input_text = ""
        state.is_processing = True

        agent.send_message(user_msg)

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


class AGENT_OT_ClearHistory(Operator):
    bl_idname = "agent.clear_history"
    bl_label = "清空对话"

    def execute(self, context):
        global _agent
        state = _get_state()
        state.messages.clear()

        if _agent:
            _agent.clear_history()

        _add_message("system", "对话已清空，开始新对话")
        return {"FINISHED"}


class AGENT_OT_OpenSettings(Operator):
    bl_idname = "agent.open_settings"
    bl_label = "打开设置"

    def execute(self, context):
        bpy.ops.preferences.addon_show(module=__package__)
        return {"FINISHED"}


class AGENT_OT_OpenChat(Operator):
    bl_idname = "agent.open_chat"
    bl_label = "打开 AI 助手"
    bl_options = {"REGISTER"}

    def execute(self, context):
        return context.window_manager.invoke_props_dialog(self, width=500)

    def draw(self, context):
        layout = self.layout
        state = _get_state()
        prefs = get_preferences()

        if not prefs.api_key:
            box = layout.box()
            box.label(text="⚠️ 请先配置 API Key", icon='ERROR')
            box.operator("agent.open_settings", text="打开设置", icon='PREFERENCES')
            return

        box = layout.box()
        box.label(text="对话历史", icon="CONSOLE")

        col = box.column(align=True)

        messages = list(state.messages)[-15:]

        if not messages:
            col.label(text="开始和 AI 助手对话吧！", icon="INFO")

        for msg in messages:
            row = col.row()

            if msg.role == "user":
                row.label(
                    text=f"👤 你: {msg.content[:80]}{'...' if len(msg.content) > 80 else ''}"
                )
            elif msg.role == "assistant":
                row.label(
                    text=f"🤖 AI: {msg.content[:80]}{'...' if len(msg.content) > 80 else ''}"
                )
            else:
                row.label(
                    text=f"ℹ️ {msg.content[:80]}{'...' if len(msg.content) > 80 else ''}"
                )

        if state.pending_code:
            code_box = layout.box()
            code_box.label(text="⚠️ 待确认的代码:", icon="ERROR")
            code_box.label(text=state.pending_code_desc)

            code_preview = state.pending_code[:200] + (
                "..." if len(state.pending_code) > 200 else ""
            )
            for line in code_preview.split("\n")[:5]:
                code_box.label(text=f"  {line}")

            row = code_box.row()
            op_yes = row.operator(
                "agent.confirm_code", text="✅ 执行", icon="CHECKMARK"
            )
            op_yes.approved = True
            op_no = row.operator("agent.confirm_code", text="❌ 取消", icon="X")
            op_no.approved = False

        layout.separator()

        if state.is_processing:
            layout.label(text="⏳ AI 正在思考...", icon="SORTTIME")
        else:
            row = layout.row(align=True)
            row.prop(state, "input_text", text="")
            row.operator("agent.send_message", text="", icon="PLAY")

        layout.separator()
        row = layout.row(align=True)
        row.operator("agent.clear_history", text="清空对话", icon="TRASH")
        row.operator("agent.open_settings", text="设置", icon="PREFERENCES")

    def invoke(self, context, event):
        prefs = get_preferences()
        if prefs.api_key:
            get_agent()

        state = _get_state()
        if len(state.messages) == 0:
            _add_message(
                "system",
                "你好！我是 Blender AI 助手，可以帮你创建物体、设置材质、执行代码等。",
            )

        return context.window_manager.invoke_props_dialog(self, width=500)





# ========== 注册 ==========

classes = [
    BlenderAgentPreferences,
    ChatMessage,
    AgentState,
    AGENT_OT_SendMessage,
    AGENT_OT_ConfirmCode,
    AGENT_OT_ClearHistory,
    AGENT_OT_OpenSettings,
    AGENT_OT_OpenChat,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.blender_agent = bpy.props.PointerProperty(type=AgentState)


def unregister():
    global _agent
    _agent = None
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.blender_agent
