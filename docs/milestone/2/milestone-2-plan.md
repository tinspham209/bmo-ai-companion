# Milestone 2 — Face Engine Plan

**Status:** In progress — software implementation is ready for target validation; device checks are pending
**Priority:** 1 (first to implement)
**Ref spec:** `docs/2026-07-22-01-bmo-ai-companion-specs.md § Milestone 2`
**macOS verification (2026-09-28):** install script completed; Homebrew Mosquitto is running on loopback and pub/sub passed; local headless service health and MQTT state control passed; 39 automated tests passed. Playbox/display acceptance, target-broker restart, and one-hour device memory profiling remain pending.

---

## Goal

Boot directly into a living, animated BMO face fullscreen and resolution-agnostic — target 30 FPS, fallback 24 FPS on constrained hardware — driven by a state machine that reacts to MQTT events from other services.

---

## Deliverable

A standalone `bmo-face` service that:
- Renders BMO's face procedurally in pygame-ce
- Runs the full animation state machine
- Subscribes to MQTT for state-change events
- Exposes a REST API for direct state queries/overrides
- Runs as a systemd unit, auto-starts on boot

---

## File Structure

```
services/bmo-face/
├── main.py               # Entry point
├── renderer.py           # pygame-ce draw loop (target 30 FPS, fallback 24)
├── face/
│   ├── __init__.py
│   ├── colors.py         # Palette constants
│   ├── components.py     # Eyes, mouth, screen draw functions
│   ├── animations.py     # Per-state animation logic
│   └── state_machine.py  # State definitions + transitions
├── mqtt_client.py        # MQTT subscriber → push events to state machine
├── api.py                # REST API (Flask/FastAPI) for overrides
├── config.py             # Load from config/bmo.yaml
└── requirements.txt
```

---

## Color Palette

| Token             | Hex       | Usage                   |
| ----------------- | --------- | ----------------------- |
| `COLOR_BODY`      | `#78C8C8` | BMO body / border       |
| `COLOR_SCREEN_BG` | `#1a1a2e` | Screen background       |
| `COLOR_EYE`       | `#FFFFFF` | Eye whites              |
| `COLOR_EYE_PUPIL` | `#00FF88` | Pupil / iris            |
| `COLOR_MOUTH`     | `#00FF88` | Mouth line              |
| `COLOR_GLOW`      | `#78C8C8` | Idle glow pulse         |
| `COLOR_DIM`       | `#0D0D1A` | Sleep dim overlay       |
| `COLOR_HOT_TINT`  | `#FF4422` | Hot state red overlay   |
| `COLOR_ALERT`     | `#FFDD00` | Alert exclamation flash |
| `COLOR_SAD_TINT`  | `#4488CC` | Sad state blue tint     |

---

## Scale Helper Contract

All geometry **must** use the `scale()` helper — no hardcoded pixel values anywhere in `face/`:

```python
# Computed once at startup in renderer.py
SCALE = min(screen_w, screen_h) / 240  # baseline: 3.2" LCD short-side = 240px

def scale(v: float) -> int:
    return max(1, int(v * SCALE))
```

**Rule:** Every size, position, radius, and offset in `face/` passes through `scale()`.
**Test:** Render at `320×240` and `1920×1080` — all proportions must match visually (no clipping, no misalignment).

---

## State Machine

### States

```
BOOT → IDLE ←→ BLINK (overlay, independent)
             ←→ LOOK_LEFT / LOOK_RIGHT
             ←→ HAPPY / SAD
             ←→ STRESSED / HOT / WORRIED
             ←→ THINKING
             ←→ LISTENING  (wake-word heard, waiting for STT result)
             ←→ SPEAKING
             ←→ ALERT  (priority 6 — interrupts all ≤ SPEAKING)
             ←→ SLEEP ←→ WAKE (returns to IDLE)
```

### Transition Table

