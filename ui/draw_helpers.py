"""
Draw helper functions for Blender Agent UI panels.

Pure UI drawing — no Agent logic, no LLM calls.
All helpers receive layout / prefs / state as parameters.
"""

import json
from .state import get_preferences, get_pending_permission, get_pending_plan, get_pending_code


def _draw_health_badge(layout, state):
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
        op_q = row.operator("agent.run_smoke_tests", text="快测", icon="CHECKMARK")
        op_q.tier = "quick"
        op_f = row.operator("agent.run_smoke_tests", text="全测", icon="CHECKMARK")
        op_f.tier = "full"
        row.operator("agent.export_performance_report", text="", icon="EXPORT")
    else:
        row.operator("agent.open_chat", text="弹窗", icon="WINDOW")
        row.operator("agent.view_performance_report", text="性能", icon="GRAPH")
        op_q = row.operator("agent.run_smoke_tests", text="快测", icon="CHECKMARK")
        op_q.tier = "quick"
        op_f = row.operator("agent.run_smoke_tests", text="全测", icon="CHECKMARK")
        op_f.tier = "full"
        row.operator("agent.export_performance_report", text="", icon="EXPORT")


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
        row.label(text="Agent | Meshy（请重载插件）", icon="INFO")


def _draw_agent_mode_quick_switch(layout, prefs):
    row = layout.row(align=True)
    row.label(text="执行模式:")
    op1 = row.operator("agent.set_agent_mode", text="Native", depress=(prefs.agent_mode == "native"))
    op1.mode = "native"
    op2 = row.operator("agent.set_agent_mode", text="XML", depress=(prefs.agent_mode == "structured"))
    op2.mode = "structured"
    op3 = row.operator("agent.set_agent_mode", text="Plan", depress=(prefs.agent_mode == "orchestrator"))
    op3.mode = "orchestrator"


def _draw_pending_confirmations(ui, state, channel: str = "agent"):
    pending_permission = get_pending_permission(channel=channel)
    if pending_permission.get("tool"):
        perm_box = ui.box()
        perm_box.label(text="🔐 待确认高权限操作:", icon="LOCKED")
        perm_box.label(text=f"工具: {pending_permission.get('tool')}")
        perm_box.label(text=f"风险: {pending_permission.get('risk')}")
        perm_box.label(text=(pending_permission.get("reason", "") or "")[:180])
        row = perm_box.row()
        op_yes = row.operator("agent.confirm_permission", text="✅ 允许一次", icon="CHECKMARK")
        op_yes.approved = True
        op_no = row.operator("agent.confirm_permission", text="❌ 拒绝", icon="X")
        op_no.approved = False

    pending_plan = get_pending_plan(channel=channel)
    if pending_plan.get("question"):
        q_box = ui.box()
        q_box.label(text="🧭 计划澄清", icon="QUESTION")
        q_box.label(text=(pending_plan.get("question") or "")[:200])
        options = []
        try:
            options = json.loads(pending_plan.get("options_json") or "[]")
        except Exception:
            options = []
        if options:
            for opt in options[:6]:
                label = opt.get("label", "")
                if not label:
                    continue
                op = q_box.operator("agent.answer_plan_question", text=label, icon="PLAY")
                op.option_label = label


def _draw_pending_code_confirmation(ui, state, channel: str = "agent"):
    pending_code = get_pending_code(channel=channel)
    if not pending_code.get("code"):
        return
    code_box = ui.box()
    code_box.label(text="⚠️ 待确认代码:", icon="ERROR")
    code_box.label(text=pending_code.get("desc", ""))
    code_preview = (pending_code.get("code") or "")[:500]
    for line in code_preview.split("\n")[:10]:
        code_box.label(text=f"  {line}")
    if len(pending_code.get("code") or "") > 500:
        code_box.label(text="  ...")
    row = code_box.row()
    op_yes = row.operator("agent.confirm_code", text="✅ 执行", icon="CHECKMARK")
    op_yes.approved = True
    op_no = row.operator("agent.confirm_code", text="❌ 取消", icon="X")
    op_no.approved = False


def _draw_smoke_failures(ui, state):
    failures = []
    try:
        failures = json.loads(state.smoke_failures_json or "[]")
    except Exception:
        failures = []
    if not failures:
        return

    box = ui.box()
    box.label(text="🧪 最近测试失败", icon="ERROR")
    if state.smoke_last_summary:
        box.label(text=state.smoke_last_summary[:160])
    if state.smoke_autofix_active:
        try:
            q = json.loads(state.smoke_autofix_queue_json or "[]")
        except Exception:
            q = []
        done = max(0, int(state.smoke_autofix_total) - len(q))
        box.label(text=f"自动修复中: {done}/{max(1, int(state.smoke_autofix_total))}", icon="SORTTIME")
    for i, f in enumerate(failures[:5]):
        row = box.row(align=True)
        name = f.get("test", "unknown")
        err = (f.get("error", "") or "")[:90]
        row.label(text=f"{i+1}. {name}")
        op = row.operator("agent.send_smoke_failure_to_agent", text="让Agent修", icon="PLAY")
        op.index = i
        if err:
            box.label(text=f"   {err}")
    row = box.row(align=True)
    if not state.smoke_autofix_active:
        row.operator("agent.autofix_smoke_failures", text="自动修复全部", icon="PLAY")
    else:
        row.operator("agent.stop_autofix_smoke_failures", text="停止自动修复", icon="CANCEL")
    row.operator("agent.clear_smoke_failures", text="清空失败列表", icon="TRASH")
