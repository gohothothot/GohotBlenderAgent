import importlib.util
import pathlib
import unittest


def _load_plan_parser_module():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    module_path = repo_root / "parsers" / "plan_parser.py"
    spec = importlib.util.spec_from_file_location("plan_parser_module", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPlanParserExtended(unittest.TestCase):
    def setUp(self):
        self.mod = _load_plan_parser_module()

    def test_parse_check_and_on_fail(self):
        text = """
        {
          "goal": "test",
          "steps": [
            {
              "id": "s1",
              "step": 1,
              "tool": "object.create_cube",
              "args": {"size_m": 2.0, "location": [0,0,1]},
              "check": {"tool": "scene.get_summary", "expect_contains": ["Cube"]},
              "on_fail": {"retry": 2, "strategy": "revise_args"}
            }
          ]
        }
        """
        plan = self.mod.parse_plan(text)
        self.assertEqual(plan.total_steps, 1)
        step = plan.steps[0]
        self.assertEqual(step.tool, "object.create_cube")
        self.assertEqual(step.params.get("size_m"), 2.0)
        self.assertEqual(step.check.get("tool"), "scene.get_summary")
        self.assertEqual(step.on_fail.get("retry"), 2)
        self.assertEqual(step.on_fail.get("strategy"), "revise_args")


if __name__ == "__main__":
    unittest.main()