| From                       | Event (MQTT topic)               | To                                   |
| -------------------------- | -------------------------------- | ------------------------------------ |
| `BOOT`                     | startup complete                 | `IDLE`                               |
| `IDLE`                     | `bmo/camera/person_left` (5 min) | `SLEEP`                              |
| `SLEEP`                    | `bmo/camera/person_detected`     | `WAKE`                               |
| `WAKE`                     | animation done                   | `IDLE`                               |
| `IDLE`                     | `bmo/camera/face_position`       | `LOOK_LEFT` / `LOOK_RIGHT`           |
| `IDLE`                     | `bmo/voice/wake_word`            | `THINKING`                           |
| `IDLE`                     | `bmo/voice/listening_start`      | `LISTENING` (10s timeout → IDLE)     |
| `THINKING`                 | `bmo/ai/speaking_start`          | `SPEAKING`                           |
| `SPEAKING`                 | `bmo/ai/speaking_end`            | `IDLE`                               |
| `IDLE`                     | `bmo/system/state` → happy       | `HAPPY`                              |
| `HAPPY`                    | timeout (3s)                     | `IDLE`                               |
| `IDLE`                     | `bmo/system/state` → stressed    | `STRESSED`                           |
| `IDLE`                     | `bmo/system/state` → hot         | `HOT`                                |
| `IDLE`                     | `bmo/system/state` → worried     | `WORRIED`                            |
| `STRESSED`/`HOT`/`WORRIED` | timeout (5s)                     | `IDLE`                               |
| `IDLE`                     | `bmo/voice/bt_disconnect`        | `SAD`                                |
| `SAD`                      | timeout (4s)                     | `IDLE`                               |
| `IDLE`                     | `bmo/ai/proactive_start`         | `THINKING`                           |
| any (priority ≤ 5)         | `bmo/notify/event` priority=high | `ALERT`                              |
| `ALERT`                    | timeout (5s)                     | `IDLE` (or `SPEAKING` if interrupted) |
| any                        | `bmo/face/set_state`             | target state (priority 6 — always wins, invalid names ignored) |

> **`set_state` safety timeouts:** SPEAKING→15s, THINKING/LISTENING→10s, emotions/WAKE→5s, IDLE/SLEEP→none

### Blink sub-state
- Runs **independently** as an overlay on top of any non-SLEEP state
- Random interval: 3–6 seconds
- Duration: 200ms (75ms close, 50ms hold, 75ms open)

### State Priority Ladder

Higher priority states interrupt lower ones. During SPEAKING/THINKING/LISTENING, lower-priority events are **coalesced** (keep the latest event per topic) to avoid backlog. ALERT holds priority over lower-priority events; `bmo/face/set_state` bypasses coalescing.

| Priority    | States                                                                  | Rule                                   |
| ----------- | ----------------------------------------------------------------------- | -------------------------------------- |
| 6 — Highest | `ALERT`, `bmo/face/set_state`                                           | Interrupts all states; set_state always bypasses coalescing |
| 5           | `SPEAKING`                                                              | Not interrupted by emotion/look states |
| 4           | `THINKING`, `LISTENING`                                                 | Not interrupted by emotion/look states |
| 3           | `HAPPY`, `SAD`, `STRESSED`, `HOT`, `WORRIED`, `LOOK_LEFT`, `LOOK_RIGHT` | Peer-level; last-in wins               |
| 2           | `IDLE`, `WAKE`                                                          | Base states                            |
| 1 — Lowest  | `SLEEP`                                                                 | Only exits via `PERSON_DETECTED`       |

---

## Animation Specs

### `BOOT` — Startup Sequence
1. Screen black (0.3s)
2. Single flicker (white flash 50ms, black 50ms) × 2
3. Eyes draw from center outward (0.5s ease-out)
4. Mouth fades in (0.3s)
5. Transition to `IDLE`

### `IDLE`
- Screen glow pulses: alpha oscillates ±15% over 3s cycle (sine wave)
- Eyes at center, pupils softly "breathe" (scale ±5%)
- Blink overlay active

### `BLINK`
- Upper eyelid sweeps down over 75ms, holds 50ms, sweeps up 75ms
- Pupil slightly squishes vertically during blink

### `LOOK_LEFT` / `LOOK_RIGHT`
- Pupils translate ±20% of eye width over 200ms (ease-in-out)
- Hold while `face_position` event is active
- Return to center 500ms after last event

### `SLEEP`
- Dim overlay fades in over 2s (alpha 0 → 180)
- Eyes half-close (top lid drops 50%)
- Glow pulse slows to 8s cycle
- Screen brightness: 30% of normal

### `WAKE`
- Dim overlay fades out over 1s
- Eyes open fully (ease-out spring)
- Short upward "pop" bounce on pupils
- Transition to `IDLE`

### `HAPPY`
- Eyes squint (height ×0.35)
- Mouth arc curves **upward** (π → 2π in pygame y-down = bottom arc = smile `:)`)
- Hold 3s → `IDLE`

### `THINKING`
- Pupils scan horizontally (sine, 800ms cycle)
- 3 pulsing staggered dots animate below mouth (radius 3–5 px, 1.5 Hz each, 200ms phase stagger)
- Hold until `bmo/ai/speaking_start` or `set_state`

