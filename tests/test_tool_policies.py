import unittest

from core.tool_policies import normalize_tool_args


class TestToolPolicies(unittest.TestCase):
    def test_summary_defaults(self):
        args = normalize_tool_args("shader_get_material_summary", {"material_name": "M1"})
        self.assertEqual(args["detail_level"], "basic")
        self.assertTrue(args["include_node_index"])
        self.assertEqual(args["node_index_limit"], 60)

    def test_summary_limit_clamp(self):
        args = normalize_tool_args(
            "shader_get_material_summary",
            {"material_name": "M1", "node_index_limit": 9999},
        )
        self.assertEqual(args["node_index_limit"], 200)

    def test_inspect_defaults(self):
        args = normalize_tool_args("shader_inspect_nodes", {"material_name": "M1"})
        self.assertTrue(args["compact"])
        self.assertTrue(args["include_links"])
        self.assertFalse(args["include_values"])
        self.assertEqual(args["limit"], 30)
        self.assertEqual(args["offset"], 0)

    def test_inspect_limit_and_offset_clamp(self):
        args = normalize_tool_args(
            "shader_inspect_nodes",
            {"material_name": "M1", "limit": 1000, "offset": -5},
        )
        self.assertEqual(args["limit"], 80)
        self.assertEqual(args["offset"], 0)

    def test_inspect_force_compact_without_node_names(self):
        args = normalize_tool_args(
            "shader_inspect_nodes",
            {"material_name": "M1", "compact": False, "include_values": True},
        )
        self.assertTrue(args["compact"])
        self.assertFalse(args["include_values"])

    def test_search_index_top_k_clamp(self):
        args = normalize_tool_args("shader_search_index", {"material_name": "M1", "query": "emission", "top_k": 999})
        self.assertEqual(args["top_k"], 30)


if __name__ == "__main__":
    unittest.main()
