import importlib.util
import pathlib
import tempfile
import unittest


def _load_vector_store_module():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    module_path = repo_root / "context" / "vector_store.py"
    spec = importlib.util.spec_from_file_location("vector_store_module", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestVectorStore(unittest.TestCase):
    def setUp(self):
        mod = _load_vector_store_module()
        self.Store = mod.SimpleVectorStore

    def test_upsert_search_and_reload(self):
        with tempfile.TemporaryDirectory() as td:
            path = str(pathlib.Path(td) / "vs.json")
            store = self.Store(storage_path=path)
            store.upsert("doc:1", "Emission node controls glow strength", {"kind": "node", "material_name": "M1"})
            store.upsert("doc:2", "Roughness and metallic on principled bsdf", {"kind": "node", "material_name": "M1"})
            store.save()

            hit = store.search("glow emission", top_k=2, metadata_filter={"material_name": "M1"})
            self.assertGreaterEqual(len(hit), 1)
            self.assertEqual(hit[0]["doc_id"], "doc:1")

            reloaded = self.Store(storage_path=path)
            hit2 = reloaded.search("roughness", top_k=2)
            self.assertGreaterEqual(len(hit2), 1)
            self.assertEqual(hit2[0]["doc_id"], "doc:2")


if __name__ == "__main__":
    unittest.main()
