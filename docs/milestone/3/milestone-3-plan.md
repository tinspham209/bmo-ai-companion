# Milestone 3 — Camera Service Plan

**Status:** Software implementation is complete; MacBook runtime acceptance is partially verified; macOS processed-FPS checks pass, but AVFoundation did not reduce native capture FPS in sleep; Playbox/Aukey acceptance remains pending
**Priority:** Next after M2 software implementation; M2 Playbox acceptance can remain a parallel verification gate
**Reference:** `docs/2026-07-22-01-bmo-ai-companion-specs.md` § Milestone 3
**Test plan:** `docs/milestone/3/test-plan.md`
**Validation order:** Develop and test first with the MacBook's built-in camera; validate the Aukey webcam later on the FPT Playbox.
**Local verification (2026-09-29):** 51 camera-service tests pass. After granting macOS camera permission, OpenCV opened the built-in camera at 1920×1080; `/health` returned 200; live presence, position, motion, and no-motion MQTT events were observed. With the checked-in `active_fps: 30`, active capture reads were about 30 FPS and analysis about 27–30 FPS. In sleep, analysis was about 4.9 FPS, but AVFoundation accepted the FPS request without applying it: reported/read capture stayed about 30 FPS and `/status` showed `capture_fps_request_applied: false`. `idle` restored active analysis. A Mosquitto restart was followed by healthy camera status and resumed `face_position` publications. Native M2 window visual confirmation, privacy audit, and Playbox/Aukey checks remain pending.

## Goal

Build an independent, on-device camera service for the FPT Playbox S400 that detects face presence and position, detects motion, and publishes camera events over the existing Mosquitto MQTT broker. Camera frames must remain in memory on the device and must never be uploaded, saved, or included in logs.

## Target and constraints

| Item | Target |
| --- | --- |
| Device | FPT Playbox S400, Amlogic S905X, Armbian |
| Development camera | MacBook built-in camera using the native macOS capture backend |
| Target camera | Aukey webcam on the Playbox; hardware is reported working (the specs call it PC-3 FullHD; the user refers to WC-3; confirm exact model/revision later) |
| Runtime | Python 3.11+ and OpenCV |
| Communication | MQTT on the shared local Mosquitto broker |
| Orchestration | Independent `systemd` service |
| Active camera mode | Capture at the camera's native active mode; measure read and analysis rates separately |
| Active analysis rate | Process the newest available frame as quickly as the detector permits; measure actual rate |
| Sleep analysis rate | 5 processed frames/second while `bmo-face` reports `sleep` |
| Privacy | 100% local processing; no frame persistence or remote vision calls |

## Scope

- Open and monitor the configured camera device.
- Detect whether at least one face is present, and publish presence transitions.
- Publish normalized horizontal face position for the largest detected face.
- Detect motion and publish `MOTION` / `NO_MOTION` transitions.
- Keep reading frames in active mode with a single latest-frame buffer; cap analysis to 5 FPS while the face service is asleep.
- Expose a small localhost health/status API without exposing frames.
- Run independently under systemd, recover from broker interruptions, and release the camera cleanly on shutdown.

### Out of scope

- Face identity, recognition, age, or emotion inference.
- Recording, storing, streaming, or uploading images or video.
- Cloud vision services.
- Camera controls or UI beyond local health/status.

## Service layout

```text
services/bmo-camera/
├── main.py                 # Service entry point and lifecycle
├── camera.py               # Capture lifecycle and frame-rate policy
├── detector.py             # Face and motion detection
├── state.py                # Presence/motion transitions and timers
├── mqtt_client.py          # MQTT subscriptions, publishing, reconnect
├── api.py                  # Local /health and /status endpoints
├── config.py               # camera section from config/bmo.yaml
├── requirements.txt
├── README.md
├── systemd/
│   └── bmo-camera.service
└── tests/
    ├── unit/
    ├── component/
    └── integration/
```

Use `opencv-python-headless` rather than the GUI-enabled OpenCV distribution because this service does not display frames. Keep capture, detection, MQTT, and state/timer logic separable so frame processing can be tested with synthetic images and a fake camera.

Deployment files follow existing repository conventions: `scripts/install-camera.sh` at the repository root and `services/bmo-camera/systemd/bmo-camera.service` for the Linux target. Do not install a systemd unit on macOS.

## Runtime flow

