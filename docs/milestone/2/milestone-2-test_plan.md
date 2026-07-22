# Milestone 2 — Face Engine Test Plan (TDD)

**Phase:** Implement (Test-first only)  
**Scope source:** `docs/milestone/2/milestone-2-plan.md`  
**Constraint:** This document defines tests only. No implementation steps.

---

## 1. Test Strategy

Use a TDD loop for each behavior:
1. Write failing test.
2. Implement minimal code to pass.
3. Refactor safely.

Test levels:
- **Unit tests:** pure state logic, timing logic, payload validation, scale math.
- **Component tests:** renderer + animation behaviors with deterministic clock.
- **Integration tests:** MQTT in/out contracts, API contract, shutdown/reconnect flow.
- **Manual acceptance checks:** visual checks and device-level constraints.

Primary objective: prove M2 acceptance criteria before feature completion.

---

## 2. Test Suite Structure

Proposed suite layout:

```text
services/bmo-face/tests/
├── unit/
│   ├── test_scale_helper.py
│   ├── test_state_machine_transitions.py
│   ├── test_state_priority.py
│   ├── test_sleep_timer.py
│   ├── test_event_coalescing.py
│   ├── test_tts_amplitude_contract.py
│   └── test_config_fps_policy.py
├── component/
│   ├── test_idle_blink_overlay.py
│   ├── test_look_direction_behavior.py
│   ├── test_emotion_state_timeouts.py
│   ├── test_alert_exit_behavior.py
│   └── test_speaking_fallback_8hz.py
├── integration/
│   ├── test_mqtt_subscribe_publish_contract.py
│   ├── test_mqtt_reconnect_behavior.py
│   ├── test_rest_api_contract.py
│   └── test_sigterm_graceful_shutdown.py
└── acceptance/
    └── manual-suite (in this file, section 6.1)
```

---

## 3. Test Environment & Tooling

- Python test runner: `pytest`
- Time control: deterministic monotonic clock fixture
- MQTT test broker: local Mosquitto test instance
- Headless rendering mode for CI/local test runs
- Device validation target: FPT Playbox S400 (Armbian)

Non-goals for automated tests:
- Perfect visual quality scoring
- Human-like animation style judgement

---

## 4. TDD Backlog by Plan Tasks

## 4.1 Foundation Tests (T0–T4)

### TP-001 Scale helper enforces resolution-agnostic geometry
- **Given:** Screen sizes `320x240` and `1920x1080`
- **When:** `scale(v)` is called for canonical values
- **Then:** Proportions are preserved and values are positive integers
- **Covers:** T3, T4, acceptance scale criterion

### TP-002 FPS policy loads target/fallback correctly
- **Given:** Config with `fps_target=30`, `fps_fallback=24`
- **When:** Config parser loads face settings
- **Then:** Values are present, valid, and fallback < target
- **Covers:** T0b, config section

### TP-003 Invalid FPS config is rejected explicitly
- **Given:** Missing/invalid fps values (e.g., 0, negative, fallback > target)
- **When:** Config is loaded
- **Then:** Service raises clear validation error
- **Covers:** robustness for T1/T2

---

## 4.2 Animation Core Tests (T5–T9)

### TP-010 Idle animation baseline behavior
- **Given:** State `IDLE`
- **When:** Frames progress with deterministic clock
- **Then:** Glow oscillates and pupil breathing oscillates within bounds
- **Covers:** T5

### TP-011 Blink overlay is independent and non-blocking
- **Given:** Any non-sleep state
- **When:** Blink timer reaches interval
- **Then:** Blink runs without replacing base state
- **Covers:** T6, T23, acceptance blink criterion

### TP-012 Boot sequence completes to IDLE
- **Given:** Initial `BOOT`
- **When:** Sequence timeline completes
- **Then:** State transitions to `IDLE` and readiness publish trigger is emitted
- **Covers:** T7, T25

### TP-013 Sleep/wake animation transitions
- **Given:** `IDLE -> SLEEP -> WAKE`
- **When:** Trigger events and timeouts occur
- **Then:** Dim/undim progression and terminal states are correct
- **Covers:** T8, T9

---

## 4.3 Reactive States Tests (T10–T18)

### TP-020 Look direction maps from face_position payload
- **Given:** `x` values left/center/right
- **When:** `bmo/camera/face_position` event arrives
- **Then:** Transitions to `LOOK_LEFT`, `IDLE`, `LOOK_RIGHT` correctly
- **Covers:** T10

### TP-021 Emotion state entry and timeout behavior
- **Given:** Emotion events (`happy`, `stressed`, `hot`, `worried`, `sad`)
- **When:** Enter state and timeout elapses
- **Then:** Returns to expected follow-up state
- **Covers:** T11–T15

### TP-022 Alert interrupt, exit rule, and notification display
- **Given:** Current state `IDLE` or `SPEAKING`; notification payload has `title` and `message`
- **When:** High-priority notification event arrives
- **Then:**
  - Enters `ALERT` immediately
  - `current_notification` is populated with title + message
  - Holds for **5s** (not 2s)
  - Exits to `IDLE` (or resumes `SPEAKING` if interrupted)
