"""
Blender Agent — standalone Operators (no Agent-instance dependency).

These operators only depend on:
  - ui.state  (get_preferences, _get_state, _add_message)
  - action_log (lazy import)
  - standard lib (json, os, datetime)
"""

import bpy
import json
import os
from datetime import datetime
from bpy.props import StringProperty, IntProperty, EnumProperty
from bpy.types import Operator

from .state import get_preferences, _get_state, _add_message


def _active_messages(state):
    prefs = get_preferences()
    mode_kind = getattr(prefs, "conversation_mode", "llm_agent")
    if mode_kind == "meshy_pipeline":
        return list(state.meshy_messages)
    return list(state.messages)


# ========== Agent mode ===========

class AGENT_OT_SetAgentMode(Operator):
    bl_idname = "agent.set_agent_mode"
    bl_label = "设置执行模式"
    bl_description = "切换 Agent 执行模式"

    mode: StringProperty(default="native")

    @classmethod
    def description(cls, context, properties):
        mode = getattr(properties, "mode", "")
        if mode == "native":
            return "Native：使用模型原生工具调用协议（tool/function calling），简单任务响应更快。"
        if mode == "structured":
            return "Structured：使用结构化文本工具调用（非原生 tool_use），兼容性更好、上下文开销更低。"
        if mode == "orchestrator":
            return "Plan：Router/Planner/Executor/Validator 分步执行，适合复杂多步骤任务。"
        return cls.bl_description

    def execute(self, context):
        prefs = get_preferences()
        if self.mode in ("native", "structured", "orchestrator"):
            prefs.agent_mode = self.mode
            mode_label = {
                "native": "Native",
                "structured": "Structured",
                "orchestrator": "Plan",
            }.get(self.mode, self.mode)
            _add_message("system", f"已切换执行模式：{mode_label}")
        return {"FINISHED"}


# ========== Message helpers ===========

class AGENT_OT_CopyMessage(Operator):
    bl_idname = "agent.copy_message"
    bl_label = "复制消息"
    bl_description = "复制消息内容到剪贴板"

    index: IntProperty()

    def execute(self, context):
        state = _get_state()
        messages = _active_messages(state)
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
        messages = _active_messages(state)
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


# ========== TODO operators ===========

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


# ========== Performance report ===========

def _build_performance_report_lines(max_sessions: int = 5) -> list:
    lines = []
    try:
        from .. import action_log
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
            from .. import action_log

            logs = action_log.get_recent_logs(20)
            if not logs:
                self.report({'WARNING'}, "暂无性能日志可导出")
                return {'CANCELLED'}

            root_dir = os.path.dirname(os.path.dirname(__file__))
            log_dir = os.path.join(root_dir, "logs")
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


# ========== Smoke test helpers ===========

class AGENT_OT_ClearSmokeFailures(Operator):
    bl_idname = "agent.clear_smoke_failures"
    bl_label = "清空 Smoke 失败"

    def execute(self, context):
        state = _get_state()
        state.smoke_failures_json = "[]"
        state.smoke_last_summary = ""
        self.report({"INFO"}, "已清空失败列表")
        return {"FINISHED"}


class AGENT_OT_StopAutoFixSmokeFailures(Operator):
    bl_idname = "agent.stop_autofix_smoke_failures"
    bl_label = "停止自动修复 Smoke 失败"

    def execute(self, context):
        state = _get_state()
        state.smoke_autofix_active = False
        state.smoke_autofix_queue_json = "[]"
        state.smoke_autofix_total = 0
        _add_message("system", "⏹️ 已停止自动修复队列。")
        return {"FINISHED"}


OPERATOR_CLASSES = [
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
]