### `LISTENING`  _(new in M2)_
- Eyes open wider (height ×1.45)
- Small open oval mouth
- Glow outline visible (same as IDLE pulse)
- Triggered by `bmo/voice/listening_start`; auto-expires after 10s → `IDLE`

### `SPEAKING`
- Mouth animates as oval using the supplied amplitude envelope when valid
- Falls back to 8 Hz oscillation when the envelope is absent or empty
- Eyes stay in current position
- Exits via `bmo/ai/speaking_end` or `set_state`; if set via `set_state`, 15s safety timeout

### `SAD`
- Eyes squint (height ×0.35)
- Mouth arc curves **downward** (0 → π = top arc = frown `:(`)
- Sad `\\` eyebrows (outer corners higher)
- Blue-tint overlay (`COLOR_SAD_TINT`, alpha 40)
- Hold 4s → `IDLE`

### `STRESSED`
- Eyes open (height ×1.2) with **X pupils** (crossing lines, like 😵)
- Angry `\/` eyebrows (inner corners lower)
- Zigzag mouth (8-segment sawtooth)
- Red-tint overlay suggestion via HOT_TINT
- Hold 5s → `IDLE`

### `HOT`
- Eyes squint (height ×0.7)
- Red-tint overlay fades in (`COLOR_HOT_TINT`, alpha 45)
- Two sweat drops (blue circles) on right side of screen panel
- Hold 5s → `IDLE`

### `WORRIED`
- `/\` eyebrows (inner edges raised)
- Pupils dart left-right (0.4s cycle sine)
- Slightly open mouth (small ellipse)
- Hold 5s → `IDLE`

### `ALERT`
- Eyes snap wide open (height ×1.45)
- Wide open "O" mouth
- Flashing coloured border (`COLOR_ALERT`)
- Small "!" rendered at top-center of screen panel
- **Notification text box** at panel bottom: title (yellow) + message (grey), semi-transparent dark background
- Hold **5s** → `IDLE` (or resumes `SPEAKING` if interrupted)

### `SLEEP`
- Dim overlay fades to alpha 180 over 2s
- Eyes half-close and pupils are hidden
- Floating "z z z" glyphs in top-right of screen panel
- Subdued glow and eye breathing use an 8s cycle

### `WAKE`
- Dim overlay fades out over 1s
- Eyes open fully and pupils pop upward
- Transition to `IDLE` after 1s

---

## TTS Amplitude Contract

Interface between `bmo-ai` (M6) / `bmo-voice` (M5) and `bmo-face` (M2) for SPEAKING mouth sync:

```json
{
  "amplitude": [0.0, 0.4, 0.9, 0.7, 0.2],
  "sample_rate_hz": 10
}
```

- `amplitude`: floats `0.0–1.0` — mouth open height = `scale(5) + amplitude[i] * scale(16)`
- `sample_rate_hz`: samples consumed per second by bmo-face (default: 10)
- **If field absent or empty:** fall back to fixed 8 Hz open/close oscillation

---

## MQTT Topics (Subscribe)

| Topic                        | Payload                                                  | Action                                  |
| ---------------------------- | -------------------------------------------------------- | --------------------------------------- |
| `bmo/camera/person_detected` | `{}`                                                                    | Start wake / cancel sleep timer         |
| `bmo/camera/person_left`     | `{}`                                                                    | Start 5-min sleep timer                 |
| `bmo/camera/face_position`   | `{"x": 0.0–1.0}`                                                        | Trigger look_left/right                 |
| `bmo/voice/wake_word`        | `{}`                                                                    | → `THINKING`                            |
| `bmo/voice/listening_start`  | `{}`                                                                    | → `LISTENING` (10s timeout)             |
| `bmo/ai/speaking_start`      | `{"amplitude": [...], "sample_rate_hz": 10}`                           | → `SPEAKING`                            |
| `bmo/ai/speaking_end`        | `{}`                                                                    | → `IDLE`                                |
| `bmo/system/state`           | `{"emotion": "happy|stressed|hot|worried"}`                            | → mapped emotion state                  |
| `bmo/ai/proactive_start`     | `{}`                                                                    | `IDLE` → `THINKING`                     |
| `bmo/notify/event`           | `{"title":"...","message":"...","priority":"low|medium|high"}`         | `priority=high` → `ALERT` (5s, shows title+msg) |
| `bmo/voice/bt_disconnect`    | `{}`                                                                    | → `SAD`                                 |
| `bmo/face/set_state`         | `{"state": "<state_name>"}`                                             | Direct override (priority 6, always wins; invalid names ignored) |
| `bmo/face/brightness`        | `{"level": 0.0–1.0}`                                                    | Set display brightness                  |

## MQTT Topics (Publish)

| Topic            | Payload            | When                      |
| ---------------- | ------------------ | ------------------------- |
| `bmo/face/state` | `{"state": "..."}` | On every state change     |
| `bmo/face/ready` | `{}`               | After BOOT animation ends |

---

## REST API

Base URL: `http://localhost:5200`