- **Covers:** T16, priority acceptance, notification display

### TP-023 Thinking state: pulsing dots behavior
- **Given:** State `THINKING`
- **When:** Clock advances
- **Then:**
  - Pupils scan horizontally (sine, 800ms cycle)
  - 3 staggered pulsing dots drawn below mouth (radius 3–5 px, 1.5 Hz, 200ms phase offset per dot)
- **Covers:** T17

### TP-025 LISTENING state entry and exit
- **Given:** Any non-SLEEPING state
- **When:** `bmo/voice/listening_start` event arrives
- **Then:**
  - State changes to `LISTENING`
  - `transient_deadline` set 10s in the future
  - After 10s of no follow-up, auto-expires to `IDLE`
- **Covers:** LISTENING state addition

### TP-024 Speaking mouth: amplitude-driven + fallback
- **Given:** With and without amplitude payload
- **When:** Speaking frames update
- **Then:** Uses envelope when valid; uses 8Hz fallback when absent
- **Covers:** T18, amplitude acceptance

---

## 4.4 State Machine Tests (T19–T23)

### TP-030 Transition table contract
- **Given:** Allowed events per source state
- **When:** Events are dispatched
- **Then:** Only valid transitions occur; invalid transitions are ignored safely
- **Covers:** T19, T20

### TP-031 Priority ladder enforcement
- **Given:** Concurrent low-priority + high-priority events
- **When:** Events arrive during THINKING/SPEAKING
- **Then:** Higher priority interrupts correctly; low-priority events are coalesced
- **Covers:** T21

### TP-034 set_state bypasses coalescing (priority 6)
- **Given:** Face in SPEAKING or THINKING state (priority 4–5, coalescing active)
- **When:** `bmo/face/set_state {"state":"happy"}` arrives
- **Then:** State changes immediately to happy (not deferred/coalesced)
- **Covers:** priority bypass bug fix

### TP-035 set_state SPEAKING has 15s safety timeout
- **Given:** `bmo/face/set_state {"state":"speaking"}` sent (no `bmo/ai/speaking_end` will follow)
- **When:** 15 seconds elapse
- **Then:** State auto-returns to `IDLE`; face is never permanently stuck
- **Covers:** set_state safety timeout

### TP-032 Sleep timer accuracy
- **Given:** `PERSON_LEFT` starts timer; `PERSON_DETECTED` cancels timer
- **When:** Time advances
- **Then:** Sleep occurs at exactly configured timeout and cancels correctly
- **Covers:** T22, sleep acceptance

### TP-033 Blink timer isolation
- **Given:** Frequent state changes
- **When:** Blink scheduler runs
- **Then:** Blink cadence is preserved and not starved
- **Covers:** T23

---

## 4.5 Integration Tests (T24–T28)

### TP-040 MQTT subscribe contract
- **Given:** Valid payloads on all subscribed topics
- **When:** Messages are consumed
- **Then:** Correct dispatch to state machine occurs per topic contract
- **Covers:** T24

### TP-041 MQTT publish contract
- **Given:** State transitions and boot completion
- **When:** Publisher emits events
- **Then:** `bmo/face/state` and `bmo/face/ready` payloads match schema
- **Covers:** T25

### TP-042 MQTT reconnect behavior
- **Given:** Broker disconnect/restart
- **When:** Connection drops then returns
- **Then:** Client reconnects within configured backoff policy and resumes processing
- **Covers:** T24, reconnect acceptance

### TP-043 REST API contract
- **Given:** Running service
- **When:** Call `GET /health`, `GET /state`, `POST /state`, `POST /brightness`
- **Then:** Response codes and payload contracts are correct; invalid input returns explicit errors
- **Covers:** T26, T27

### TP-044 SIGTERM graceful shutdown
- **Given:** Running renderer + API + MQTT
- **When:** Process receives SIGTERM
- **Then:** Clean shutdown sequence executes and exits within threshold
- **Covers:** T28

---

## 4.6 Ops & Device Tests (T29–T32)

### TP-050 systemd startup behavior
- **Given:** Enabled `bmo-face.service`
- **When:** Device boots
- **Then:** Service starts automatically and reaches healthy state
- **Covers:** T29, T30

### TP-051 End-to-end smoke behavior
- **Given:** Live service on device
- **When:** Publish representative MQTT events
- **Then:** Visible state changes and API health stay correct
- **Covers:** T31

### TP-052 Memory stability profile
- **Given:** 1h steady run
- **When:** Collect RSS over time
- **Then:** Steady-state remains within baseline +20% (soft target ≤120MB)
- **Covers:** T32

---

## 5. MQTT Payload Schemas Under Test

