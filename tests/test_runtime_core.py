import importlib.util
import pathlib
import unittest


def _load_runtime_core_module():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    module_path = repo_root / "core" / "runtime_core.py"
    spec = importlib.util.spec_from_file_location("runtime_core_module", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Dummy:
    pass


class TestRuntimeCore(unittest.TestCase):
    def setUp(self):
        mod = _load_runtime_core_module()
        self.mixin = mod.RuntimeCoreMixin()

    def test_round_compaction_keeps_tail_rounds(self):
        history = [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "tool", "content": "t1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "u3"},
            {"role": "assistant", "content": "a3"},
        ]
        compacted = self.mixin._runtime_compact_history(history, keep_tail_rounds=2)
        self.assertGreaterEqual(len(compacted), 3)
        self.assertEqual(compacted[0]["role"], "system")
        # tail rounds kept
        joined = " ".join(str(m.get("content", "")) for m in compacted)
        self.assertIn("u2", joined)
        self.assertIn("u3", joined)


if __name__ == "__main__":
    unittest.main()
