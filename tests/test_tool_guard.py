import importlib.util
import pathlib
import sys
import unittest


def _load_tool_guard_module():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    module_path = repo_root / "core" / "tool_guard.py"
    spec = importlib.util.spec_from_file_location("tool_guard_module", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestToolGuard(unittest.TestCase):
    def setUp(self):
        self.mod = _load_tool_guard_module()

    def test_execute_python_blocked(self):
        result = self.mod.precheck_tool_execution("execute_python", {"code": "print(1)"})
        self.assertIsInstance(result, dict)
        self.assertFalse(result.get("success", True))
        self.assertIn("权限拦截", result.get("error", ""))


if __name__ == "__main__":
    unittest.main()