### Subscribed topics
- `bmo/camera/person_detected` → `{}`
- `bmo/camera/person_left` → `{}`
- `bmo/camera/face_position` → `{"x": 0.0..1.0}`
- `bmo/voice/wake_word` → `{}`
- `bmo/voice/listening_start` → `{}`
- `bmo/ai/speaking_start` → `{"amplitude":[0.0..1.0], "sample_rate_hz": 10}`
- `bmo/ai/speaking_end` → `{}`
- `bmo/system/state` → `{"emotion":"happy|stressed|hot|worried"}`
- `bmo/ai/proactive_start` → `{}`
- `bmo/notify/event` → `{"title":"...","message":"...","priority":"low|medium|high"}`
- `bmo/voice/bt_disconnect` → `{}`
- `bmo/face/set_state` → `{"state":"<state_name>"}`

### Published topics
- `bmo/face/state` → `{"state":"<state_name>"}`
- `bmo/face/ready` → `{}`

---

## 6. Manual Test Suite (Device + Visual)

Run on target hardware (FPT Playbox S400) after automated tests pass.

### 6.1 Manual checklist

- [ ] Service starts from cold boot and reaches `idle` face automatically.
- [ ] Face renders fullscreen on dev monitor; no clipping.
- [ ] Face renders correctly on 3.2" LCD with similar proportions.
- [ ] IDLE glow outline + breathing pupils are visibly active.
- [ ] Blink appears every ~3–6 seconds and does not interrupt base state.
- [ ] Publish `bmo/camera/face_position x=0.2` → face looks left.
- [ ] Publish `bmo/camera/face_position x=0.8` → face looks right.
- [ ] Publish `bmo/camera/person_left`, wait timeout → enters sleep (dim + Z's).
- [ ] Publish `bmo/camera/person_detected` from sleep → wake then idle.
- [ ] Publish `bmo/system/state {"emotion":"happy"}` → **smile `:)`** + squinted eyes.
- [ ] Publish `bmo/system/state {"emotion":"stressed"}` → **X eyes** + zigzag mouth + angry brows.
- [ ] Publish `bmo/system/state {"emotion":"hot"}` → red tint + sweat drops.
- [ ] Publish `bmo/system/state {"emotion":"worried"}` → `/\` brows + darting eyes.
- [ ] Publish `bmo/voice/bt_disconnect` → sad frown `:(` + blue tint.
- [ ] Publish `bmo/voice/listening_start` → **wide eyes** + glow outline active.
- [ ] Publish `bmo/face/set_state {"state":"thinking"}` → **scanning pupils + pulsing 3 dots**.
- [ ] Publish `bmo/face/set_state {"state":"speaking"}` → **animated oval mouth** oscillating.
- [ ] While in `speaking`, publish another `set_state {"state":"happy"}` → state changes immediately (no coalescing block).
- [ ] Publish `bmo/notify/event {"priority":"high","title":"Door","message":"Someone at front door"}` → ALERT with flashing border + **title in yellow + message in grey** in text box at bottom.
- [ ] Publish same notify while in `speaking` → alert then resumes speaking.
- [ ] `GET /health` returns 200.
- [ ] `POST /state` with invalid state returns 400.
- [ ] Restart Mosquitto → bmo-face reconnects and keeps reacting to events.
- [ ] Send SIGTERM → process exits cleanly (no hung display process).
- [ ] Observe memory for 1h → steady-state remains within baseline +20%.

### 6.2 Manual command snippets

- MQTT publish: `mosquitto_pub -t <topic> -m '<json>'`
- Health check: `curl -s http://127.0.0.1:5200/health`
- State check: `curl -s http://127.0.0.1:5200/state`

---

## 7. Entry / Exit Criteria

## Entry Criteria
- Plan and spec are aligned for M2.
- MQTT topic contracts frozen for M2.
- Test harness (pytest + fixtures) available.

## Exit Criteria
- All critical automated tests (TP-001, 010, 011, 012, 022, 031, 032, 040, 041, 043, 044) pass.
- No failing tests in unit/component/integration suite.
- Manual checklist section 6.1 is executed and signed on target hardware.

---

## 8. Risk-Driven Test Priorities

Priority P0 (must pass first):
- TP-030/031/032 (state correctness)
- TP-040/041 (MQTT contract)
- TP-043 (API health/control)
- TP-044 (shutdown safety)

Priority P1:
- TP-010/011/012/013/024 (animation core behavior)
- TP-052 (memory stability)

Priority P2:
- Visual polish checks and optional behavior boundaries

---

## 9. Traceability Matrix (Plan Task → Test Cases)

| Plan Tasks | Test Cases |
| --- | --- |
| T0–T4 | TP-001, TP-002, TP-003 |
| T5–T9 | TP-010, TP-011, TP-012, TP-013 |
| T10–T18 | TP-020, TP-021, TP-022, TP-023, TP-024 |
| T19–T23 | TP-030, TP-031, TP-032, TP-033 |
| T24–T28 | TP-040, TP-041, TP-042, TP-043, TP-044 |
| T29–T32 | TP-050, TP-051, TP-052 |

---

## 10. Out of Scope (for M2 test plan)

- Voice recognition quality benchmarking (belongs to M5).
- LLM response quality tests (belongs to M6).
- Home Assistant integration behavior tests (belongs to M8).
- Hardware fan / LED behavior tests (belongs to M9).
