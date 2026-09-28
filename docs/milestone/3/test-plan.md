# Milestone 3 — Camera Service Test Plan

**Status:** Software implementation and automated tests are complete; MacBook runtime acceptance is partially verified; Playbox/Aukey acceptance remains pending
**Scope source:** `docs/milestone/3/milestone-3-plan.md`
**Requirements source:** `docs/2026-07-22-01-bmo-ai-companion-specs.md` § Milestone 3
**Validation order:** Static/isolated → runtime → system and termination
**Hardware order:** MacBook built-in camera first; Aukey camera on the FPT Playbox later

This document defines tests and acceptance procedures only; it does not implement tests. The MacBook stage validates behavior and the native camera backend. It does not prove Aukey compatibility, S905X performance, or Playbox service startup.

**Latest local run:** 2026-09-29 — 51 automated tests passed. macOS camera permission was granted after an initial denied attempt. AVFoundation opened the MacBook camera at 1920×1080; `/health` returned 200; live `face_position` MQTT events were observed. With `active_fps: 30`, active capture reads reached about 30 FPS and analysis about 27 FPS. In sleep, analysis was about 4.9 FPS; AVFoundation accepted the 5-FPS request but `/status` showed `capture_fps_request_applied: false` and capture reads stayed about 30 FPS.

**MacBook acceptance record:** MQTT subscribers captured `PERSON_DETECTED`, `PERSON_LEFT`, re-detection, face positions from left through right (x≈0.27 to 0.79), `MOTION`, and `NO_MOTION`. `/status` showed presence transitions and the 10-second leave event; unit tests cover exact timeout/cancellation and transition-only behavior. Controlled position events produced M2 API states `look_left`, `idle`, and `look_right`. A Mosquitto restart was followed by healthy camera status and resumed camera-event publishing. The native M2 window was not visually inspected; the Mac camera backend did not apply its requested 5-FPS capture setting; the privacy artifact audit and Aukey/Playbox checks remain pending.

**MacBook checks completed:** camera access/open, frame resolution, API health/status, live event topics, face-state synchronization, 5-FPS sleep analysis, active-rate restoration, local Mosquitto restart/reconnect, and SIGTERM followed by successful camera reopen. AVFoundation continued reading at about 30 FPS in sleep despite reporting the 5-FPS request was not applied; sensor-level low-power behavior remains pending target-camera validation.

**Capture-rate caveat:** the MacBook backend did not reduce sensor/read rate in sleep, although the service throttled analysis to about 4.9 FPS and restored active processing after wake. Treat sensor-level AC-04 power behavior as pending target/backend validation.

## 1. Existing validation command catalog

Use only the repository's established validation patterns:

| Purpose | Existing command pattern | M3 use |
| --- | --- | --- |
| Python tests | From M2 README: `.venv/bin/python -m pytest tests/ -v` | Run from `services/bmo-camera` after its environment and tests exist |
| Observe MQTT events | From M2 README: `mosquitto_sub -t bmo/face/# -v` | Subscribe to `bmo/camera/#` while running camera acceptance |
| Publish MQTT control | From M2 README: `mosquitto_pub -t <topic> -m '<json>'` | Set the face to `sleep` / `idle` to test the camera FPS policy |
| Check local API | From M2 README: `curl -s http://127.0.0.1:5200/health` and `/state` | Use the same `curl -s` pattern for camera `/health` and `/status` on port 5201 |
| Start a Linux service | From M2 README: copy/enable the systemd unit and inspect its journal | Repeat for `bmo-camera` on the Playbox only |
| Exercise broker restart | M2 manual acceptance restarts Mosquitto; macOS README uses `brew services restart mosquitto` | Verify the camera continues capture and resumes event publishing |

No static linter, coverage reporter, benchmark executable, frame-recording tool, or additional monitoring package is currently cataloged. Do not add one as part of this test plan. Do not report a coverage percentage. CPU/RSS are not exposed by the planned camera `/status`; mark those measurements human-only until an approved repository interface provides them.

## 2. Data-flow and privacy boundary

Expected path:

```text
MacBook/Aukey camera
  → volatile frame memory
  → local OpenCV resize and detection
  → small derived state/events
  → localhost Mosquitto and camera /status
  → bmo-face consumes person/position events
```

