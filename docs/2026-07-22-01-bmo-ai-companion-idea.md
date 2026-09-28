# BMO AI Companion - Development Plan

## Current Status

| Component         | Status |
| ----------------- | ------ |
| FPT Playbox S400  | ✅      |
| Armbian           | ✅      |
| Wi-Fi             | ✅      |
| Bluetooth Speaker | ✅      |
| HDMI LCD          | ✅      |
| Webcam            | ✅      |
| Face Engine       | 🟡 Code implemented; target-device acceptance pending |

### Specs devices

- Box: FPT Playbox S400
- Amlogic S905X SoC, 1GB RAM, 8GB eMMC storage ()
- Armbian ver: Armbian_26.02.0_amlogic_s905x-b860h_trixie_6.1.160_server_2026.01.15
- RAM (53.9% of ~800MB used)
- CPU (0.5% load)
- Disk Space (3.43 GB free)
- Wifi/Bluetooth: working
- Broadcom AP6356S Wi-Fi/Bluetooth chip
- Speaker: EDIFIER MP85
- Webcam: Aukey PC-3 FullHD
- Monitor: temporary use the 27inch for testing, later will use the 3.2inch HDMI LCD

## Goal

Build a desktop BMO companion with:
- Animated BMO face
- Voice assistant
- Webcam awareness
- AI conversation
- Home Assistant integration
- Notifications
- Modular architecture

## BMO Box idea

```
             ┌─────────────────────┐
             │  Webcam+Mic Module  │
             ├─────────────────────┤
             │                     │
             │    LCD Module       │
             │                     │
             ├─────────────────────┤
             │  Speaker inside     │
             ├─────────────────────┤
             │   Button mock       │
             │  Playbox S400       │
             │                     │
             ├─────────────────────┤
             │ Cable Manager       │
             └─────────────────────┘
```

---

# Milestone 1 - Project Structure

```
bmo-ai-companion/
├── docs/
├── assets/
│ ├── animations/
│ ├── sounds/
│ ├── fonts/
│ └── personalities/
├── services/
│ ├── bmo-face/
│ ├── bmo-camera/
│ ├── bmo-monitor/
│ ├── bmo-voice/
│ ├── bmo-ai/
│ └── bmo-notify/
├── config/
├── scripts/
└── docker/
```

---

# Milestone 2 - Face Engine

**Status:** In progress. The `services/bmo-face` renderer, animations, state machine, MQTT client, REST API, systemd unit, and automated tests are implemented. Mosquitto/device operation, visual acceptance on both displays, reboot behavior, and the one-hour memory profile still need to be verified on the Playbox.

## Stack

- Python 3.11+
- pygame-ce
- Pillow

## Tasks

- [x] Fullscreen, resolution-agnostic rendering and `scale()` helper (code implemented; display validation pending)
- [x] 30 FPS target with 24 FPS fallback after sustained low measured FPS
- [x] Idle, blink overlay, look, sleep/wake, startup, and emotional animations
- [x] Fifteen face states with priority handling; blink is an independent overlay
- [x] MQTT event/publish adapter and reconnect backoff
- [x] Local REST API and graceful process shutdown
- [ ] Install/health-check Mosquitto on the Playbox and verify reconnect after broker restart
- [ ] Run display, boot/reboot, latency, and one-hour memory acceptance checks on the Playbox

Deliverable:
Boot directly into a living BMO face.

---

# Milestone 3 - Camera

**Status:** Camera service software is implemented and 51 automated tests pass. MacBook live presence/position/motion events, sleep analysis rate, and broker reconnect were verified; native visual/privacy checks and Aukey/Playbox acceptance remain pending. AVFoundation did not reduce native capture FPS in sleep.
**Plan:** `docs/milestone/3/milestone-3-plan.md`
**Test plan:** `docs/milestone/3/test-plan.md`

Software implementation:

- [x] OpenCV capture and face/motion detection
- [x] Presence timeout, face position, and MQTT events
- [x] Sleep-rate handling, status API, and graceful shutdown

Acceptance still pending:

- [x] Grant macOS camera access and open the built-in camera; local API and face-position MQTT smoke checks pass
- [x] Verify live MacBook presence, face-position, motion, and no-motion MQTT events
- [x] Restart local Mosquitto and verify camera status and event publishing recover
- [ ] Confirm visible face animation and inspect filesystem/log/network for image data
- [ ] Test the Aukey webcam on the Playbox and complete FPS, systemd, privacy, and resource checks

Events:
- PERSON_DETECTED
- PERSON_LEFT
- MOTION
- NO_MOTION

---

# Milestone 4 - System Monitor

Collect:

- CPU
- RAM
- Temperature
- Disk
- WiFi
- Bluetooth

Map system state to emotions.

---

# Milestone 5 - Voice

Pipeline:

OpenWakeWord
→ Whisper.cpp
→ LLM
→ Piper TTS
→ Bluetooth Speaker

Tasks:

- [ ] Wake word
- [ ] Speech to text
- [ ] TTS
- [ ] Conversation manager

---

# Milestone 6 - AI

Modes:

- Local (Ollama + Qwen2.5/Phi)
- Cloud (maybe opencode go api_token)

System prompt:

You are BMO from Adventure Time.
Be cheerful, playful and emotional.
Always call the user "Best Friend".

---

# Milestone 7 - Notification Engine

Sources:

- Weather
- Calendar
- Spotify
- Docker
- GitHub
- Home Assistant

---

# Milestone 8 - Home Assistant

React to:

- Door
- Lights
- Weather
- Motion
- Automations

---

# Milestone 9 - Hardware

- [ ] RGB LEDs
- [ ] Decorative buttons
- [ ] Speaker grille
- [ ] Fan control

---

# Daily Coding Order

1. Face Engine
2. Camera Events
3. System Monitor
4. Voice Pipeline
5. AI Service
6. Notification Service
7. Home Assistant
8. Hardware polish

Each service should expose a simple local API (REST/WebSocket) and run independently under systemd for easy debugging.