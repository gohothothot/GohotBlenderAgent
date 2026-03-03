import importlib
import importlib.util
import pathlib
import sys
import tempfile
import shutil
import time
import unittest


def _repo_root():
    return pathlib.Path(__file__).resolve().parents[1]


def _load_file_module(mod_name: str, relative_path: str):
    module_path = _repo_root() / relative_path
    spec = importlib.util.spec_from_file_location(mod_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def _import_package_module(dotted_name: str):
    root = _repo_root()
    parent = root.parent
    if str(parent) not in sys.path:
        sys.path.insert(0, str(parent))
    return importlib.import_module(dotted_name)


class TestBackendAgent2Basics(unittest.TestCase):
    def test_mini_rewrite_rule_fallback(self):
        mod = _load_file_module("backend_mini_rewrite", "backend/core/mini_rewrite.py")
        rewriter = mod.MiniRewriter()
        out = rewriter.rewrite("创建一个2m立方体并加bevel", llm=None)
        self.assertIn("normalized_instruction", out)
        self.assertIn("extracted_terms", out)
        self.assertIn("task_type", out)
        self.assertIn("complexity", out)
        self.assertTrue(isinstance(out["extracted_terms"], list))

    def test_rag_store_seed_and_retrieve(self):
        mod = _load_file_module("backend_rag_stores", "backend/rag/stores.py")
        gs = mod.GlossaryStore.create()
        self.assertGreaterEqual(len(gs.entries), 30)
        rr = mod.auto_retrieve(
            normalized_instruction="Create UV Sphere and apply Principled BSDF material",
            extracted_terms=["UV Sphere", "Principled BSDF"],
            task_type="modeling+material",
        )
        self.assertIn("context_text", rr)
        self.assertIn("meta", rr)
        self.assertLessEqual(len(rr.get("context_text", "")), int(rr.get("meta", {}).get("max_chars", 1200)) + 64)

    def test_token_optimizer_deep_sleep_hook(self):
        mod = _load_file_module("backend_token_optimizer", "backend/utils/token_optimizer.py")
        called = {"v": 0}

        def _deep_sleep(_payload):
            called["v"] += 1

        budget = mod.TokenBudget(
            max_tokens=200,
            warning_threshold=0.1,
            compression_threshold=0.2,
            emergency_threshold=0.3,
            keep_recent_messages=2,
        )
        optimizer = mod.TokenOptimizer(budget=budget, deep_sleep_callback=_deep_sleep)
        large_messages = [
            {"role": "system", "content": "x" * 200},
            {"role": "user", "content": "u" * 500},
            {"role": "assistant", "content": "a" * 500},
            {"role": "tool", "content": "t" * 1500},
            {"role": "assistant", "content": "b" * 400},
        ]
        out = optimizer.optimize_messages(large_messages, strategy=mod.CompressionStrategy.BALANCED)
        self.assertTrue(out.get("deep_sleep_triggered"))
        self.assertEqual(called["v"], 1)
        self.assertTrue(out.get("meta", {}).get("compressed"))

    def test_memory_store_crud_and_search(self):
        mod = _load_file_module("backend_memory_store", "backend/memory/store.py")
        td = tempfile.mkdtemp(prefix="agent2_mem_")
        try:
            dbp = str(pathlib.Path(td) / "memory.db")
            store = mod.MemoryStore(db_path=dbp)
            sem_id = store.add_semantic(
                content="Use Bevel before Subdivision for hard-surface edges",
                category="workflow",
            )
            epi_id = store.add_episodic(
                session_id="s1",
                user_input="加倒角",
                normalized_input="Add Bevel modifier",
                tool_calls=[{"tool": "object.add_modifier_bevel"}],
                result="成功",
                success=True,
            )
            self.assertIsNotNone(store.get_by_id("semantic_memory", sem_id))
            self.assertIsNotNone(store.get_by_id("episodic_memory", epi_id))
            hits = store.search_similar("bevel hard surface", top_k=5)
            self.assertGreaterEqual(len(hits), 1)
            del store
            time.sleep(0.05)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_orchestrator_prepare_input_context_dry_run(self):
        try:
            orch_mod = _import_package_module("GohotBlenderAgent.agents.orchestrator")
        except Exception as e:
            raise unittest.SkipTest(f"orchestrator import unavailable: {e}") from e

        Orch = orch_mod.AgentOrchestrator
        orch = Orch.__new__(Orch)
        orch._mini_rewriter = None
        orch._executor = type("_DummyExec", (), {"_llm": None})()
        orch._memory_store = None
        orch._context_builder = None
        orch._reflection = None
        result = orch._prepare_input_context("创建一个立方体")
        self.assertIn("normalized", result)
        self.assertIn("enriched_message", result)


if __name__ == "__main__":
    unittest.main()

