# Describing ShadowPad accurately

Current implementation supports a useful systems/computer-vision project description:

> Built a Windows webcam controller using Python, OpenCV, and on-device MediaPipe pose estimation; implemented calibrated shoulder movement and wrist-based attack gestures with focus-aware native input and tracking-loss release handling.

Additional evidence-backed bullets:

- Designed a threaded capture pipeline with a latest-frame buffer and asynchronous inference, preserving frame/landmark alignment while bounding application-level backlog.
- Added warmup-aware P50/P95/P99 timing reports, throughput and tracking-coverage counters, and deterministic tests for concurrency, input lifecycle, calibration, and failure handling.
- Implemented a guarded Windows scan-code adapter supporting simultaneous direction keys, explicit arming, and cleanup after uncertain input failures.

Describe MediaPipe as pretrained pose estimation, not a model trained for this project. The input test launcher and left/right/jump gestures are manually confirmed in PPSSPP; duck and attack gestures still need live acceptance.

After controlled benchmarks and gameplay evaluation, add the measured configuration, sample counts, P95 timing boundary, false-activation rate, and labeled gesture accuracy. Until then, do not claim sub-X-ms gameplay latency, a speedup percentage, production readiness, or a recognition accuracy percentage.
