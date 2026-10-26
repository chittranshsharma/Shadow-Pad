# Project instructions

## Purpose and authorized scope

Build ShadowPad, a local Windows webcam gesture controller for PPSSPP / Tekken 6, using only the upper body visible above a laptop on a table.

Current scope includes camera tracking, PPSSPP input tests, calibrated left/right/jump/duck movement, latency instrumentation, public documentation, automated checks, and publication to the user's Shadow-Pad GitHub repository. Attack gesture recognition remains a future milestone. Do not change PPSSPP settings automatically; read its existing bindings.

## Implementation

- Use Python, OpenCV, NumPy, and the MediaPipe Tasks Pose Landmarker API. The default is the official Full model with one person; Lite remains available for comparison.
- Keep the first version small. Use a local virtual environment and pin dependencies after verification. No backend, cloud inference, database, custom model training, or virtual controller drivers are needed.
- Treat shoulders, elbows, and wrists as the required tracked joints. Do not require legs or hips. Hidden or low-confidence joints must be reported as missing rather than accepted as reliable.
- The user wants a large, relaxed camera view with minimal UI. Use the full camera frame without a framing box, sidebar, or guard-position requirement. Keep diagnostics behind Tab; F toggles fullscreen. Report shoulders/wrists separately when elbows are uncertain. Never lower confidence thresholds or invent elbow positions just to show 6/6. Future movement must depend on shoulders, not elbow readiness; punch-specific requirements belong to that later milestone.
- Mirror the preview, preserve anatomical left/right joint labels, and explain which side is which.
- Keep fresh frames; avoid an unbounded capture or inference queue. Label processing and result-age metrics accurately; they are not end-to-end game latency.
- Release the webcam and close windows on exit and errors. Keep camera data in memory; do not record, save, or upload frames without a user request.
- Input tests and gesture control start paused. Check the foreground PPSSPP executable before each key-down; release held keys on pause, focus loss, invalid/stale tracking, exit, or error. Movement holds can persist while fresh tracking requests them; individual test holds are bounded. Never report SendInput success as proof of the visible game response.
- Keep models and virtual environments out of Git. Download models from the official Google model host.

## Validation and communication

- Add small meaningful tests for tracking-quality decisions and other nontrivial logic without requiring a webcam.
- Run the automated checks and a short real camera/model smoke test when hardware is available. Report camera access, model inference, detected landmarks, and manual visual checks separately.
- Never call milestone 1 visually verified until the user or an observed preview confirms upper-body tracking. If the user is absent or out of frame, report that clearly.
- Update IMPLEMENTATION_PLAN.md with completed work, actual validation, limitations, and the next authorized step. Keep README.md run instructions current.
- Commit/publication to https://github.com/chittranshsharma/Shadow-Pad is authorized. Exclude environments, models, game images, personal captures, and generated reports. Do not force-push or install system-wide components. Keep performance claims tied to reproducible measurements.
