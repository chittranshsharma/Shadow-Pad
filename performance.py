"""Bounded, thread-safe timing summaries. No frames or landmark coordinates stored."""

from collections import deque
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import threading


class TimingWindow:
    def __init__(self, capacity=4096):
        if capacity < 1:
            raise ValueError("Timing capacity must be positive.")
        self.values = deque(maxlen=capacity)
        self.count = 0
        self.total = 0.0

    def add(self, milliseconds):
        if not math.isfinite(milliseconds) or milliseconds < 0:
            raise ValueError("Timings must be finite and nonnegative.")
        self.values.append(float(milliseconds))
        self.count += 1
        self.total += milliseconds

    def summary(self):
        ordered = sorted(self.values)

        def percentile(fraction):
            if not ordered:
                return None
            position = (len(ordered) - 1) * fraction
            lower = math.floor(position)
            upper = math.ceil(position)
            return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 3)

        return {
            "count": self.count,
            "retained_samples": len(ordered),
            "sample_capacity": self.values.maxlen,
            "mean_ms_all_samples": round(self.total / self.count, 3) if self.count else None,
            "p50_ms_recent_samples": percentile(.50),
            "p95_ms_recent_samples": percentile(.95),
            "p99_ms_recent_samples": percentile(.99),
        }


class PipelineMetrics:
    def __init__(self, warmup_results=15, capacity=4096):
        if warmup_results < 0:
            raise ValueError("Warmup results must be nonnegative.")
        self.lock = threading.Lock()
        self.warmup_results = warmup_results
        self.submitted = 0
        self.completed = 0
        self.with_person = 0
        self.all_joints = 0
        self.joints = {index: 0 for index in (11, 12, 13, 14, 15, 16)}
        self.submit_to_result = TimingWindow(capacity)
        self.read_to_result = TimingWindow(capacity)

    def submitted_frame(self):
        with self.lock:
            self.submitted += 1

    def completed_frame(self, submit_ms, read_ms, has_person, reliable_joints):
        if any(not math.isfinite(value) or value < 0 for value in (submit_ms, read_ms)):
            raise ValueError("Timings must be finite and nonnegative.")
        with self.lock:
            self.completed += 1
            self.with_person += bool(has_person)
            self.all_joints += all(index in reliable_joints for index in self.joints)
            for index in self.joints:
                self.joints[index] += index in reliable_joints
            if self.completed > self.warmup_results:
                self.submit_to_result.add(submit_ms)
                self.read_to_result.add(read_ms)

    def summary(self, captured_frames, duration_seconds):
        if not math.isfinite(duration_seconds) or duration_seconds <= 0 or captured_frames < 0:
            raise ValueError("Duration must be positive and capture count nonnegative.")
        with self.lock:
            return {
                "captured_frames": captured_frames,
                "submitted_frames": self.submitted,
                "completed_results": self.completed,
                "captured_frames_not_submitted": max(0, captured_frames - self.submitted),
                "uncompleted_submissions": max(0, self.submitted - self.completed),
                "duration_seconds": round(duration_seconds, 3),
                "capture_fps": round(captured_frames / duration_seconds, 3),
                "completed_result_fps": round(self.completed / duration_seconds, 3),
                "timing_warmup_results_excluded": min(self.completed, self.warmup_results),
                "submit_to_result": self.submit_to_result.summary(),
                "read_to_result": self.read_to_result.summary(),
                "quality_all_results": {
                    "results_with_person": self.with_person,
                    "results_with_all_six_reliable_joints": self.all_joints,
                    "reliable_results_per_joint": dict(self.joints),
                },
                "interpretation": (
                    "Software timings only; camera timestamps are recorded after read(). "
                    "Percentiles use the most recent bounded sample window after warmup. "
                    "Capture frames not submitted include intentional superseding and shutdown. "
                    "No camera exposure, gesture-onset, input-to-game, or display latency measured."
                ),
            }


def environment(model):
    return {
        "python": platform.python_version(),
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "dependencies": {name: version(name) for name in ("mediapipe", "numpy", "opencv-contrib-python")},
        "model_name": Path(model).name,
        "model_sha256": hashlib.sha256(Path(model).read_bytes()).hexdigest(),
    }


def write_report(path, report):
    path = Path(path)
    payload = json.dumps({"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
                          **report}, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Refuse to overwrite an earlier run so benchmarks remain individually reviewable.
    with path.open("x", encoding="utf-8") as target:
        target.write(payload + "\n")
