# Reproducible performance checks

## Current evidence

The timing collector and report-export path have deterministic tests. A controlled benchmark for the current Full-model release is still pending. Earlier smoke tests used different models/UI conditions and partial body visibility; they are not a release baseline or end-to-end latency evidence.

## Capture a baseline

1. Connect laptop power; keep the power mode unchanged between runs.
2. Close other camera apps. Keep camera position, lighting, posture, backend, and background load consistent.
3. Use the same model, threshold, duration, and warmup for each repetition.
4. Run three 60-second trials per configuration with different report filenames.

```powershell
.\.venv\Scripts\python.exe webcam_tracker.py --headless --seconds 60 --warmup 15 --report reports/full-01.json
.\.venv\Scripts\python.exe webcam_tracker.py --headless --seconds 60 --warmup 15 --report reports/full-02.json
.\.venv\Scripts\python.exe webcam_tracker.py --headless --seconds 60 --warmup 15 --report reports/full-03.json
```

Download Lite with `download_model.py --variant lite` and add `--model models/pose_landmarker_lite.task` for separate comparisons. Report tracking coverage alongside speed. Repeat later with PPSSPP running to quantify resource contention, recording emulator settings and workload.

Headless and preview runs are different workloads. Headless mode skips display-only mirroring/copies and rendering. Do not mix their results or claim an optimization without equivalent before/after conditions.

Use `--practice --headless --seconds 60 --report reports/both-models-01.json` to measure capture with both body and hand models active without sending keys. Hand inference always mirrors its input for handedness. Headless practice stays paused, so this workload measures inference and does not score forward strikes. Interactive Test Gestures.cmd is required to calibrate and count actual attempts.

## Interpret the JSON

- `pipeline.submit_to_result`: submission/preprocessing start to callback entry.
- `pipeline.read_to_result`: completion of camera `read()` to callback entry. Exposure and earlier driver buffering are excluded.
- `count`: all post-warmup timing samples; `retained_samples`: samples used for percentiles.
- `mean_ms_all_samples`: cumulative mean after warmup.
- `p50_ms_recent_samples`, `p95_ms_recent_samples`, `p99_ms_recent_samples`: linearly interpolated quantiles over the most recent 4,096 samples. A 60-second run at 30 results/s fits inside this window.
- `completed_results`: all callbacks, including warmup. Top-level `observed_pose_results` counts results seen by the main loop.
- `capture_fps` and `completed_result_fps`: throughput over the capture-to-drain interval, including startup/shutdown.
- `captured_frames_not_submitted`: captures intentionally superseded or left at shutdown. This is not a camera-loss error rate.
- `quality_all_results`: presence and per-joint reliability counts, including warmup. A fast run with missing arms is not automatically better.
- `hand_pipeline`: hand callback count, results with hand observations, and submission-to-result timings. These samples include hand warmup and finish after landmark extraction in the callback; do not combine them with the pose timing series.
- `recognized_attacks`: motion events from the hand detector. Counts can be checked against labeled attempts, but do not prove native key delivery or visible game response.
- `input_press_counts`: successful keyboard-adapter key-down transitions for all eight actions. In practice these are simulated; in control they still do not prove visible game response. Holds count once until released.
- `hand_pipeline.detection_counts`: raw hand detections versus assigned identities and filter reasons. These distinguish hand acquisition from motion thresholds; assignment coverage is not gesture accuracy.
- `attack_sensitivity`: initial/final reach settings. Record changes during an interactive evaluation; compare accuracy only under matched settings.

Compare median and tail latency alongside throughput and tracking coverage. P99 from few samples is weak evidence; include counts, repetitions, model hashes, and hardware in published results.

## Metrics still to build

After gesture integration, label actual movement/strike attempts and measure precision, recall, false activations per minute, missed actions, and re-arm timing. Use the same evaluation protocol across configurations.

For the current hand detector, let calibration and hand readiness settle, then hold hands and torso still for 20 seconds with practice running. Compare `input_presses` for all eight actions before and after, and confirm `active_actions` starts empty. The two-second practice log retains brief press transitions that snapshots of held keys would miss. Then perform ten attempts for each action. Record the actual hand class shown, intended action, counter that changed, and whether an extra press occurred. Repeat across lighting and camera distances before presenting an accuracy claim.

Motion-to-visible-game latency requires physical motion and screen response on a common timebase, such as a suitable high-frame-rate external recording with consent. A `SendInput` return timestamp cannot establish that latency. Distinguish recognition delay from game-animation timing.

## Publish defensible results

Keep aggregate reports locally under `reports/` by default. Review environment details before sharing a report. Publish exact configurations, sample counts, three trial results, quality counts, and limitations. Never invent speedups, accuracy percentages, percentiles, or a baseline.
