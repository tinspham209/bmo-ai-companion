# BMO AI Companion — Product Specification

**Date:** 2026-07-22
**Version:** 1.1
**Status:** Approved
**Idea spec:** `docs/2026-07-22-01-bmo-ai-companion-idea.md`


---

## 1. Overview

BMO AI Companion is a physical desktop companion device inspired by BMO from *Adventure Time*. It runs on an FPT Playbox S400 (Amlogic S905X, 1GB RAM, 8GB eMMC) with Armbian, presenting an animated face on an LCD display, responding to voice commands, and reacting to its environment through camera awareness, system monitoring, Home Assistant integration, and notifications.

---

## 2. Hardware

| Component      | Spec                                          |
| -------------- | --------------------------------------------- |
| SoC            | Amlogic S905X                                 |
| RAM            | ~800MB usable                                 |
| Storage        | 8GB eMMC (~3.4GB free)                        |
| OS             | Armbian 26.02 (Debian Trixie, kernel 6.1.160) |
| Wi-Fi / BT     | Broadcom AP6356S                              |
| Speaker        | EDIFIER MP85 (Bluetooth)                      |
| Webcam         | Aukey PC-3 FullHD                             |
| Display (dev)  | 27" HDMI monitor                              |
| Display (prod) | 3.2" HDMI LCD                                 |

---

## 3. Architecture

### 3.1 Service Layout

```
bmo-ai-companion/
├── docs/
├── assets/
│   ├── animations/
│   ├── sounds/
│   ├── fonts/
│   └── personalities/
├── services/
│   ├── bmo-face/        # Face renderer (pygame-ce)
│   ├── bmo-camera/      # Webcam + vision events
│   ├── bmo-monitor/     # System stats → emotions
│   ├── bmo-voice/       # Wake word → STT → TTS
│   ├── bmo-ai/          # LLM conversation manager
│   └── bmo-notify/      # Notification aggregator
├── config/
├── scripts/
└── docker/
```

### 3.2 Inter-Service Communication

- **Message bus:** MQTT (or Redis pub/sub) — all services publish and subscribe to events
- Each service is **fully independent** and can be restarted without affecting others
- Services expose a **local REST or WebSocket API** for direct queries

### 3.3 Service Orchestration

- Each service runs as a **systemd unit** (avoids Docker overhead on constrained RAM)
- Services start on boot; watchdog restarts on failure

### 3.4 Infrastructure Prerequisites

- **MQTT Broker:** Mosquitto installed, enabled at boot, and health-checked — prerequisite for ALL services. Must be deployed before any milestone service starts.
- **Config:** `config/bmo.yaml` (shared, per-service sections) + `config/secrets.yaml` (tokens/keys, gitignored)

---

## 4. Milestones

### Milestone 2 — Face Engine *(Priority 1)*

**Stack:** Python 3.11+, pygame-ce, Pillow

**Display:**
- Fullscreen, resolution-agnostic (detects at runtime)
- Targets 30 FPS (fallback 24 FPS on constrained hardware)
- Scales correctly from 27" dev monitor → 3.2" production LCD

**Rendering approach:** Procedurally drawn (pygame vector shapes + transitions) — no external sprite assets required, scales to any resolution.

**Color palette:**
- Body: `#78C8C8` (classic BMO teal)
- Screen background: `#1a1a2e`
- Eyes / mouth: white + green (matching the show)

**Startup sequence:** Power-on animation — screen flicker → BMO eyes open → settle into `idle`.

**Animations / States:**

| State        | Description                                                            |
| ------------ | ---------------------------------------------------------------------- |
| `idle`       | Subtle breathing/glow loop                                             |
| `blink`      | Random eye blink every 3–6s                                            |
| `look_left`  | Eyes shift left (camera detects face left of center)                   |
| `look_right` | Eyes shift right (camera detects face right of center)                 |
| `sleep`      | Dims + slow breath; triggered after 5 min of no presence               |
| `wake`       | Brightens; triggered by presence detected                              |
| `happy`      | Upward curve mouth                                                     |
| `thinking`   | Eyes scroll / loading indicator                                        |
| `speaking`   | Mouth animates in sync with TTS                                        |
| `sad`        | Drooping mouth, half-close eyes, blue tint; triggered by BT disconnect |
| `stressed`   | Pupils vibrate, screen shake; triggered by CPU > 80%                   |
| `hot`        | Red tint overlay, sweat drop; triggered by Temp > 70°C                 |
| `worried`    | Raised brows, eye dart; triggered by Disk < 500MB                      |
| `alert`      | Wide eyes + `!` flash; triggered by high-priority notification         |

