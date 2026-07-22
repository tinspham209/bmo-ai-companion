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

## Stack

- Python 3.11+
- pygame-ce
- Pillow

## Tasks

- [ ] Fullscreen display (resolution-agnostic; scale helper for 320×240 ↔ 1920×1080)
- [ ] 60 FPS renderer (30 FPS fallback if Mali-450 has no GPU driver on Armbian)
- [ ] Idle animation
- [ ] Blink animation (independent overlay, never blocked by state changes)
- [ ] Look left/right (driven by camera face position)
- [ ] Sleep / Wake (5-min no-presence timeout)
- [ ] State machine (14 states with priority ladder)
- [ ] Emotional states: happy, sad, stressed, hot, worried, alert
- [ ] MQTT broker setup (Mosquitto — prerequisite for all services)
- [ ] Graceful shutdown + MQTT auto-reconnect

Deliverable:
Boot directly into a living BMO face.

---

# Milestone 3 - Camera

Status: Webcam working ✅

Next:

- [ ] OpenCV service
- [ ] Face detection
- [ ] Motion detection
- [ ] Presence timeout
- [ ] Publish events

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