import pathlib
import tempfile
import unittest

import action_log


class TestActionLogMetrics(unittest.TestCase):
    def test_performance_summary_generated(self):
        with tempfile.TemporaryDirectory() as td:
            old_dir = action_log._LOG_DIR
            old_metrics = action_log._METRICS_FILE
            old_session = action_log._current_session
            try:
                action_log._LOG_DIR = str(pathlib.Path(td))
                action_log._METRICS_FILE = str(pathlib.Path(td) / "metrics.jsonl")
                action_log._current_session = None

                sid = action_log.start_session("test request")
                action_log.log_metric("shader_prewarm", {"success": True, "elapsed_ms": 120})
                action_log.log_metric("shader_context_attach", {"source": "prewarm_cache"})
                action_log.log_metric("shader_search_index_result", {"success": True, "candidate_count": 3})
                action_log.end_session("done")

                saved = action_log.get_session_log(sid)
                self.assertIsNotNone(saved)
                self.assertIn("performance_summary", saved)
                self.assertIn("performance_brief", saved)

                summary = saved["performance_summary"]
                self.assertGreaterEqual(summary["metric_events"], 3)
                self.assertEqual(summary["shader_prewarm"]["success"], 1)
                self.assertEqual(summary["shader_context_attach"]["prewarm_cache"], 1)

                metrics_records = action_log.get_recent_metrics(10)
                self.assertGreaterEqual(len(metrics_records), 4)  # 3 metric_event + 1 session_summary
                self.assertEqual(metrics_records[0].get("kind"), "session_summary")
            finally:
                action_log._LOG_DIR = old_dir
                action_log._METRICS_FILE = old_metrics
                action_log._current_session = old_session


if __name__ == "__main__":
    unittest.main()
