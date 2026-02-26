"""
Blender Agent Chat UI - 侧边栏 + 弹窗双模式对话界面
"""

import bpy
import json
from bpy.props import StringProperty, CollectionProperty, IntProperty, BoolProperty, EnumProperty
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
        layout.label(text="⚙️ Agent 设置", icon='TOOL_SETTINGS')
        box = layout.box()
        box.prop(self, "agent_mode")
        if self.agent_mode == "structured":
            box.label(text="ℹ️ XML 模式：LLM 生成文本 + XML 标签，更省 token", icon='INFO')
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
    pending_tool_id: StringProperty(name="Pending Tool ID", default="")
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

_agent = None
_agent_config_key = None  # 用于检测配置变更


def get_agent():
    global _agent, _agent_config_key
    prefs = get_preferences()

    if not prefs.api_key:
        return None

    model = prefs.custom_model if prefs.custom_model else prefs.model
    config_key = f"{prefs.api_base}|{prefs.api_key}|{model}|{prefs.agent_mode}"

    if _agent is None or _agent_config_key != config_key:
        from .core.llm import LLMConfig

        config = LLMConfig(
            api_base=prefs.api_base,
            api_key=prefs.api_key,
            model=model,
        )

        if prefs.agent_mode == "structured":
            from .core.structured_agent import StructuredAgent
            _agent = StructuredAgent(config=config)
        else:
            from .core.agent import BlenderAgent
            _agent = BlenderAgent(config=config)

        _agent.on_message = _on_agent_message
        _agent.on_tool_call = _on_tool_call
        _agent.on_error = _on_error
        _agent.on_plan = _on_plan
        _agent_config_key = config_key

    return _agent


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


def _on_agent_message(role: str, content: str):
    _add_message(role, content)
    state = _get_state()
    state.is_processing = False


def _on_tool_call(tool_name: str, args: dict):
    args_preview = json.dumps(args, ensure_ascii=False)[:200] if args else ""
    _add_message("system", f"🔧 调用工具: {tool_name}\n{args_preview}")


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
    _add_message("system", f"❌ 错误: {error}")
    state = _get_state()
    state.is_processing = False


_pending_callback = None


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
            agent = get_agent()
            if agent is None:
                self.report({"ERROR"}, "请先配置 API Key")
                return {"CANCELLED"}
            msg = f"请帮我完成这个任务：{todo.content}"
            _add_message("user", msg)
            state.is_processing = True
            agent.send_message(msg)
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

        if not prefs.api_key:
            box = layout.box()
            box.label(text="⚠️ 请先配置 API Key", icon='ERROR')
            box.operator("agent.open_settings", text="打开设置", icon='PREFERENCES')
            return

        box = layout.box()
        row = box.row()
        row.label(text="对话历史", icon="CONSOLE")
        row.operator("agent.clear_history", text="", icon="TRASH")

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
            code_box = layout.box()
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

        layout.separator()

        if state.is_processing:
            layout.label(text="⏳ AI 正在思考...", icon="SORTTIME")
        else:
            row = layout.row(align=True)
            row.prop(state, "input_text", text="")
            row.operator("agent.send_message", text="", icon="PLAY")

        layout.separator()
        row = layout.row(align=True)
        row.operator("agent.open_settings", text="设置", icon="PREFERENCES")

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

        if not prefs.api_key:
            box = layout.box()
            box.label(text="⚠️ 请先配置 API Key", icon='ERROR')
            box.operator("agent.open_settings", text="打开设置", icon='PREFERENCES')
            return

        if len(state.messages) == 0:
            layout.label(text="你好！在下方输入需求，我会直接操作 Blender。", icon='INFO')

        box = layout.box()
        row = box.row()
        row.label(text="对话", icon='CONSOLE')
        row.operator("agent.clear_history", text="", icon='TRASH')

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
            layout.label(text="⏳ AI 正在思考...", icon='SORTTIME')
        else:
            row = layout.row(align=True)
            row.prop(state, "input_text", text="")
            row.operator("agent.send_message", text="", icon='PLAY')

        if state.pending_code:
            code_box = layout.box()
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

        row = layout.row(align=True)
        row.operator("agent.open_settings", text="设置", icon='PREFERENCES')
        row.operator("agent.open_chat", text="弹窗模式", icon='WINDOW')


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
    AGENT_OT_ConfirmCode,
    AGENT_OT_ClearHistory,
    AGENT_OT_OpenSettings,
    AGENT_OT_CopyMessage,
    AGENT_OT_ViewFullMessage,
    AGENT_OT_AddTodo,
    AGENT_OT_RemoveTodo,
    AGENT_OT_ToggleTodo,
    AGENT_OT_SendTodoToAgent,
    AGENT_OT_OpenChat,
    AGENT_PT_MainPanel,
    AGENT_PT_TodoPanel,
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
