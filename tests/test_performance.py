import json
from pathlib import Path
import tempfile
import threading
import unittest

from performance import PipelineMetrics, TimingWindow, write_report


class PerformanceTests(unittest.TestCase):
    def test_percentiles_use_linear_interpolation(self):
        window = TimingWindow()
        for value in (10, 20, 30, 40, 50):
            window.add(value)
        summary = window.summary()
        self.assertEqual(summary["p50_ms_recent_samples"], 30)
        self.assertEqual(summary["p95_ms_recent_samples"], 48)
        self.assertEqual(summary["p99_ms_recent_samples"], 49.6)

    def test_retention_is_bounded_and_mean_covers_all_samples(self):
        window = TimingWindow(capacity=2)
        for value in (10, 20, 90):
            window.add(value)
        summary = window.summary()
        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["retained_samples"], 2)
        self.assertEqual(summary["mean_ms_all_samples"], 40)
        self.assertEqual(summary["p50_ms_recent_samples"], 55)

    def test_empty_timings_are_unknown_not_zero_latency(self):
        self.assertIsNone(TimingWindow().summary()["p95_ms_recent_samples"])

    def test_invalid_times_do_not_mutate_counts(self):
        metrics = PipelineMetrics(warmup_results=0)
        for value in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                metrics.completed_frame(value, 10, True, set())
        self.assertEqual(metrics.summary(0, 1)["completed_results"], 0)

    def test_warmup_excludes_timings_but_not_quality_or_throughput(self):
        metrics = PipelineMetrics(warmup_results=1)
        for processing in (200, 20):
            metrics.submitted_frame()
            metrics.completed_frame(processing, processing + 5, True, {11, 12})
        summary = metrics.summary(3, 2)
        self.assertEqual(summary["submit_to_result"]["mean_ms_all_samples"], 20)
        self.assertEqual(summary["read_to_result"]["p50_ms_recent_samples"], 25)
        self.assertEqual(summary["completed_result_fps"], 1)
        self.assertEqual(summary["captured_frames_not_submitted"], 1)
        self.assertEqual(summary["quality_all_results"]["results_with_person"], 2)

    def test_concurrent_callbacks_do_not_lose_results(self):
        metrics = PipelineMetrics(warmup_results=0)
        def record():
            for _ in range(100):
                metrics.submitted_frame()
                metrics.completed_frame(10, 12, False, set())
        workers = [threading.Thread(target=record) for _ in range(4)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        summary = metrics.summary(400, 10)
        self.assertEqual(summary["completed_results"], 400)
        self.assertEqual(summary["uncompleted_submissions"], 0)

    def test_report_roundtrip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runs" / "run.json"
            write_report(path, {"pipeline": PipelineMetrics().summary(0, 1)})
            report = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(report["schema_version"], 1)
            self.assertIn("created_at_utc", report)
            with self.assertRaises(FileExistsError):
                write_report(path, {"changed": True})
            self.assertEqual(report, json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
