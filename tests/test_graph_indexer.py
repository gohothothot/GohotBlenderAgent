import importlib.util
import pathlib
import sys
import types
import unittest


def _load_indexer_module():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    context_dir = repo_root / "context"

    # 构造可相对导入的 context 包环境
    pkg = types.ModuleType("context")
    pkg.__path__ = [str(context_dir)]
    sys.modules["context"] = pkg

    vs_spec = importlib.util.spec_from_file_location("context.vector_store", context_dir / "vector_store.py")
    vs_mod = importlib.util.module_from_spec(vs_spec)
    sys.modules["context.vector_store"] = vs_mod
    vs_spec.loader.exec_module(vs_mod)

    idx_spec = importlib.util.spec_from_file_location("context.indexer", context_dir / "indexer.py")
    idx_mod = importlib.util.module_from_spec(idx_spec)
    sys.modules["context.indexer"] = idx_mod
    idx_spec.loader.exec_module(idx_mod)
    return idx_mod


class TestGraphIndexer(unittest.TestCase):
    def setUp(self):
        mod = _load_indexer_module()
        self.GraphIndexer = mod.GraphIndexer
        self.indexer = self.GraphIndexer()

    def test_upsert_from_summary_and_query(self):
        self.indexer.upsert_from_summary(
            "MatA",
            {
                "node_count": 3,
                "link_count": 2,
                "node_types_used": {"ShaderNodeBsdfPrincipled": 1, "ShaderNodeTexNoise": 2},
                "node_index": [
                    {"name": "Principled BSDF", "type": "ShaderNodeBsdfPrincipled", "label": ""},
                    {"name": "Noise Texture", "type": "ShaderNodeTexNoise", "label": "Noise"},
                    {"name": "Noise Texture.001", "type": "ShaderNodeTexNoise", "label": ""},
                ],
            },
        )
        summary = self.indexer.get_summary("MatA")
        self.assertTrue(summary["exists"])
        self.assertEqual(summary["total_nodes"], 3)
        self.assertEqual(summary["indexed_nodes"], 3)

        page = self.indexer.query_nodes("MatA", keyword="noise", limit=1, offset=0)
        self.assertEqual(page["total"], 2)
        self.assertEqual(len(page["items"]), 1)
        self.assertTrue(page["has_more"])

    def test_upsert_from_inspect_merges_nodes(self):
        self.indexer.upsert_from_inspect(
            "MatB",
            {
                "graph_summary": {"total_nodes": 2, "total_links": 1, "node_type_top": []},
                "nodes": [
                    {"name": "A", "type": "TypeA", "label": ""},
                    {"name": "B", "type": "TypeB", "label": ""},
                ],
            },
        )
        self.indexer.upsert_from_inspect(
            "MatB",
            {
                "graph_summary": {"total_nodes": 3, "total_links": 2, "node_type_top": []},
                "nodes": [
                    {"name": "B", "type": "TypeB2", "label": "updated"},
                    {"name": "C", "type": "TypeC", "label": ""},
                ],
            },
        )
        page = self.indexer.query_nodes("MatB", limit=10)
        self.assertEqual(page["total"], 3)
        b = [n for n in page["items"] if n["name"] == "B"][0]
        self.assertEqual(b["type"], "TypeB2")

    def test_semantic_search(self):
        self.indexer.upsert_from_summary(
            "MatC",
            {
                "node_count": 2,
                "link_count": 1,
                "node_types_used": {"ShaderNodeEmission": 1},
                "node_index": [
                    {"name": "Emission", "type": "ShaderNodeEmission", "label": "Glow"},
                    {"name": "ColorRamp", "type": "ShaderNodeValToRGB", "label": ""},
                ],
            },
        )
        result = self.indexer.semantic_search("MatC", "glow emission", top_k=5)
        self.assertGreaterEqual(result["count"], 1)
        node_hits = [i for i in result["items"] if i["metadata"].get("kind") == "node"]
        self.assertTrue(any(h["metadata"].get("node_name") == "Emission" for h in node_hits))


if __name__ == "__main__":
    unittest.main()