| Method | Endpoint      | Body / Params        | Description                |
| ------ | ------------- | -------------------- | -------------------------- |
| GET    | `/state`      | —                    | Current state              |
| POST   | `/state`      | `{"state": "happy"}` | Force state change         |
| GET    | `/health`     | —                    | Service health check       |
| POST   | `/brightness` | `{"level": 0.0–1.0}` | Override screen brightness |

---

## Config (`config/bmo.yaml` section)

```yaml
face:
  fps_target: 30
  fps_fallback: 24
  fullscreen: true
  resolution: auto          # or "320x240" for 3.2" LCD
  sleep_timeout_seconds: 300
  mqtt_broker: localhost
  mqtt_port: 1883
  api_port: 5200
```

---

## Tasks

### File-level implementation checklist (tracking)

#### Phase 1 — Foundation
- [x] Create `services/bmo-face/requirements.txt` with runtime and test dependencies
- [x] Create `services/bmo-face/config.py` with config load + validation (`fps_target=30`, `fps_fallback=24`)
- [x] Create `services/bmo-face/face/colors.py` with palette constants + `ScaleContext.scale()`
- [x] Create `services/bmo-face/face/components.py` with `build_face_layout()`
- [x] Create `services/bmo-face/renderer.py` runtime loop scaffold + event queue plumbing
- [x] Add baseline `config/bmo.yaml` face section

#### Phase 2 — Animation Core
- [x] Add `services/bmo-face/face/animations.py` for IDLE/SLEEP glow, breathing, amplitude sampling, and speaking fallback
- [x] Add independent blink scheduler and animated eyelid timing in `services/bmo-face/face/state_machine.py`
- [x] Add BOOT flicker/eye/mouth sequence, completion transition, and ready publish event
- [x] Add SLEEP/WAKE timing with dim/undim progression

#### Phase 3 — Reactive States
- [x] Add LOOK_LEFT/LOOK_RIGHT mapping from `bmo/camera/face_position`
- [x] Add emotion transitions (`happy`, `stressed`, `hot`, `worried`) from `bmo/system/state`
- [x] Add `SAD` transition from `bmo/voice/bt_disconnect`
- [x] Add `ALERT` interrupt from `bmo/notify/event` with high priority
- [x] Add `THINKING` from wake/proactive events
- [x] Add `SPEAKING` entry/exit + amplitude handling

#### Phase 4 — State Machine
- [x] Implement `FaceState` enum and `FaceStateMachine` core
- [x] Implement priority ladder + coalescing for lower-priority events during THINKING/LISTENING/SPEAKING/ALERT
- [x] Implement sleep timeout + cancellation
- [x] Implement transient timeout exits and alert exit rule

#### Phase 5 — Integration
- [x] Create `services/bmo-face/mqtt_client.py` with complete subscriptions, payload checks, and reconnect policy
- [x] Create `services/bmo-face/api.py` with `/health`, `/state`, `/brightness`
- [x] Create `services/bmo-face/main.py` wiring runtime + mqtt + api
- [x] Add signal handler, fade-to-black, pygame cleanup, and joined API/MQTT shutdown

#### Phase 6 — Ops
- [x] Create `services/bmo-face/systemd/bmo-face.service`
- [x] Create `scripts/install-face.sh` for virtual environment and dependency setup
- [ ] Device smoke test execution on S905X
- [ ] 1h memory profile execution on S905X

### Phase 1 — Foundation

- [ ] **T0** Install Mosquitto MQTT broker, enable service, and verify local pub/sub health
- [ ] **T0b** Benchmark pygame-ce renderer on S905X; verify automatic fallback when measured FPS stays below 80% of target for 2 seconds
- [x] **T1** Set up `services/bmo-face/` project skeleton (venv, requirements.txt, config loader)
- [x] **T2** Scaffold pygame-ce window: fullscreen, `pygame.SCALED` flag, auto-detect resolution, FPS loop with fallback
- [x] **T3** Define color palette constants + `scale()` helper in `face/colors.py`
- [x] **T4** Draw static BMO face: screen border, eyes, mouth — all using `scale()` in `face/components.py`

### Phase 2 — Animation Core

