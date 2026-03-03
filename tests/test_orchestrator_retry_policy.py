import importlib
import pathlib
import sys
import unittest
from types import SimpleNamespace


def _load_orchestrator_class():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    parent = repo_root.parent
    if str(parent) not in sys.path:
        sys.path.insert(0, str(parent))
    try:
        module = importlib.import_module("GohotBlenderAgent.agents.orchestrator")
    except Exception as e:
        raise unittest.SkipTest(f"无法导入 orchestrator: {e}") from e
    return module.AgentOrchestrator


class _DummyExecutor:
    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    def execute_step(self, step, domain, prev_summary, user_message):
        self.calls += 1
        if self._results:
            return self._results.pop(0)
        return {"success": True, "result": "ok", "error": None}

    def _run_tool(self, name, args):
        return {"success": True, "result": "scene contains Cube", "error": None}


class TestOrchestratorRetryPolicy(unittest.TestCase):
    def test_retry_same_until_success(self):
        Orch = _load_orchestrator_class()
        orch = Orch.__new__(Orch)
        orch._executor = _DummyExecutor(
            [
                {"success": False, "result": None, "error": "first_fail"},
                {"success": True, "result": "done", "error": None},
            ]
        )
        orch.on_plan = None
        orch._fire_callback = lambda cb, *args: cb(*args)

        step = SimpleNamespace(
            on_fail={"retry": 1, "strategy": "retry_same"},
            params={},
            step=1,
            status="pending",
            error="",
            check={},
        )
        route = SimpleNamespace(domain="scene")
        result = orch._execute_plan_step_with_policy(step, route, "", "make cube")

        self.assertTrue(result.get("success"))
        self.assertEqual(orch._executor.calls, 2)

    def test_revise_args_clamps_invalid_values(self):
        Orch = _load_orchestrator_class()
        orch = Orch.__new__(Orch)
        orch._executor = _DummyExecutor(
            [
                {"success": False, "result": None, "error": "bad_args"},
                {"success": True, "result": "done", "error": None},
            ]
        )
        orch.on_plan = None
        orch._fire_callback = lambda cb, *args: cb(*args)

        step = SimpleNamespace(
            on_fail={"retry": 1, "strategy": "revise_args"},
            params={"size_m": -2.0, "segments": 0},
            step=2,
            status="pending",
            error="",
            check={},
        )
        route = SimpleNamespace(domain="scene")
        result = orch._execute_plan_step_with_policy(step, route, "", "subdivide")

        self.assertTrue(result.get("success"))
        self.assertEqual(step.params["size_m"], 0.001)
        self.assertEqual(step.params["segments"], 1)

    def test_enforce_capability_grounding_filters_invalid_steps(self):
        Orch = _load_orchestrator_class()
        orch = Orch.__new__(Orch)
        orch.on_plan = None
        orch._fire_callback = lambda cb, *args: cb(*args)
        orch._planner = type(
            "_DummyPlanner",
            (),
            {
                "plan": lambda self, _msg, _intent: SimpleNamespace(
                    steps=[
                        SimpleNamespace(step=1, tool="gn_create_modifier", params={}, description="", status="pending", error=""),
                        SimpleNamespace(step=2, tool="unknown_tool_x", params={}, description="", status="pending", error=""),
                        SimpleNamespace(step=3, tool="", params={}, description="manual step", status="pending", error=""),
                    ],
                    total_steps=3,
                    summary="dummy",
                    failed_steps=[],
                )
            },
        )()
        route = SimpleNamespace(intent="modify")
        plan = SimpleNamespace(
            steps=[
                SimpleNamespace(step=1, tool="gn_create_modifier", params={}, description="", status="pending", error=""),
                SimpleNamespace(step=2, tool="bad_tool", params={}, description="", status="pending", error=""),
            ],
            total_steps=2,
            summary="orig",
            failed_steps=[],
        )

        out = orch._enforce_capability_tool_grounding(
            plan=plan,
            raw_user_message="创建几何节点链路",
            route=route,
            capability_tool_chain=["gn_create_modifier", "gn_add_node", "gn_link_nodes", "gn_get_summary"],
        )
        tools = [getattr(s, "tool", "") for s in out.steps]
        self.assertIn("gn_create_modifier", tools)
        self.assertNotIn("bad_tool", tools)


if __name__ == "__main__":
    unittest.main()
