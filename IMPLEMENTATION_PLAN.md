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
- Four wrist-and-shoulder attack gestures: left/right forward or inward strikes for Square/Triangle and left/right downward strikes for Cross/Circle, with one pulse per strike and return-to-guard rearming. Elbows are optional.
- Paused startup, explicit arming, modifier suppression, focus checks, tracking-loss pause, and multi-key release handling.
- Bounded callback-based timing statistics, warmup exclusion, P50/P95/P99, throughput/quality counters, environment/model identifiers, and JSON export.
- Headless path avoids display-only mirroring/copies. No speedup percentage is claimed without equivalent benchmark runs.
- Public README, architecture documentation, repeatable benchmark protocol, and Windows CI workflow.

## Verification

- Camera-independent automated tests cover tracking, preview preservation, binding parsing, input state transitions, movement calibration/mapping/re-arming, cleanup, metric math, concurrency, and report preservation.
- Dependency consistency and Python compilation are checked locally; GitHub CI runs separately after publication.
- Actual Full-model callback/report integration has been checked using synthetic in-memory frames, with no physical webcam opened. This verifies plumbing, not real-world accuracy or latency.
- Prior physical webcam runs established capture/model operation and occasional six-joint detection. Sustained elbow tracking was not established. Those differing development conditions are not a controlled Full-model benchmark.
- Live individual PPSSPP test inputs and integrated left/right/jump movement are user-confirmed. Duck did not trigger reliably in the first live run, so its shoulder threshold was lowered and visible head lowering was added. Duck and four attacks still need live game acceptance.

## Immediate acceptance steps

1. Open Tekken Practice mode and start Play ShadowPad.cmd.
2. Press C in the camera preview and sit still until calibrated.
3. Press A in the preview and focus PPSSPP during the five-second countdown.
4. Verify lean left/right, rise/jump, shoulder dip/duck, and neutral release. Then bring hands to chest-height guard and check left/right inward punches and downward kick-button gestures. Tune sensitivity if needed.
5. Verify pause, focus-loss release, and shoulder-tracking-loss release. Re-arm explicitly afterward.
6. Record consistent headless Full/Lite runs using docs/PERFORMANCE.md. Publish measured results only after reviewing configuration and sample counts.

## Next milestones

- Refine duck and attack thresholds against actual gameplay and relaxed-posture feedback.
- Evaluate labeled gesture precision/recall and false activations per minute.
- Measure motion-to-visible-game latency separately from software timing.

## Publication

The user authorized GitHub publication. Preserve existing remote work and avoid force pushes. Publish only reviewed project sources/docs/tests, then verify the remote commit and CI status. Keep local and remote Git history aligned.
