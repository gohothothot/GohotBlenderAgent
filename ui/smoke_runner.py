"""
Blender Agent — Smoke test runner, autofix queue, and related operators.

Dependencies:
  - ui.state (_get_state, _add_message)
  - standard lib (io, os, json, unittest, traceback, datetime)
  - _send_prompt_to_agent: injected via init_smoke_callbacks()
"""

import io
import os
import json
import sys
import unittest
import traceback
from datetime import datetime

import bpy
from bpy.props import IntProperty, EnumProperty
from bpy.types import Operator

from .state import _get_state, _add_message, is_processing

# ---------- callback slots (injected by chat_ui at register time) ----------
_send_prompt_to_agent = None


def init_smoke_callbacks(send_prompt_to_agent):
    global _send_prompt_to_agent
    _send_prompt_to_agent = send_prompt_to_agent


# ---------- test runners ----------

def _discover_suite(loader, tests_dir: str, pattern: str, root_dir: str):
    try:
        return loader.discover(start_dir=tests_dir, pattern=pattern, top_level_dir=root_dir)
    except Exception:
        if root_dir not in sys.path:
            sys.path.insert(0, root_dir)
        return loader.discover(start_dir=tests_dir, pattern=pattern)

def _run_smoke_test_suite(tier: str = "quick") -> dict:
    root_dir = os.path.dirname(os.path.dirname(__file__))
    tests_dir = os.path.join(root_dir, "tests")
    if not os.path.isdir(tests_dir):
        return {"ok": False, "summary": "tests 目录不存在", "details": []}

    tier = (tier or "quick").lower()
    quick_patterns = (
        "test_runtime_core.py",
        "test_tool_guard.py",
        "test_plan_manager.py",
    )
    try:
        stream = io.StringIO()
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        if tier == "full":
            suite.addTests(_discover_suite(loader, tests_dir, "test_*.py", root_dir))
        else:
            for pat in quick_patterns:
                suite.addTests(_discover_suite(loader, tests_dir, pat, root_dir))
        runner = unittest.TextTestRunner(stream=stream, verbosity=2)
        result = runner.run(suite)
        details = stream.getvalue().splitlines()[-40:]
        ok = result.wasSuccessful()
        summary = (
            f"tier={tier}, tests={result.testsRun}, failures={len(result.failures)}, "
            f"errors={len(result.errors)}, skipped={len(getattr(result, 'skipped', []))}"
        )
        failures = []
        for case, tb in list(result.failures) + list(result.errors):
            name = getattr(case, "id", lambda: str(case))()
            tail = (tb or "").splitlines()[-1] if tb else ""
            failures.append({"test": name, "error": tail})
        return {"ok": ok, "summary": summary, "details": details, "failures": failures, "tier": tier}
    except Exception as e:
        return {
            "ok": False,
            "summary": f"测试执行异常: {e}",
            "details": traceback.format_exc().splitlines()[-40:],
            "failures": [{"test": "runner", "error": str(e)}],
            "tier": tier,
        }


def _run_target_test(failure: dict) -> dict:
    """针对单条失败项，只跑它所属的测试文件做定向验证。"""
    test_id = failure.get("test", "")
    parts = test_id.split(".")
    filename = (parts[1] + ".py") if len(parts) >= 2 else None
    if not filename or not filename.startswith("test_"):
        return _run_smoke_test_suite("quick")
    root_dir = os.path.dirname(os.path.dirname(__file__))
    tests_dir = os.path.join(root_dir, "tests")
    try:
        stream = io.StringIO()
        loader = unittest.TestLoader()
        suite = _discover_suite(loader, tests_dir, filename, root_dir)
        runner = unittest.TextTestRunner(stream=stream, verbosity=2)
        result = runner.run(suite)
        failures = []
        for case, tb in list(result.failures) + list(result.errors):
            name = getattr(case, "id", lambda: str(case))()
            tail = (tb or "").splitlines()[-1] if tb else ""
            failures.append({"test": name, "error": tail})
        summary = (
            f"file={filename}, tests={result.testsRun}, "
            f"failures={len(result.failures)}, errors={len(result.errors)}"
        )
        return {"ok": result.wasSuccessful(), "summary": summary, "failures": failures, "tier": "target"}
    except Exception as e:
        return {
            "ok": False,
            "summary": f"目标测试执行异常: {e}",
            "failures": [{"test": test_id, "error": str(e)}],
            "tier": "target",
        }


