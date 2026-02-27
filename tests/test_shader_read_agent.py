import unittest
import importlib.util
import pathlib


def _load_shader_read_agent_class():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    module_path = repo_root / "agents" / "shader_read_agent.py"
    spec = importlib.util.spec_from_file_location("shader_read_agent_module", module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ShaderReadAgent


class TestShaderReadAgent(unittest.TestCase):
    def test_build_context_with_candidates(self):
        ShaderReadAgent = _load_shader_read_agent_class()

        def fake_run_tool(name, args):
            if name == "shader_list_materials":
                return {"success": True, "result": [{"name": "MatA"}, {"name": "MatB"}], "error": None}
            if name == "shader_get_material_summary":
                return {"success": True, "result": {"node_count": 12, "link_count": 10, "node_types_used": {"ShaderNodeBsdfPrincipled": 1}, "key_parameters": {"Principled BSDF": {"Roughness": 0.5}}}, "error": None}
            if name == "shader_search_index":
                return {"success": True, "result": {"candidates": [{"node_name": "Principled BSDF", "node_type": "ShaderNodeBsdfPrincipled"}]}, "error": None}
            if name == "shader_inspect_nodes":
                return {"success": True, "result": {"nodes": [{"name": "Principled BSDF"}]}, "error": None}
            return {"success": False, "result": None, "error": f"unknown tool {name}"}

        agent = ShaderReadAgent(fake_run_tool)
        result = agent.build_context("帮我调 MatA 的 roughness")
        self.assertTrue(result["success"])
        self.assertEqual(result["material_name"], "MatA")
        self.assertIn("[Shader Context]", result["context_text"])
        self.assertTrue(result["metrics"]["used_inspect"])

    def test_build_context_without_materials(self):
        ShaderReadAgent = _load_shader_read_agent_class()

        def fake_run_tool(name, args):
            if name == "shader_list_materials":
                return {"success": True, "result": [], "error": None}
            return {"success": False, "result": None, "error": "not used"}

        agent = ShaderReadAgent(fake_run_tool)
        result = agent.build_context("任意需求")
        self.assertFalse(result["success"])
        self.assertEqual(result["material_name"], None)


if __name__ == "__main__":
    unittest.main()