- [x] **T5** Implement `IDLE` state: glow pulse (sine wave) + breathing pupils
- [x] **T6** Implement `BLINK` overlay: independent timer, eyelid sweep
- [x] **T7** Implement `BOOT` startup sequence (flicker → eyes open → mouth fade)
- [x] **T8** Implement `SLEEP` state: dim overlay + half-close eyes + slow pulse
- [x] **T9** Implement `WAKE` state: reverse dim + pupil pop → IDLE

### Phase 3 — Reactive States

- [x] **T10** Implement `LOOK_LEFT` / `LOOK_RIGHT`: pupil translation + auto-return 500ms after last event
- [x] **T11** Implement `HAPPY` state: mouth arc + eye squint + 3s timeout
- [x] **T12** Implement `SAD` state: downward mouth arc + blue tint + 4s timeout
- [x] **T13** Implement `STRESSED` state: jittering X eyes + red tint + screen shake + 5s timeout
- [x] **T14** Implement `HOT` state: red tint overlay + sweat drop + eye squint + 5s timeout
- [x] **T15** Implement `WORRIED` state: inverted-V brows + eye dart + 5s timeout
- [x] **T16** Implement `ALERT` state: wide eyes + flashing border + `!` icon + **notification text box** (title + message) + return to IDLE (or resume SPEAKING if interrupted)
- [x] **T17** Implement `THINKING` state: scanning pupils + 3 pulsing staggered dots (pygame circles, no font)
- [x] **T18** Implement `SPEAKING` state: animated oval mouth with 8 Hz fallback oscillation (amplitude envelope when provided)

### Phase 4 — State Machine

- [x] **T19** Implement `StateMachine` class: states, transitions, event dispatch
- [x] **T20** Wire all 15 animation states (including LISTENING) into state machine with correct transitions
- [x] **T21** Implement state priority ladder: higher priority interrupts lower; coalesce lower-priority events during active interaction states
- [x] **T22** Add sleep timer logic (5-min countdown, reset on `person_detected`)
- [x] **T23** Add blink as independent overlay timer (not blocked by state changes)

### Phase 5 — Integration

- [x] **T24** Implement MQTT client: subscribe to all topics, validate payload objects, dispatch events, and configure reconnect backoff
- [x] **T25** Implement MQTT publisher: emit `bmo/face/state` on transitions, `bmo/face/ready` on boot
- [x] **T26** Implement REST API (`/state`, `/health`, `/brightness`) in `api.py`
- [x] **T27** Run API in-process with a thread-safe event queue (no direct cross-thread state mutation)
- [x] **T28** Add SIGTERM handler: fade to black, stop API/MQTT, and quit pygame cleanly

### Phase 6 — Ops

- [x] **T29** Write `systemd` unit file: `bmo-face.service` (auto-start, restart on failure)
- [x] **T30** Write install script: `scripts/install-face.sh` (venv and dependency setup; systemd installation is documented separately)
- [ ] **T31** Smoke test: boot device → BMO face appears → MQTT event changes state → verified
- [ ] **T32** Memory profile: run for 1h → record baseline RSS and keep steady-state within baseline +20% (soft target ≤120MB)

---

## Dependencies

```
pygame-ce>=2.4.0
pillow>=10.0.0
paho-mqtt>=2.0.0
flask>=3.0.0       # REST API
pyyaml>=6.0.0      # Config loader
psutil>=5.9.0      # Memory profiling
```

---

## Acceptance Criteria

- [ ] BMO face renders fullscreen with target 30 FPS and fallback 24 FPS on Armbian (Amlogic S905X)
- [ ] All 15 base states animate correctly on target displays (automated state/draw tests pass; device visual acceptance pending)
- [x] State priority ladder enforced: ALERT interrupts SPEAKING; SLEEP cannot interrupt THINKING
- [x] `bmo/face/set_state` always bypasses coalescing (priority 6); can override SPEAKING/THINKING
- [x] `set_state` forced SPEAKING has 15s safety timeout; never traps face permanently
- [ ] MQTT event → state change latency < 100ms
- [x] Blink overlay runs independently, never blocked by other states
- [x] Sleep triggers exactly after 5 min of `PERSON_LEFT`; cancels on `PERSON_DETECTED`
- [ ] Scale test: face proportions visually consistent at `320×240` and `1920×1080` on target displays
- [x] SPEAKING mouth syncs to amplitude envelope; falls back to 8 Hz if absent
- [x] REST `/health` returns 200 when service is running
- [ ] MQTT broker restart → face reconnects automatically within 30s
- [ ] SIGTERM → clean exit (screen fades to black) in < 2s on the Playbox
- [ ] `bmo-face.service` survives a reboot (auto-starts)
- [ ] bmo-face steady-state RSS after 1h stays within baseline +20% (soft target ≤120MB)