Frames must not be written to disk, included in logs, sent through MQTT, returned by `/health` or `/status`, or sent to any network endpoint. MQTT payloads contain only the event metadata in the M3 plan. The camera API is localhost-only and reports status/derived values, never images. A successful automated test of the code boundary does not replace the human-only device privacy check.

## 3. Acceptance-criterion traceability

| M3 criterion | Static / isolated | Runtime | System / termination | Observable effect and boundary |
| --- | --- | --- | --- | --- |
| **AC-01 Presence events**: one `PERSON_DETECTED` on presence; one `PERSON_LEFT` after 10 seconds without a face; reset on re-detection | Fake-clock state tests for initial `unknown`, present/absent transitions, timeout boundary, and cancellation | MacBook camera plus MQTT observation; repeat with Aukey later | Camera-open failure must not masquerade as absence; restart and reinitialize cleanly | Only `{}` events on `bmo/camera/person_detected` and `bmo/camera/person_left`; `PERSON_LEFT` starts the M2 five-minute sleep timer |
| **AC-02 Face position**: normalized `x`, largest face, movement updates and heartbeat | Synthetic bounding-box tests at x=0, 0.4, 0.6, 1.0; throttle/heartbeat tests | Hold a person left/center/right and observe MQTT and M2 face response | Verify stable position while camera stays open and after recovery | Publish only `{"x":0.0..1.0}` to `bmo/camera/face_position`; heartbeat at least every 400 ms, capped at 5 Hz; no frames |
| **AC-03 Motion**: thresholded `MOTION` and `NO_MOTION` transitions | Synthetic frame sequences; threshold, initial quiet interval, debounce, and timer-boundary cases | Create motion, then remain still; observe one transition per state change | Verify stable behavior through camera reconnect | Publish `{}` to `bmo/camera/motion` and `bmo/camera/no_motion`; score stays internal |
| **AC-04 Sleep rate**: 5 processed FPS during `sleep`, active camera-supported rate otherwise | Pure policy tests for active, sleep, wake, and invalid/unknown states | MQTT sleep/idle events; inspect the planned `/status` FPS fields | Start/restart camera while face is already asleep; verify initial state sync | Subscribe to `bmo/face/state`, initialize through `GET /state`, then apply queued MQTT updates; the public API reports rates, not frames |
| **AC-05 On-device privacy**: no frame leaves memory or device | Unit/component checks that capture buffers do not enter publisher, logger, API, or file-write paths | Confirm only JSON event metadata appears on `bmo/camera/#`; check API responses | Human-only Playbox check for files/logs/network destinations during extended run | No image/video files, raw frame MQTT payloads, frame-bearing logs, or remote vision traffic |
| **AC-06 MQTT contract/reconnect**: topic names, payloads, broker outage recovery | Contract tests for topics, JSON object shapes, invalid messages, and reconnect policy | Observe events with `mosquitto_sub`; restart local Mac broker | Repeat broker restart on Playbox; capture loop continues and publishing resumes | Broker carries only documented JSON events; frame acquisition remains local during outage |
| **AC-07 Health, errors, and lifecycle**: truthful status and explicit camera failure | Fake capture open/read errors, API response contract, release-on-shutdown tests | `curl -s` `/health` and `/status`; unplug/disable the Mac camera only when safe | Playbox camera permission, systemd cold boot/restart, SIGTERM release | Health must not claim a working camera when capture is unavailable; API exposes status only; shutdown releases capture/MQTT/API |
| **AC-08 Active/sleep performance**: full supported active rate and 5-FPS sleep analysis | FPS-policy tests with injected measured rates | MacBook capture reads/analysis reached about 30 FPS active; sleep analysis measured about 4.9 FPS | Measure Aukey/S905X capture FPS, processing FPS, CPU, and RSS under both modes | `/status` exposes reported capture FPS, successful read FPS, and processed FPS; CPU/RSS are not repository-exposed and remain human-only |

## 4. Layer 1 — Static and isolated tests

Run this layer first. It must not require a physical camera, a running broker, a browser, or systemd.

### Unit tests

Planned test coverage, using deterministic clocks and injected dependencies:

