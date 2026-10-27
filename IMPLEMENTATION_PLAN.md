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
- Replaced unreliable pose-wrist attack heuristics with the official Gesture Recognizer hand model. Closed-fist forward pushes map to Square/Triangle; open-palm forward pushes map to Cross/Circle. Median filtering, stable guards, palm expansion, motion timing, torso-scale rejection, and retraction gate each event.
- Test Gestures.cmd uses the same detector with a keyboard adapter that has no native API calls. The preview shows actual hand class/confidence, guard state, expansion ratio, and per-action counts. Game mode keeps expanded diagnostics behind Tab.
- Live practice exposed a visible fist getting stuck before ready. Guard learning now uses five-sample median confidence and robust stability checks, preserves observations across brief uncertain/body gaps, accepts any fully visible hand position, and displays the specific blocking reason. A 100% classifier score is not required.
- Paused startup, explicit arming, modifier suppression, focus checks, immediate release on tracking gaps with automatic two-result recovery, and multi-key release handling.
- Bounded callback-based timing statistics, warmup exclusion, P50/P95/P99, throughput/quality counters, environment/model identifiers, and JSON export.
- Camera-only headless runs avoid display-only mirroring/copies; hand inference requires mirrored input even in headless practice. No speedup percentage is claimed without equivalent benchmark runs.
- Public README, architecture documentation, repeatable benchmark protocol, and Windows CI workflow.

## Verification

- Camera-independent automated tests cover tracking, preview preservation, binding parsing, input state transitions, movement calibration/mapping/re-arming, cleanup, metric math, concurrency, and report preservation.
- Dependency consistency and Python compilation are checked locally; GitHub CI runs separately after publication.
- Actual Full-model callback/report integration has been checked using synthetic in-memory frames, with no physical webcam opened. This verifies plumbing, not real-world accuracy or latency.
- Prior physical webcam runs established capture/model operation and occasional six-joint detection. Sustained elbow tracking was not established. Those differing development conditions are not a controlled Full-model benchmark.
- Live individual PPSSPP test inputs and integrated left/right/jump movement are user-confirmed. Repeated live reports rejected the prior attack heuristics as inaccurate; those reports are the reason for replacing the hand-input path.
- The combined pose/hand pipeline was run on the physical webcam without game injection or recording. One pass delivered about one frame/s with no detections; a second pass delivered about 25 callback results/s and detected shoulders, with wrists below frame and no hand detections. These short runs verify model/capture plumbing, not recognition accuracy or a repeatable benchmark.
- The actual hand model recognized Google's reference fist image above the required confidence and rejected a reference pointing-up shape as an attack. Applying a synthetic approach/return scaling sequence to the reference fist image through the real classifier and motion detector produced exactly one punch event. All images stayed in memory. This verifies the recognition plumbing, not physical punch accuracy.
- Deterministic tests cover all four forward actions, idle jitter, shape changes, lowering hands, scale drift, hand rotation, tracking jumps/gaps, duplicate identity, stale observations, practice-mode isolation from native input, one event per stroke, and bounded key pulses. No labeled live punch/kick accuracy is claimed.

## Immediate acceptance steps

1. Start Test Gestures.cmd, calibrate shoulders with C, and start practice with A. Confirm actual fist/palm labels and each hand's ready state.
2. At rest for 20 seconds, confirm counters do not increase. Perform ten forward closed-fist pushes and ten open-palm pushes per hand, retracting after each; count hits, misses, and wrong actions.
3. Correct remaining live failures using the hand label, guard state, size ratio, and affected action as evidence. H relearns hand guards without recalibrating shoulders.
4. Open Tekken Practice and Play ShadowPad.cmd. Calibrate with C, press A, and focus PPSSPP within five seconds. Verify the same four gestures alongside movement.
5. Verify explicit pause and focus-loss release; tracking gaps should release inputs and recover automatically after two good shoulder results without recalibration.
6. Record consistent benchmark runs using docs/PERFORMANCE.md. Publish metrics only with the exact workload, sample counts, and timing boundary.

## Next milestones

- Refine duck and attack thresholds against labeled live gameplay and relaxed-posture feedback. Verify wrists remain in view during actual punches and kick-button gestures.
- Evaluate labeled gesture precision/recall and false activations per minute.
- Measure motion-to-visible-game latency separately from software timing.

## Publication

The user authorized GitHub publication. Preserve existing remote work and avoid force pushes. Publish only reviewed project sources/docs/tests, then verify the remote commit and CI status. Keep local and remote Git history aligned.