**State machine:** Driven by MQTT events published by other services.

**State priority ladder:** `ALERT(6) > SPEAKING(5) > THINKING(4) > Emotion/Look(3) > IDLE/WAKE(2) > SLEEP(1)`. Higher priority interrupts lower; during SPEAKING/THINKING, low-priority events are coalesced (keep latest) instead of fully queued.

**Alert exit rule:** `alert` returns to `idle` after timeout, except when it interrupts `speaking`, in which case it resumes `speaking`.

**Scale contract:** All rendering uses a `scale()` helper — `SCALE = min(w, h) / 240` — ensuring correct proportions at both `320×240` (prod LCD) and `1920×1080` (dev monitor). No hardcoded pixel values.

**Deliverable:** Boot directly into a living, animated BMO face.

---

### Milestone 3 — Camera Service

**Stack:** Python, OpenCV (on-device only — no cloud vision)

**Camera mode:**
- Always-on at full frame rate when active
- Drops to **5 FPS** in sleep mode (low power)

**Events published to MQTT:**

| Event             | Trigger                        |
| ----------------- | ------------------------------ |
| `PERSON_DETECTED` | Face detected in frame         |
| `PERSON_LEFT`     | Face absent for **10 seconds** |
| `MOTION`          | Motion delta above threshold   |
| `NO_MOTION`       | No motion for N seconds        |

**Privacy:** 100% on-device processing. No frames leave the device.

---

### Milestone 4 — System Monitor

**Collects:** CPU, RAM, Temperature, Disk, Wi-Fi, Bluetooth

**Maps system state → BMO emotions:**

| Condition    | Emotion    |
| ------------ | ---------- |
| CPU > 80%    | `stressed` |
| Temp > 70°C  | `hot`      |
| Disk < 500MB | `worried`  |
| All nominal  | `happy`    |

Publishes `bmo/system/state` events to MQTT.

---

### Milestone 5 — Voice Pipeline

**Pipeline:**
```
OpenWakeWord → Whisper.cpp → LLM (bmo-ai) → Piper TTS → Bluetooth Speaker
```

**Wake Words:** `"Hey Dog"` | `"Ok Dog"`
*(Custom OpenWakeWord model to be trained)*

**Language support:** **Vietnamese + English in parallel** (high priority)
- STT: Whisper `tiny`/`base` model — multilingual, handles both VI + EN natively (~150MB)
- TTS: Piper with Vietnamese voice model + English voice model; language auto-detected from STT output

**Wake word acknowledgment:** Short chime + `thinking` face plays immediately on wake word detect (before STT finishes).

**Conversation mode:** Multi-turn — BMO stays in conversation mode for **30 seconds** after last response, then returns to idle (no need to re-trigger wake word).

**Bluetooth speaker fallback:** If speaker disconnects mid-conversation, fall back to HDMI audio output and show a `sad` face animation.

**TTS→Face amplitude contract:** `bmo-voice` publishes to `bmo/ai/speaking_start` with:
```json
{"amplitude": [0.0–1.0, ...], "sample_rate_hz": 10}
```
bmo-face consumes this for mouth sync. Falls back to 8 Hz fixed oscillation if absent. See M2 plan for full contract spec.

**Tasks:**
- Wake word detection (always-on, low CPU)
- Speech-to-text: Whisper.cpp (local, multilingual VI + EN)
- TTS: Piper (local, VI + EN voice models)
- Conversation manager: maintains session context in RAM

---

### Milestone 6 — AI Service

**Mode:** Local-only first; cloud optional fallback later

**Local stack:** Ollama + **Qwen2.5:0.5b** or **Phi3:mini** (quantized GGUF, ~300–400MB to fit RAM budget)

**Whisper model:** `tiny` or `base` (~150MB) — multilingual, acceptable accuracy for VI + EN

**System Prompt:**
```
You are BMO from Adventure Time.
Be cheerful, playful and emotional.
Always call the user "Best Friend".
```

**Memory:** Session-only (RAM). No persistent history across reboots.

**Idle behaviour:** BMO occasionally starts conversation proactively — a random idle remark every **15–30 minutes** (e.g., *"Best Friend, I learned something cool today!"*). Publishes `bmo/ai/proactive_start → {}` to trigger `THINKING` face before speaking.

**Cloud fallback (future):** Optional API token via config; disabled by default.

---

### Milestone 7 — Notification Engine

**Sources:** Weather, Calendar, Spotify, Docker, GitHub, Home Assistant

Each source is a plugin that publishes a `NOTIFICATION` event to MQTT with:
```json
{ "source": "weather", "message": "...", "priority": "low|medium|high" }
```

Topic: `bmo/notify/event`