- Config: defaults, MacBook backend/device override, active-rate `auto`, 5-FPS sleep setting, API/MQTT ports, invalid ranges, and explicit errors.
- Presence state: initial unknown state, no-face startup timer, face found just before/at/after timeout, continuous presence without duplicate messages, re-detection cancellation, and monotonic-clock timing.
- Face position: largest-face selection, x normalization including both frame edges, center thresholds, minimum meaningful delta, 400-ms heartbeat, and 5-Hz maximum.
- Motion: score threshold crossing, no repeated `MOTION`, configured quiet timeout, initial `NO_MOTION` interval, re-entry into motion, noise/debounce, and timer reset.
- Rate policy: active full-rate setting, sleep at 5 FPS, leaving sleep, unknown face state, initial-state API timeout, and state-message/API race ordering.
- MQTT contract: exact topics and minimal payloads, invalid/non-object payloads, and reconnect backoff.
- Privacy: frames are not passed to MQTT/API/logging and no code path writes image/video files.

### Contract tests

- Compare camera publish topic names and payloads to the M3 plan and M2 face subscriber contract.
- Confirm `bmo/face/state` expects `{"state":"<state_name>"}` and startup uses the documented localhost `/state` response shape.
- Reject malformed face-state data without changing the active/sleep policy.
- Confirm motion scores remain internal; published `MOTION` and `NO_MOTION` payloads stay `{}`.

### Component tests

- Feed synthetic no-face, one-face, and multi-face frames to the detector; assert largest-face x and presence transitions.
- Feed synthetic static/noisy/moving frames to the motion detector; assert transition-only publishing.
- Exercise resize with varied aspect ratios and small/empty/read-failed frames without displaying or saving frames.
- Inject camera open/read/reopen failures; verify status and release behavior.

### Expected result

The full camera pytest suite passes using only fakes/synthetic frames. It covers M3 state, contract, failure, and privacy code paths; it does not establish real-camera accuracy, FPS, systemd behavior, or a numerical coverage percentage.

**Catalog command** (once the M3 environment exists):

```bash
cd services/bmo-camera
.venv/bin/python -m pytest tests/ -v
```

## 5. Layer 2 — Runtime tests

Run with the MacBook built-in camera and the existing local Mosquitto broker. These are live integration checks, not target-device sign-off.

### Runtime sequence

1. Grant the terminal/Python process macOS camera permission. Start the camera service and bmo-face using their documented run procedures.
2. Use the catalog's `mosquitto_sub -t bmo/face/# -v` pattern, substituting `bmo/camera/#`, to observe camera event publications.
3. Use the catalog's `curl -s` pattern against `http://127.0.0.1:5201/health` and `/status`. Confirm status contains reported capture FPS, successful read FPS, processing FPS, presence/motion metadata, and no image fields.
4. Show a person; verify one `PERSON_DETECTED`. Move left, center, and right; verify normalized x values and the face responds. Hold still for over one second to test the heartbeat.
5. Leave the camera view; verify no `PERSON_LEFT` before 10 seconds, one event at the absence timeout, and cancellation if the face returns in time. Confirm the M2 sleep timer starts from the event.
6. Create visible motion, then remain still; verify one `MOTION` and one `NO_MOTION` after the configured interval. Repeat with no initial motion to test the startup quiet interval.
7. If needed, move out of camera view, then publish M2's `sleep` state using the existing `bmo/face/set_state` catalog command; verify `/status` reports about 5 processed FPS and record `capture_read_fps` plus `capture_fps_request_applied`. Return to `idle`; verify active processing resumes. Start/restart the camera while the face is already asleep to verify API state sync.
8. Restart the local Mosquitto service using the existing macOS README procedure. Verify frames continue to process locally and MQTT events resume after reconnect.
9. Stop the camera service using the documented signal/shutdown procedure. Confirm the camera becomes available again and no frame artifacts were created.

**MacBook results observed (partial Stage A):** `/status` reported the camera healthy with 1920×1080 frames. MQTT subscribers captured `PERSON_DETECTED`, `PERSON_LEFT`, re-detection, face-position values spanning x≈0.27–0.79, `MOTION`, and `NO_MOTION`. The M2 API showed left/center/right for controlled x=0.2/0.5/0.8 inputs. A face `sleep`/`idle` state event switched analysis to ≈4.9 FPS and restored ≈30 FPS active processing. AVFoundation kept capture reads at ≈30 FPS in sleep and reported `capture_fps_request_applied: false`. Mosquitto restart was followed by healthy status and resumed camera-event publishing. The native M2 window was not visually inspected, and the filesystem/privacy audit remains pending.