1. Load and validate the `camera` section in `config/bmo.yaml`.
2. Open the selected camera backend/device and check that frames can be read. On macOS, use the MacBook's built-in camera and grant the required OS camera permission. Fail visibly if the camera cannot be opened; do not report a healthy status with no working camera.
3. Negotiate the camera's supported capture resolution, then resize analysis frames while preserving aspect ratio. Perform face and motion detection locally and keep frames only in memory.
4. Publish events only on state transitions or meaningful position changes; do not publish one presence/motion event per frame.
5. Synchronize initial face state from `bmo-face`'s `GET /state` endpoint, then apply subsequent `bmo/face/state` MQTT events. Capture in the camera's native mode and process the newest frame as quickly as possible in active mode. In sleep, cap analysis to 5 FPS. Return to active analysis on any non-sleep state. If the face API is unavailable, log the failure and start in active mode. Request an explicit camera FPS only when `active_fps` is configured numerically; `auto` must not infer a cap from unreliable backend FPS metadata.
6. On shutdown, stop frame processing, release `VideoCapture`, stop the MQTT loop, and stop the API server.

## MQTT contract

### Subscribed topic

| Topic | Payload | Behavior |
| --- | --- | --- |
| `bmo/face/state` | `{"state":"<state_name>"}` | Switch to 5 FPS on `sleep`; restore active processing for other states |

Subscribe before requesting the current face state. Since `bmo/face/state` is transition-published and not retained, fetch `GET /state` after subscribing and apply queued MQTT updates after that response so a concurrent transition is not overwritten. Use a short timeout; if the face API is unavailable, log it and start in active mode.

### Published topics

| Topic | Payload | Trigger |
| --- | --- | --- |
| `bmo/camera/person_detected` | `{}` | First successful face detection after an absent period; emit once per presence transition |
| `bmo/camera/person_left` | `{}` | No face detected continuously for 10 seconds; emit once per absent period |
| `bmo/camera/face_position` | `{"x": 0.0..1.0}` | A meaningful change in the largest detected face center or a position heartbeat while a face remains visible |
| `bmo/camera/motion` | `{}` | Motion score crosses the configured threshold into the moving state |
| `bmo/camera/no_motion` | `{}` | No motion for the configured interval since startup or last motion; emit once per quiet period |

Start in an `unknown` presence state after the first valid frame. If no face is detected for 10 seconds from camera-ready, publish one `person_left`; subsequent events occur only on presence transitions. Use a monotonic clock for the 10-second absence timer and motion/no-motion timers. Continue to detect absence while processing at the reduced sleep rate; the presence timeout remains 10 seconds regardless of FPS.

Motion scores are internal to detection/state logic; keep `MOTION` and `NO_MOTION` payloads empty in v1 because the M3 spec defines event names but no payload contract. Expose current motion state through `/status` if useful; do not add a frame stream or a separate telemetry topic.

For `face_position`, publish the horizontal center of the largest face. The M2 face service auto-centers after 500 ms without a position event, so publish a heartbeat at least every 400 ms while a face remains visible. Also publish sooner when the position changes meaningfully, subject to a 5-Hz maximum. This keeps the face looking toward a stationary person without flooding MQTT. The M2 face service maps `x < 0.4` to left, `x > 0.6` to right, and the center band to idle.

## Configuration

Add a `camera` section to the existing `config/bmo.yaml`; do not introduce a second general-purpose configuration file.

```yaml
camera:
  backend: auto
  device_index: 0
  active_fps: 30 # Initial target; tune to the device's supported full active mode
  sleep_fps: 5
  analysis_width: 320
  face_absent_seconds: 10
  face_position_max_hz: 5
  face_position_min_delta: 0.05
  face_position_heartbeat_seconds: 0.4
  motion_threshold_ratio: 0.02
  no_motion_timeout_seconds: 30
  face_state_url: http://127.0.0.1:5200/state
  face_state_timeout_seconds: 1
  api_port: 5201
  mqtt_broker: localhost
  mqtt_port: 1883
```

Values other than the 10-second face-absence rule and 5-FPS sleep mode are proposed starting defaults, not measured S905X values. Make them validated and configurable; tune analysis width, motion threshold, and no-motion timeout during device acceptance. Keep the API port distinct from `bmo-face`'s port 5200.