**Queue behaviour:**
- `high` — interrupts current interaction immediately
- `medium` — queued, delivered after current interaction ends
- `low` — queued, **face animation only** (no voice announcement)

BMO displays high/medium notifications as face reactions + spoken announcements.

---

### Milestone 8 — Home Assistant Integration

**Connection:** WebSocket (`hass-client`) for real-time event reactivity

**Config:** HA WebSocket URL and token stored in `config/home-assistant.yaml` (excluded from git via `.gitignore`)

**Reacts to:**

| HA Event      | BMO Reaction          |
| ------------- | --------------------- |
| Door opened   | Look toward door      |
| Lights off    | Switch to sleep mode  |
| Motion sensor | Alert / curious face  |
| Weather alert | Announce notification |

---

### Milestone 9 — Hardware Polish

- RGB LEDs (ambient mood lighting)
- Decorative buttons (non-functional or shortcut triggers)
- Speaker grille enclosure
- Fan control based on temperature

---

## 5. Configuration

- **Shared config:** `config/bmo.yaml` — one file with per-service sections, loaded at startup by each service
- **Secrets** (HA token, API keys): separate `config/secrets.yaml`, excluded from git via `.gitignore`
- **Remote control:** MQTT messages + config files only (no web dashboard in scope)

---

## 6. Decisions Log

| #   | Decision            | Choice                             | Rationale                                          |
| --- | ------------------- | ---------------------------------- | -------------------------------------------------- |
| 1   | Inter-service comms | MQTT pub/sub                       | Decoupled, lightweight, works on 1GB RAM           |
| 2   | Display resolution  | Resolution-agnostic                | No rework when switching to 3.2" LCD               |
| 3   | Face rendering      | Procedural (pygame shapes)         | Scales to any resolution, easy to animate          |
| 4   | Wake word           | "Hey Dog" / "Ok Dog"               | User preference                                    |
| 5   | AI mode             | Local-only (Ollama) first          | RAM constraints; cloud as future option            |
| 6   | Camera privacy      | 100% on-device                     | No cloud vision APIs                               |
| 7   | HA connection       | WebSocket                          | Real-time event reactivity                         |
| 8   | Conversation memory | Session-only (RAM)                 | Simplicity; no sensitive data persisted            |
| 9   | Orchestration       | systemd                            | Less overhead than Docker on 1GB RAM               |
| 10  | First milestone     | Face Engine (M2)                   | Visual core; all services react to it              |
| 11  | STT/TTS language    | Vietnamese + English (parallel)    | User is Vietnamese; high priority bilingual        |
| 12  | Whisper model       | tiny/base (~150MB)                 | Multilingual VI+EN; fits RAM budget                |
| 13  | LLM model           | Qwen2.5:0.5b or Phi3:mini          | ~300–400MB quantized; fits RAM headroom            |
| 14  | Sleep timeout       | 5 min no presence                  | Reasonable idle delay before dimming               |
| 15  | PERSON_LEFT timeout | 10 seconds                         | Low-latency but avoids false positives             |
| 16  | Conversation mode   | Multi-turn, 30s window             | Natural dialogue without re-triggering wake word   |
| 17  | Notification queue  | Priority queue (high/med/low)      | Prevents interruption spam                         |
| 18  | Config management   | Single shared bmo.yaml             | Simple, one source of truth per service            |
| 19  | Face state count    | 14 states (9 original + 5 new)     | sad/stressed/hot/worried/alert needed for M4/M5/M7 |
| 20  | State priority      | Priority ladder 1–6 + coalescing   | Avoid interruption lag and event backlog           |
| 21  | Scale helper        | `scale() = min(w,h)/240`           | Resolution-agnostic on 320×240 and 1920×1080       |
| 22  | TTS amplitude       | `{amplitude:[],sample_rate_hz:10}` | Cross-service contract M5↔M2 for mouth sync        |
| 23  | MQTT broker         | Mosquitto install + enable + health check | Prerequisite for all services, deploy first |
| 24  | FPS fallback        | Target 30 FPS, fallback 24 FPS     | Reduce performance load while keeping smooth motion |
| 25  | MQTT reconnect      | paho reconnect_delay_set(1,30)     | Survive broker restarts without manual fix         |
| 26  | Proactive speech    | `bmo/ai/proactive_start` topic     | AI idle remarks must trigger THINKING face         |

---

## 7. Implementation Order

1. Face Engine (M2)
2. Camera Events (M3)
3. System Monitor (M4)
4. Voice Pipeline (M5)
5. AI Service (M6)
6. Notification Service (M7)
7. Home Assistant (M8)
8. Hardware Polish (M9)