def _run_backend_agent2_suite() -> dict:
    """
    运行 Agent2 backend 基础测试（tests/test_backend_agent2_basics.py）。
    该入口用于 Blender UI 一键快测。
    """
    root_dir = os.path.dirname(os.path.dirname(__file__))
    tests_dir = os.path.join(root_dir, "tests")
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
    if not os.path.isdir(tests_dir):
        return {"ok": False, "summary": "tests 目录不存在", "details": [], "failures": []}

    stream = io.StringIO()
    try:
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromName("tests.test_backend_agent2_basics")
        runner = unittest.TextTestRunner(stream=stream, verbosity=2)
        result = runner.run(suite)
        details = stream.getvalue().splitlines()[-40:]
        failures = []
        for case, tb in list(result.failures) + list(result.errors):
            name = getattr(case, "id", lambda: str(case))()
            tail = (tb or "").splitlines()[-1] if tb else ""
            failures.append({"test": name, "error": tail})
        summary = (
            f"agent2_backend, tests={result.testsRun}, failures={len(result.failures)}, "
            f"errors={len(result.errors)}, skipped={len(getattr(result, 'skipped', []))}"
        )
        return {"ok": result.wasSuccessful(), "summary": summary, "details": details, "failures": failures}
    except Exception as e:
        return {
            "ok": False,
            "summary": f"Agent2 backend 测试异常: {e}",
            "details": traceback.format_exc().splitlines()[-40:],
            "failures": [{"test": "agent2_backend_runner", "error": str(e)}],
        }


# ---------- autofix queue ----------

def _autofix_send_next():
    state = _get_state()
    if not state.smoke_autofix_active:
        return False
    if is_processing(channel="agent"):
        return False
    try:
        queue_data = json.loads(state.smoke_autofix_queue_json or "[]")
    except Exception:
        queue_data = []
    if not queue_data:
        result = _run_smoke_test_suite("quick")
        failures = result.get("failures", []) or []
        state.smoke_failures_json = json.dumps(failures, ensure_ascii=False)
        state.smoke_last_summary = result.get("summary", "")
        state.smoke_autofix_active = False
        state.smoke_autofix_queue_json = "[]"
        state.smoke_autofix_total = 0
        state.smoke_autofix_current_json = "{}"
        if failures:
            _add_message("system", f"🔁 自动修复后快测仍有失败：{result.get('summary', '')}", channel="agent")
        else:
            _add_message("system", f"✅ 自动修复后快测通过：{result.get('summary', '')}", channel="agent")
        return False

    current = queue_data.pop(0)
    state.smoke_autofix_queue_json = json.dumps(queue_data, ensure_ascii=False)
    state.smoke_autofix_current_json = json.dumps(current, ensure_ascii=False)
    test_name = current.get("test", "unknown")
    test_err = current.get("error", "")
    prompt = (
        "请修复下面的 smoke test 失败项（自动修复队列）。\n"
        f"失败用例: {test_name}\n"
        f"错误摘要: {test_err}\n"
        "要求：先定位根因，再做最小改动修复，并给出简短验证要点。"
    )
    if _send_prompt_to_agent:
        return _send_prompt_to_agent(prompt)
    return False


def _autofix_verify_and_advance():
    """护栏：Agent 回复后，先跑目标测试文件验证修复是否生效，再推进队列。"""
    state = _get_state()
    try:
        current = json.loads(state.smoke_autofix_current_json or "{}")
    except Exception:
        current = {}
    state.smoke_autofix_current_json = "{}"

    if current:
        test_name = current.get("test", "unknown")
        result = _run_target_test(current)
        if result.get("ok"):
            _add_message("system", f"✅ 护栏验证通过：{test_name}", channel="agent")
        else:
            still_broken = any(f.get("test") == test_name for f in result.get("failures", []))
            if still_broken:
                _add_message(
                    "system",
                    f"⚠️ 护栏验证失败（修复未生效）：{test_name} — 跳过继续下一条",
                    channel="agent",
                )
            else:
                broken_names = ", ".join(f.get("test", "?") for f in result.get("failures", []))
                _add_message(
                    "system",
                    f"⚠️ 护栏发现新失败：{broken_names} — 跳过继续下一条",
                    channel="agent",
                )
    _autofix_send_next()


# ---------- Operators ----------

