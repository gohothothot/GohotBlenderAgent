import unittest

from core.shader_read_planner import plan_shader_inspect, estimate_inspect_cost


class TestShaderReadPlanner(unittest.TestCase):
    def test_auto_search_when_values_without_nodes(self):
        raw_args = {"material_name": "MatA", "include_values": True}
        normalized = {"material_name": "MatA", "include_values": False, "compact": True, "limit": 30}
        plan = plan_shader_inspect(raw_args, normalized)
        self.assertTrue(plan["auto_search"])
        self.assertIsNotNone(plan["search_args"])
        self.assertEqual(plan["search_args"]["material_name"], "MatA")

    def test_no_auto_search_when_node_names_exist(self):
        raw_args = {"material_name": "MatA", "include_values": True, "node_names": ["Principled BSDF"]}
        normalized = {"material_name": "MatA", "include_values": True, "node_names": ["Principled BSDF"]}
        plan = plan_shader_inspect(raw_args, normalized)
        self.assertFalse(plan["auto_search"])

    def test_cost_estimate_levels(self):
        low = estimate_inspect_cost({"limit": 10, "compact": True, "include_values": False})
        high = estimate_inspect_cost({"limit": 80, "compact": False, "include_values": True})
        self.assertIn(low["risk_level"], ("low", "medium"))
        self.assertEqual(high["risk_level"], "high")


if __name__ == "__main__":
    unittest.main()
