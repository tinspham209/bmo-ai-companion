# BMO AI Companion

> A physical desktop companion shaped like BMO from Adventure Time — powered by voice, camera, and AI.

```
             ┌─────────────────────┐
             │  Webcam + Mic       │
             ├─────────────────────┤
             │                     │
             │   🟢 BMO Face LCD   │
             │                     │
             ├─────────────────────┤
             │  Speaker            │
             ├─────────────────────┤
             │  FPT Playbox S400   │
             └─────────────────────┘
```

---

## What is this?

BMO AI Companion turns an FPT Playbox S400 into a living desktop character:

- **Animated face** that reacts in real time to voice, camera, system events, and notifications
- **Wake word** recognition ("Hey Dog" / "Ok Dog") → starts listening
- **Voice conversation** in Vietnamese + English
- **Camera awareness** — sees you, tracks face position, goes to sleep when you leave
- **Home Assistant integration** — receives smart home notifications
- **Modular microservices** — each feature is an independent service, communicating over MQTT

---

## Hardware

| Component        | Model / Detail                          |
| ---------------- | --------------------------------------- |
| Box              | FPT Playbox S400                        |
| SoC              | Amlogic S905X, 1 GB RAM, 8 GB eMMC     |
| OS               | Armbian (Debian Trixie, kernel 6.1)     |
| Display          | 3.2" HDMI LCD (target) / HDMI monitor (dev) |
| Camera           | Aukey PC-3 Full HD USB webcam           |
| Speaker          | EDIFIER MP85 Bluetooth                  |
| Connectivity     | Broadcom AP6356S Wi-Fi + Bluetooth      |

---

## Architecture

All services communicate over a local **MQTT broker** (Mosquitto).  
Each service is an independent Python process managed by **systemd**.

```
                     ┌──────────────────────────────────────────────┐
                     │              MQTT Broker (Mosquitto)          │
                     └────┬─────────┬──────────┬────────┬───────────┘
                          │         │          │        │
                   ┌──────┴──┐  ┌───┴────┐  ┌─┴────┐  ┌┴────────────┐
                   │bmo-face │  │bmo-voice│  │bmo-ai│  │bmo-camera   │
                   │(M2) ✅  │  │(M5) 🔜 │  │(M6)🔜│  │(M4) 🔜     │
                   └─────────┘  └────────┘  └──────┘  └─────────────┘
                        │
               ┌────────┴────────┐
               │bmo-notify (M7)🔜│   ┌──────────────────┐
               │bmo-ha     (M8)🔜│   │bmo-system (M3) 🔜│
               └─────────────────┘   └──────────────────┘
```

### Services

| Service        | Milestone | Status | Description                              |
| -------------- | --------- | ------ | ---------------------------------------- |
| `bmo-face`     | M2        | ✅ Done | Animated BMO face — pygame-ce renderer   |
| `bmo-system`   | M3        | 🔜 Next | CPU/RAM/temp monitoring → emotion states |
| `bmo-camera`   | M4        | 🔜     | Face detection, person presence tracking |
| `bmo-voice`    | M5        | 🔜     | Wake word, STT (Vietnamese + English)    |
| `bmo-ai`       | M6        | 🔜     | LLM conversation, TTS synthesis          |
| `bmo-notify`   | M7        | 🔜     | Notification queue, priority routing     |
| `bmo-ha`       | M8        | 🔜     | Home Assistant integration               |
| `bmo-hw`       | M9        | 🔜     | Fan control, LED strips, button input    |

---

## Repository Structure

```
bmo-ai-companion/
├── config/
│   └── bmo.yaml                  # Shared config for all services
├── docs/
│   ├── 2026-07-22-01-bmo-ai-companion-specs.md    # Master spec v1.1
│   ├── 2026-07-22-01-bmo-ai-companion-idea.md     # Original idea
│   └── milestone/
│       └── 2/
│           ├── milestone-2-plan.md                # M2 implementation plan
│           └── milestone-2-test_plan.md           # M2 TDD + manual tests
├── scripts/
│   └── install-face.sh           # Setup script for bmo-face
└── services/
    └── bmo-face/                 # ← Milestone 2 (face engine, complete)
        └── README.md             # Setup + run guide with test commands
```

---

## Quick Start (bmo-face service)

```bash
# 1. Install MQTT broker
sudo apt install mosquitto mosquitto-clients
sudo systemctl enable --now mosquitto

# 2. Setup and run the face service
cd services/bmo-face
bash ../../scripts/install-face.sh
.venv/bin/python main.py
```

See [`services/bmo-face/README.md`](services/bmo-face/README.md) for full setup, all test commands, and a complete payload reference.

---

## MQTT Topic Map

| Topic                        | Direction | Description                        |
| ---------------------------- | --------- | ---------------------------------- |
| `bmo/face/set_state`         | → face    | Force a face state directly        |
| `bmo/face/state`             | face →    | Published on every state change    |
| `bmo/face/ready`             | face →    | Published after boot completes     |
| `bmo/face/brightness`        | → face    | Set screen brightness 0.0–1.0      |
| `bmo/notify/event`           | → face    | Show notification (priority=high)  |
| `bmo/system/state`           | → face    | Emotion trigger (happy/hot/etc.)   |
| `bmo/voice/wake_word`        | → face    | Wake word detected → THINKING      |
| `bmo/voice/listening_start`  | → face    | STT listening → LISTENING          |
| `bmo/ai/speaking_start`      | → face    | TTS start → SPEAKING               |
| `bmo/ai/speaking_end`        | → face    | TTS end → IDLE                     |
| `bmo/camera/person_detected` | → face    | Person seen → cancel sleep timer   |
| `bmo/camera/person_left`     | → face    | Person gone → start sleep timer    |
| `bmo/camera/face_position`   | → face    | `{"x": 0.0–1.0}` → look direction |
| `bmo/voice/bt_disconnect`    | → face    | Bluetooth lost → SAD               |

---

## Development Notes

- **Language:** Python 3.11+
- **Renderer:** pygame-ce (SDL2), target 30 FPS / fallback 24 FPS
- **Event bus:** paho-mqtt v2, `connect_async()` for resilient startup
- **Config:** `config/bmo.yaml` — shared across all services
- **Tests:** `pytest` — run `pytest tests/` inside any service directory
- **Scale system:** all geometry uses `ScaleContext.scale()` — works at 320×240 and 1080p

---

## Docs

- [Master Specification](docs/2026-07-22-01-bmo-ai-companion-specs.md)
- [Milestone 2 Plan](docs/milestone/2/milestone-2-plan.md)
- [Milestone 2 Test Plan](docs/milestone/2/milestone-2-test_plan.md)
