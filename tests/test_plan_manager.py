import importlib.util
import pathlib
import tempfile
import unittest


def _load_plan_manager_module():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    module_path = repo_root / "context" / "plan_manager.py"
    spec = importlib.util.spec_from_file_location("plan_manager_module", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPlanManager(unittest.TestCase):
    def setUp(self):
        self.mod = _load_plan_manager_module()

    def test_create_and_update_step(self):
        with tempfile.TemporaryDirectory() as td:
            m = self.mod.PlanManager()
            m._plan_dir = pathlib.Path(td)  # redirect storage for test
            session_id = "s1"
            plan = m.create_plan(session_id, {
                "title": "t",
                "steps": [
                    {"id": "step-1", "title": "a"},
                    {"id": "step-2", "title": "b"},
                ],
            })
            self.assertEqual(plan["status"], "draft")
            loaded = m.load_plan(session_id)
            self.assertIsNotNone(loaded)
            self.assertEqual(len(loaded["steps"]), 2)

            updated = m.update_step(session_id, "step-1", "running", "doing")
            self.assertEqual(updated["status"], "executing")
            updated = m.update_step(session_id, "step-1", "done", "done")
            self.assertEqual(updated["steps"][0]["status"], "done")
            updated = m.update_step(session_id, "step-2", "error", "fail")
            self.assertEqual(updated["status"], "completed")


if __name__ == "__main__":
    unittest.main()