class AGENT_OT_RunSmokeTests(Operator):
    bl_idname = "agent.run_smoke_tests"
    bl_label = "运行 Smoke Tests"
    bl_description = "在 Blender 内置 Python 环境中执行 tests/test_*.py"

    _lines = None
    tier: EnumProperty(
        name="测试档位",
        items=[
            ("quick", "快速", "仅运行核心 smoke tests"),
            ("full", "完整", "运行所有 test_*.py"),
        ],
        default="quick",
    )

    def invoke(self, context, event):
        result = _run_smoke_test_suite(self.tier)
        summary = result.get("summary", "")
        details = result.get("details", [])
        self._lines = [f"Smoke Tests: {summary}", "-" * 60] + details
        state = _get_state()
        failures = result.get("failures", []) or []
        state.smoke_failures_json = json.dumps(failures, ensure_ascii=False)
        state.smoke_last_summary = summary

        try:
            root_dir = os.path.dirname(os.path.dirname(__file__))
            log_dir = os.path.join(root_dir, "logs")
            os.makedirs(log_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = os.path.join(log_dir, f"smoke_test_{ts}.log")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("\n".join(self._lines))
            self._lines.append("")
            self._lines.append(f"报告已保存: {out_path}")
        except Exception as e:
            self._lines.append("")
            self._lines.append(f"保存报告失败: {e}")

        if failures:
            top = failures[:5]
            msg_lines = ["🧪 Smoke Test 失败摘要："]
            for f in top:
                msg_lines.append(f"- {f.get('test', 'unknown')}: {f.get('error', '')[:180]}")
            if len(failures) > 5:
                msg_lines.append(f"... 还有 {len(failures) - 5} 条失败")
            _add_message("system", "\n".join(msg_lines), channel="agent")
        else:
            _add_message("system", f"🧪 Smoke Test ({result.get('tier', self.tier)}) 通过：{summary}", channel="agent")

        if result.get("ok"):
            self.report({"INFO"}, "Smoke tests 通过")
        else:
            self.report({"WARNING"}, "Smoke tests 失败，请查看报告")

        return context.window_manager.invoke_props_dialog(self, width=860)

    def execute(self, context):
        result = _run_smoke_test_suite(self.tier)
        failures = result.get("failures", []) or []
        if failures:
            self.report({"WARNING"}, result.get("summary", "Smoke tests failed"))
        else:
            self.report({"INFO"}, result.get("summary", "Smoke tests passed"))
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        col = box.column(align=True)
        for line in (self._lines or ["暂无结果"]):
            col.label(text=line if line else " ")


class AGENT_OT_RunBackendAgent2Tests(Operator):
    bl_idname = "agent.run_backend_agent2_tests"
    bl_label = "运行 Agent2 Backend 快测"
    bl_description = "执行 tests.test_backend_agent2_basics，快速验证 Agent2 backend 模块链路"

    _lines = None

    def invoke(self, context, event):
        result = _run_backend_agent2_suite()
        summary = result.get("summary", "")
        details = result.get("details", [])
        self._lines = [f"Agent2 Backend Tests: {summary}", "-" * 60] + details

        failures = result.get("failures", []) or []
        if failures:
            msg_lines = ["🧪 Agent2 Backend 快测失败："]
            for f in failures[:5]:
                msg_lines.append(f"- {f.get('test', 'unknown')}: {f.get('error', '')[:180]}")
            _add_message("system", "\n".join(msg_lines), channel="agent")
            self.report({"WARNING"}, "Agent2 backend 快测失败")
        else:
            _add_message("system", f"🧪 Agent2 Backend 快测通过：{summary}", channel="agent")
            self.report({"INFO"}, "Agent2 backend 快测通过")

        return context.window_manager.invoke_props_dialog(self, width=860)

    def execute(self, context):
        result = _run_backend_agent2_suite()
        if result.get("ok"):
            self.report({"INFO"}, result.get("summary", "Agent2 backend tests passed"))
        else:
            self.report({"WARNING"}, result.get("summary", "Agent2 backend tests failed"))
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        col = box.column(align=True)
        for line in (self._lines or ["暂无结果"]):
            col.label(text=line if line else " ")


class AGENT_OT_SendSmokeFailureToAgent(Operator):
    bl_idname = "agent.send_smoke_failure_to_agent"
    bl_label = "修复 Smoke 失败"
    bl_description = "把失败用例作为修复任务发给 Agent"

    index: IntProperty(default=0)

    def execute(self, context):
        state = _get_state()
        if is_processing(channel="agent"):
            self.report({"WARNING"}, "Agent 正在处理中，请稍后")
            return {"CANCELLED"}

        try:
            failures = json.loads(state.smoke_failures_json or "[]")
        except Exception:
            failures = []
        if not failures or self.index < 0 or self.index >= len(failures):
            self.report({"WARNING"}, "失败项不存在")
            return {"CANCELLED"}

        target = failures[self.index]
        test_name = target.get("test", "unknown")
        test_err = target.get("error", "")
        prompt = (
            "请修复下面的 smoke test 失败项。\n"
            f"失败用例: {test_name}\n"
            f"错误摘要: {test_err}\n"
            "要求：先定位根因，再做最小改动修复，并说明验证步骤。"
        )
        if _send_prompt_to_agent and _send_prompt_to_agent(prompt):
            return {"FINISHED"}
        return {"CANCELLED"}


class AGENT_OT_AutoFixSmokeFailures(Operator):
    bl_idname = "agent.autofix_smoke_failures"
    bl_label = "自动修复 Smoke 失败"

    def execute(self, context):
        state = _get_state()
        if is_processing(channel="agent"):
            self.report({"WARNING"}, "Agent 正在处理中，请稍后")
            return {"CANCELLED"}
        try:
            failures = json.loads(state.smoke_failures_json or "[]")
        except Exception:
            failures = []
        if not failures:
            self.report({"WARNING"}, "没有可修复的失败项")
            return {"CANCELLED"}
        state.smoke_autofix_active = True
        state.smoke_autofix_total = len(failures)
        state.smoke_autofix_queue_json = json.dumps(failures, ensure_ascii=False)
        _add_message("system", f"🚀 启动自动修复队列，共 {len(failures)} 项", channel="agent")
        if not _autofix_send_next():
            state.smoke_autofix_active = False
            self.report({"WARNING"}, "自动修复启动失败")
            return {"CANCELLED"}
        return {"FINISHED"}


SMOKE_CLASSES = [
    AGENT_OT_RunSmokeTests,
    AGENT_OT_RunBackendAgent2Tests,
    AGENT_OT_SendSmokeFailureToAgent,
    AGENT_OT_AutoFixSmokeFailures,
]