**Runtime signals/side effects:** `PERSON_LEFT` eventually causes bmo-face to enter sleep after its own configured five-minute timer; `face_position` heartbeat keeps look direction active; face-state updates change analysis rate; broker messages contain only documented JSON metadata. Check each side effect at both the MQTT subscriber and bmo-face API when relevant.

**Executable vs human-only:** MQTT observation, API reads, state injection, and restart behavior are executable with catalog commands. Granting macOS camera permission, presenting a person/motion, checking visual response, and confirming no physical recording are human-only.

### Negative and edge cases

- Camera permission denied, invalid device index, no camera, camera opens but returns no frames, and camera disconnect while running.
- No face at initial camera-ready, a face appearing just before the 10-second deadline, and a face returning just after `PERSON_LEFT`.
- Multiple faces and a change in which face is largest.
- x values at 0, 0.4, 0.6, and 1.0; jitter smaller than the configured delta; repeated heartbeat at the maximum rate.
- Motion score exactly at/around threshold, lighting flicker, brief motion shorter than debounce, motion during sleep, and no motion since startup.
- Face API unavailable, invalid API response, API/MQTT state race, camera starts asleep, and face transitions sleep/wake while frames are being read.
- Broker unavailable at startup, disconnect during detection, malformed state payload, and reconnect while face position is changing.
- Verify every negative case fails/reports status explicitly without publishing frames or reporting a failed camera as healthy.

## 6. Layer 3 — System and termination tests

Run this layer on the Playbox after Runtime checks pass. macOS does not run the systemd unit; the Mac stage can verify signal handling and camera release only.

| Procedure | Expected result | Mode |
| --- | --- | --- |
| Install and enable `bmo-camera.service` using the repository's existing systemd-service setup pattern | Service starts after boot with the configured camera and broker; no interactive session needed | Human-only on Playbox |
| Cold boot/reboot with camera attached | Camera opens; API is healthy; events begin after valid frames; initial face state is synchronized | Human-only on Playbox |
| Send SIGTERM during capture, face detection, and MQTT outage | Process exits cleanly, closes API/MQTT resources, releases `/dev/video*`, and creates no frame files | Automated fake-capture test plus human-only target check |
| Restart Mosquitto during capture | Capture continues; publisher reconnects and events resume; no duplicate presence transition is emitted solely because of reconnect | Integration test plus human-only target restart |
| Disconnect/reconnect Aukey camera | Status becomes unhealthy on failure; bounded recovery or systemd restart restores capture; absence timer is not falsely treated as normal presence | Human-only on Playbox |
| Run active and sleep processing for an extended period | `/status` reports reported capture FPS, successful read FPS, and processing FPS; record CPU and RSS using the approved local device procedure | Human-only; CPU/RSS are not exposed by this repository |
| Inspect filesystem, service logs, MQTT, and network boundary during operation | No frame/video files, frame-bearing log entries, MQTT image data, or remote vision traffic | Human-only privacy acceptance |

No browser UI is in scope. Use the catalog's `curl -s` API checks; browser-based camera viewing or frame streaming would violate the plan's privacy boundary.

## 7. Regression and exit

After any implementation change, rerun the existing catalog pytest command and repeat affected MQTT/API cases. M2 regressions to protect are:

- `PERSON_DETECTED` cancels/avoids the face sleep timer; `PERSON_LEFT` starts it only after the camera's 10-second absence rule.
- `face_position` values continue to drive M2 left/center/right mapping; heartbeat prevents the 500-ms look timeout while a face remains visible.
- Camera sleep-rate subscription does not interfere with normal face state publication or MQTT reconnect.
- Camera API/MQTT never includes frame data; shutdown does not leave the webcam locked.

M3 is ready for target sign-off only when AC-01 through AC-08 have passing automated or documented human results. Record MacBook development results separately from Aukey/Playbox results. Do not mark target acceptance complete based on MacBook camera behavior alone.
