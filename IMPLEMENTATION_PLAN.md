# ShadowPad implementation plan

## Scope

Build an on-device Windows webcam controller for PPSSPP with upper-body movement, reliable native input, minimal UI, and reproducible performance reporting. Publish the implementation and documentation to the user's Shadow-Pad repository. Do not include camera recordings, emulator/game files, model binaries, or local reports.

## Implemented

- Project-local Python environment; pinned direct dependencies and verified official model downloads.
- Single-slot threaded capture and asynchronous MediaPipe Full inference, with Lite available for comparison.
- Mirrored full-frame preview; optional diagnostics; confidence and stale-result handling.
- PPSSPP binding inspection and explicitly armed one-shot input tests. The user confirmed the test launcher works in PPSSPP.
- Shoulder-based neutral calibration and mirrored left/right movement with hysteresis.
- Upper-body rise for a one-shot Up hold; dip for a sustained Down hold. Movement does not require reliable elbows.
- Paused startup, explicit arming, modifier suppression, focus checks, tracking-loss pause, and multi-key release handling.
- Bounded callback-based timing statistics, warmup exclusion, P50/P95/P99, throughput/quality counters, environment/model identifiers, and JSON export.
- Headless path avoids display-only mirroring/copies. No speedup percentage is claimed without equivalent benchmark runs.
- Public README, architecture documentation, repeatable benchmark protocol, and Windows CI workflow.

## Verification

- Camera-independent automated tests cover tracking, preview preservation, binding parsing, input state transitions, movement calibration/mapping/re-arming, cleanup, metric math, concurrency, and report preservation.
- Dependency consistency and Python compilation are checked locally; GitHub CI runs separately after publication.
- Actual Full-model callback/report integration has been checked using synthetic in-memory frames, with no physical webcam opened. This verifies plumbing, not real-world accuracy or latency.
- Prior physical webcam runs established capture/model operation and occasional six-joint detection. Sustained elbow tracking was not established. Those differing development conditions are not a controlled Full-model benchmark.
- Live individual PPSSPP test inputs are user-confirmed. Integrated left/right/jump/duck movement still needs a live game acceptance run.

## Immediate acceptance steps

1. Open Tekken Practice mode and start Play ShadowPad.cmd.
2. Press C in the camera preview and sit still until calibrated.
3. Focus PPSSPP; press/release Ctrl+Alt+P to arm.
4. Verify lean left/right, rise/jump, dip/duck, and neutral release. Tune sensitivity if needed.
5. Verify pause, focus-loss release, and shoulder-tracking-loss release. Re-arm explicitly afterward.
6. Record consistent headless Full/Lite runs using docs/PERFORMANCE.md. Publish measured results only after reviewing configuration and sample counts.

## Next milestones

- Refine movement thresholds against actual gameplay and relaxed-posture feedback.
- Add independent arm strike detection and four attack gestures.
- Evaluate labeled gesture precision/recall and false activations per minute.
- Measure motion-to-visible-game latency separately from software timing.

## Publication

The user authorized GitHub publication. Preserve existing remote work and avoid force pushes. Publish only reviewed project sources/docs/tests, then verify the remote commit and CI status. Keep local and remote Git history aligned.