Use backend auto-selection (`AVFoundation` on macOS, the platform's Linux backend on Armbian) unless device testing demonstrates that an explicit backend is needed. Camera index 0 is only a starting value; allow it to be changed without code edits.

`active_fps: 30` is the initial request for the MacBook and FullHD Aukey, not a guaranteed supported rate. Set it to the measured active mode for the target. `active_fps: auto` preserves native capture mode; in that mode sleep guarantees 5-FPS analysis but cannot guarantee the sensor itself downshifts. Verify the camera backend actually applies both active and sleep requests; OpenCV may report success without changing the stream.

## Reverse-spec review

### Gaps found

- The spec names `MOTION` / `NO_MOTION` and says “N seconds” but does not define the no-motion interval, motion score, or threshold.
- The spec lists event names but only implies the `face_position` schema through M2. This plan now uses `{}` for presence/motion transition events and `{"x": 0.0..1.0}` for face position; the internal motion score is not an MQTT contract.
- Startup behavior was unspecified. This plan starts presence as `unknown` and emits one `PERSON_LEFT` after 10 seconds of valid camera frames with no face. Camera-open failure must not be mistaken for an empty room.
- M2 returns `LOOK_LEFT` / `LOOK_RIGHT` to center 500 ms after the last position event. A change-only camera publisher would let a stationary face expire back to idle; the 400-ms position heartbeat closes this integration gap.
- “Full frame rate” does not state a number or distinguish camera capture FPS from analysis FPS. The plan leaves active capture in native mode by default, measures capture reads and analysis separately, and throttles analysis to 5 FPS in sleep. Any target-hardware shortfall must be recorded as a deviation rather than silently redefining “full rate.”
- The spec has no detector accuracy/lighting target or camera-specific CPU/RSS budget. Stage B must record these results and agree any pass threshold before declaring M3 complete.
- Hardware inventory calls the target camera “Aukey PC-3 FullHD”; the user refers to it as “Aukey WC-3.” Confirm the exact model/revision when connecting it to the Playbox.

### Assumptions to validate

- **MacBook first:** use the native macOS capture backend (normally AVFoundation), grant camera permission to the terminal/Python host, and make device index/backend configurable.
- **Playbox later:** test the Aukey camera using the Linux OpenCV backend after the MacBook path works.
- Treat any face as presence and use the largest detected face for `face_position`; do not identify people.
- Start with OpenCV's bundled Haar cascade and a downscaled, aspect-preserving analysis frame. Keep the detector replaceable, but do not add another model/runtime unless Mac or Playbox tests show Haar cannot meet needs.
- Initial tuning proposals are `active_fps: 30`, `no_motion_timeout_seconds: 30`, `motion_threshold_ratio: 0.02`, minimum position delta `0.05`, maximum position rate `5 Hz`, and a `0.4`-second position heartbeat. These are configurable proposals, not requirements from the spec.
- Synchronize the initial sleep/active policy from M2's localhost `/state` API because its MQTT state topic is not retained; use active mode if the face API is temporarily unavailable.
- A numeric `active_fps` lets a backend that supports FPS changes switch capture to 5 FPS during sleep and restore the explicit active value on wake. With `auto`, capture stays native and the analysis loop is capped at 5 FPS.
- Use the minimal event payloads in the contract above until another service demonstrates a need for extra fields.

### Over-engineering removed or constrained

- No camera dashboard, remote camera API, WebSocket stream, snapshots, recordings, cloud vision, identity recognition, or multi-camera orchestration.
- Keep the API to architecture-required localhost `/health` and `/status`; it must never return frames.
- Do not publish per-frame motion scores or add a new telemetry topic. Publish transition events only.
- Do not create a detector plugin framework; use one small detector interface so a measured replacement remains possible.
- Keep broker reconnect and camera recovery bounded to the existing service lifecycle; do not add a separate queue/broker or a complex supervisor.

## Revised implementation plan

### Phase 1 — MacBook-first capture foundation

- [x] **T0** Verify the MacBook's built-in camera is accessible through OpenCV with OS camera permission; record selected backend, device index, negotiated resolution, and actual capture rate. (AVFoundation, device 0, 1920×1080, approximately 30 capture reads/sec after permission was granted.)
- [x] **T1** Create the service skeleton, `opencv-python-headless` dependencies, configurable backend/device selection, validated camera config, and localhost API port.
- [x] **T2** Implement an injectable capture wrapper with explicit open/read/release behavior; fail visibly on camera-open failure and never interpret it as `PERSON_LEFT`.
- [x] **T3** Add deterministic fake-capture and synthetic-frame fixtures; verify aspect-preserving analysis resize and that frames are not written to disk.

### Phase 2 — Detection and event semantics

- [x] **T4** Implement one OpenCV Haar face detector using downscaled grayscale frames and configurable minimum face size.
- [x] **T5** Implement `unknown` / `present` / `absent` transitions. After the first valid frame, publish one `PERSON_LEFT` after 10 seconds with no face; publish `PERSON_DETECTED` on first detection and cancel/reset the absence timer.
- [x] **T6** Publish largest-face center as normalized `x`; emit meaningful changes plus a heartbeat at least every 400 ms while a face remains visible, capped at 5 Hz.
- [x] **T7** Implement internal motion scoring and thresholding. Publish one `MOTION` on entering the moving state and one `NO_MOTION` after the configurable quiet interval, including the initial quiet interval after camera startup.

### Phase 3 — MQTT and frame-rate policy

- [x] **T8** Subscribe to `bmo/face/state`, initialize from M2 `GET /state`, and apply queued MQTT updates after the response; process at active rate except for `sleep`, where analysis is capped at 5 FPS.
- [x] **T9** Implement the MQTT topics/payloads defined above, validate incoming face-state messages, and configure bounded reconnect backoff. Camera analysis continues during broker outages; publishing resumes after reconnect.
- [x] **T10** Capture on a dedicated thread with a bounded single-frame latest-value handoff; report backend FPS, successful capture-read FPS, and processed FPS separately. Keep native capture in `auto`, and enforce the 5-FPS sleep analysis limit.

### Phase 4 — Service lifecycle and deployment

- [x] **T11** Implement localhost `GET /health` and `GET /status` with camera-open state, reported/read/processed FPS, presence/motion state, and last-event times only.
- [x] **T12** Recover from transient read failures with a bounded camera reopen attempt; report unhealthy status and surface errors if recovery fails. Add SIGTERM cleanup for capture, MQTT, and API.
- [x] **T13** Add repository-level `scripts/install-camera.sh`, Linux `systemd/bmo-camera.service`, macOS and Playbox run instructions, and camera permission/troubleshooting guidance.

### Phase 5 — Staged acceptance

- [ ] **T14** Complete the MacBook development checklist below before target-camera validation.
- [ ] **T15** On the Playbox, connect the Aukey camera, confirm its exact model/backend, tune detection and thresholds, then complete the target-device checklist.

## Test plan

### Unit tests

- Config parsing, invalid ranges, and explicit errors.
- Presence startup state and exact 10-second absence timing with a fake monotonic clock.
- Face-center normalization, movement threshold, heartbeat, and 5-Hz rate limit.
- Motion/no-motion transition timing, including initial quiet interval, debounce, and threshold noise.
- Active/sleep processed-FPS policy independent of the backend's requested capture FPS.
- MQTT face-state payload validation and event schemas.

### Component tests

- Synthetic frames with no face, one face, and multiple faces; largest-face selection and normalized position.
- Synthetic motion/no-motion sequences with threshold noise.
- Read failure/recovery and release on shutdown.
- Assert that no frame is written, published, or returned from the status API.

### Integration tests

- MQTT `bmo/face/state` changes processing policy; leaving sleep restores active processing.
- Published topics and payload shapes match the contract above.
- Broker disconnect/reconnect resumes event publishing without restarting capture.
- `/health` and `/status` reflect camera failure and contain no frame data.
- SIGTERM closes the API/MQTT client and releases the camera handle.

All automated tests must run without a physical camera or broker by using fakes/synthetic frames. Run live-camera acceptance first with the MacBook camera, then repeat hardware-specific checks with the Aukey on the Playbox.

## Acceptance criteria and traceability

| ID | Acceptance criterion | Covered by |
| --- | --- | --- |
| AC-01 | Valid face causes one `PERSON_DETECTED`; no-face for 10 seconds causes one `PERSON_LEFT`; detection resets the absence timer | T5, presence unit tests, both staged checklists |
| AC-02 | `face_position` is normalized, follows the largest face, and heartbeats keep M2's look state active without flooding MQTT | T6, position unit/component tests, Mac end-to-end check |
| AC-03 | Motion threshold creates one `MOTION`; configured quiet period creates one `NO_MOTION` | T7, synthetic motion tests, Mac and Playbox checks |
| AC-04 | Request 5-FPS camera mode in face `sleep`, enforce 5-FPS analysis, and restore active mode after wake | T8/T10, rate-policy tests, both camera acceptance stages; backend capture-mode support must be verified |
| AC-05 | Face/motion processing remains on-device; no frames are stored, logged, published, or returned | T2/T11, privacy tests, both staged checklists |
| AC-06 | MQTT events and reconnect behavior match the shared local broker contract | T9, MQTT integration tests, Playbox broker-restart check |
| AC-07 | Service health, camera failure, and shutdown are explicit and resources are released | T11/T12, lifecycle tests, Playbox systemd/SIGTERM checks |
| AC-08 | Active/sleep rates and resource use are measured on the target hardware | T10/T15, Playbox performance checklist |

### Stage A — MacBook built-in camera (do now)

- [x] Grant camera permission to the terminal/Python process; confirm OpenCV opens the built-in camera and reports its negotiated resolution (AVFoundation, 1920×1080).
- [x] Record capture/processing rates: active capture reads were about 30 FPS and analysis about 27 FPS; sleep analysis was about 4.9 FPS against a 5-FPS target.
- [x] Start the camera and face services locally; verify `/health` returns 200 and `/status` reports metadata only.
- [x] Observe live presence changing to present and later absent; `/status` reported `person_left` after more than 10 seconds without a face. Fake-clock tests verify exact timeout and cancellation.
- [x] Capture `PERSON_DETECTED` / `PERSON_LEFT` on MQTT, including re-detection after an absent period; fake-clock tests verify one event per transition and exact timeout cancellation.
- [x] Observe live normalized `face_position` MQTT payloads across left/center/right (including x≈0.27, 0.50, 0.79); controlled x=0.2/0.5/0.8 events produced M2 API states `look_left`/`idle`/`look_right`. Visible window response and stationary look hold remain human-only.
- [x] Create movement, then keep the scene quiet; MQTT subscribers captured `MOTION` and `NO_MOTION` after the configured quiet interval.
- [x] Publish face sleep/wake states; verify analysis rate drops to about 4.9 FPS and returns to active. AVFoundation did not apply the sleep capture request: capture reads stayed around 30 FPS, and `/status` reported `capture_fps_request_applied: false`.
- [x] Restart the local Mosquitto service while camera and face services run; capture remained healthy and camera event publishing resumed.
- [ ] Verify a camera backend can actually reduce capture reads to 5 FPS in sleep; the MacBook backend did not apply this request.
- [x] Stop the camera service with SIGTERM; it exited and the camera reopened successfully on the next run.
- [x] Source/tests contain no frame persistence or image-bearing MQTT/API path; runtime API and MQTT carried metadata only.
- [ ] Inspect filesystem/logs/network during an extended runtime check; confirm no image/video artifacts or frame data cross process boundaries.

### Stage B — Aukey camera on FPT Playbox (later)

- [ ] Confirm the exact Aukey model/revision, Linux camera device, permissions, and supported capture modes.
- [ ] Repeat the Stage A event checks against the Aukey and verify the M2 face on the Playbox display.
- [ ] Verify 10-second absence, position heartbeat, motion threshold, and 5-FPS sleep behavior under actual S905X load.
- [ ] Configure the measured active FPS explicitly; confirm `/status.capture_fps_request_applied` and `capture_read_fps` show the backend actually switches to 5 FPS in sleep and restores active rate on wake.
- [ ] Measure actual capture/processing FPS, CPU, and RSS in active/sleep modes; record results and tune configurable values.
- [ ] Verify broker restart, camera unplug/recovery, systemd cold-boot start, SIGTERM cleanup, and extended-run stability.
- [ ] Confirm privacy: no frame files, frame-bearing logs, MQTT image payloads, or network destinations other than configured local services.

## Remaining assumptions to resolve

| Decision | Current proposal | Resolution gate |
| --- | --- | --- |
| Target camera identity | Docs list Aukey PC-3 FullHD; user refers to Aukey WC-3 | Confirm model/revision during Stage B |
| `NO_MOTION` interval | 30 seconds, configurable; first interval starts after first valid frame | Confirm through Stage A; tune in Stage B if needed |
| Motion threshold | 2% changed analysis pixels, configurable | Tune under MacBook lighting, then recalibrate on target |
| Detector | Bundled Haar cascade | Keep only if face detection is adequate and target CPU/FPS is acceptable |
| Camera index/backend | Auto backend, index 0 as initial candidate | Discover/confirm separately on MacBook and Playbox |
| FPS behavior | Request the measured full active mode (initial proposal 30 FPS) / 5-FPS sleep mode | Record actual capture and processing rates in Stage A and Stage B; document any backend limitation or deviation |
| Accuracy/resource exit thresholds | Not specified | Record false/missed detections, CPU, RSS, and sustained FPS on the Playbox; agree pass thresholds before M3 sign-off |
