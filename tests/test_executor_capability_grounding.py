import importlib
import pathlib
import sys
import unittest


def _import_package_module(dotted_name: str):
    root = pathlib.Path(__file__).resolve().parents[1]
    parent = root.parent
    if str(parent) not in sys.path:
        sys.path.insert(0, str(parent))
    try:
        return importlib.import_module(dotted_name)
    except Exception as e:
        raise unittest.SkipTest(f"无法导入模块 {dotted_name}: {e}") from e


class TestExecutorCapabilityGrounding(unittest.TestCase):
    def test_apply_capability_grounding_prefers_chain(self):
        mod = _import_package_module("GohotBlenderAgent.agents.executor")
        Exec = mod.ExecutorAgent
        ex = Exec.__new__(Exec)
        ex._grounding_tool_chain = ["gn_create_modifier", "gn_add_node", "gn_link_nodes", "gn_get_summary"]

        tool_schemas = [
            {"name": "list_objects"},
            {"name": "gn_add_node"},
            {"name": "gn_link_nodes"},
            {"name": "gn_create_modifier"},
            {"name": "scene_add_light"},
            {"name": "gn_get_summary"},
            {"name": "get_object_info"},
        ]
        out = ex._apply_capability_grounding(tool_schemas)
        names = [t.get("name") for t in out]
        self.assertIn("gn_create_modifier", names)
        self.assertIn("gn_add_node", names)
        self.assertIn("gn_link_nodes", names)
        self.assertIn("gn_get_summary", names)
        # 应较原始集合更收敛
        self.assertLess(len(out), len(tool_schemas))

    def test_set_grounding_tools_dedup(self):
        mod = _import_package_module("GohotBlenderAgent.agents.executor")
        Exec = mod.ExecutorAgent
        ex = Exec.__new__(Exec)
        ex._grounding_tool_chain = []
        ex.set_grounding_tools(["gn_add_node", "gn_add_node", "  ", "gn_link_nodes"])
        self.assertEqual(ex._grounding_tool_chain, ["gn_add_node", "gn_link_nodes"])


if __name__ == "__main__":
    unittest.main()

