# bmo-face

> Animated BMO face engine — the visual core of the BMO AI Companion.  
> Renders a living face in pygame-ce, driven by MQTT events and a 15-state priority machine.

---

## Overview

`bmo-face` is a standalone Python service that:

- Renders BMO's face procedurally (no image assets) using **pygame-ce**
- Reacts to MQTT events from other services (voice, camera, AI, notifications)
- Exposes a **REST API** for direct state inspection and overrides
- Targets **30 FPS** (fallback 24 FPS on constrained hardware)
- Scales to any resolution — works on a 3.2" LCD and a 27" monitor equally

---

## Face States

| State       | Visual                                      | Trigger                              |
| ----------- | ------------------------------------------- | ------------------------------------ |
| `idle`      | Glow pulse + breathing pupils + blink       | Default / after all transitions      |
| `happy`     | Smile `:)` + squinted eyes                  | `bmo/system/state {"emotion":"happy"}` |
| `sad`       | Frown `:(` + blue tint + sad brows          | `bmo/voice/bt_disconnect`            |
| `stressed`  | X eyes 😵 + zigzag mouth + angry brows      | `bmo/system/state {"emotion":"stressed"}` |
| `hot`       | Squint + red tint + sweat drops             | `bmo/system/state {"emotion":"hot"}` |
| `worried`   | `/\` brows + darting eyes + open mouth      | `bmo/system/state {"emotion":"worried"}` |
| `thinking`  | Scanning pupils + 3 pulsing dots `...`      | Wake word detected                   |
| `listening` | Wide eyes + glow outline                    | `bmo/voice/listening_start`          |
| `speaking`  | Animated oscillating oval mouth             | `bmo/ai/speaking_start`              |
| `alert`     | Wide eyes + flashing border + text box      | `bmo/notify/event {"priority":"high"}` |
| `sleep`     | Dim overlay + closed eyes + floating z's   | 5 min after person leaves            |
| `wake`      | Eyes open from sleep                        | Person detected while sleeping       |
| `look_left` | Pupils shifted left                         | `bmo/camera/face_position {"x":<0.4}` |
| `look_right`| Pupils shifted right                        | `bmo/camera/face_position {"x">0.6}` |
| `blink`     | Brief eye close (overlay, any state)        | Random every 3–6 s                   |

---

## Setup

### Prerequisites

```bash
# Python 3.11+
python3 --version

# MQTT broker (required)
sudo apt install mosquitto mosquitto-clients
sudo systemctl enable --now mosquitto

# Verify broker
mosquitto_pub -t test -m hello &
mosquitto_sub -t test -C 1   # should print "hello"
```

### Install

```bash
cd services/bmo-face

# Option A — install script (recommended)
bash ../../scripts/install-face.sh

# Option B — manual
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Run

```bash
cd services/bmo-face
.venv/bin/python main.py
```

Service starts a pygame window and a Flask API on `http://127.0.0.1:5200`.

> **Tip:** Run MQTT broker first (`mosquitto -v` in another terminal), then start the face service.

### Run as systemd service (device)

```bash
# Copy and enable
sudo cp systemd/bmo-face.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bmo-face
sudo journalctl -u bmo-face -f   # watch logs
```

### Run tests

```bash
cd services/bmo-face
.venv/bin/python -m pytest tests/ -v
```

---

## REST API

Base URL: `http://127.0.0.1:5200`

```bash
# Health check
curl -s http://127.0.0.1:5200/health

# Get current state
curl -s http://127.0.0.1:5200/state

# Force state change
curl -s -X POST http://127.0.0.1:5200/state \
  -H "Content-Type: application/json" \
  -d '{"state": "happy"}'

# Set brightness (0.0 = off, 1.0 = full)
curl -s -X POST http://127.0.0.1:5200/brightness \
  -H "Content-Type: application/json" \
  -d '{"level": 0.7}'
```

---

## MQTT Payload Reference

All commands below assume `mosquitto_pub` is available and the broker is on `localhost:1883`.

### ── Basic States ──

```bash
# Idle (default — returns to this after all timeouts)
mosquitto_pub -t bmo/face/set_state -m '{"state":"idle"}'

# Sleep (dim overlay + closed eyes + z's)
mosquitto_pub -t bmo/face/set_state -m '{"state":"sleep"}'

# Wake (eyes open from sleep)
mosquitto_pub -t bmo/face/set_state -m '{"state":"wake"}'
```

### ── Emotions (auto-expire after 3–5 s) ──

```bash
# Happy :)  — smile + squinted eyes
mosquitto_pub -t bmo/system/state -m '{"emotion":"happy"}'

# Sad :(  — frown + blue tint + sad eyebrows
mosquitto_pub -t bmo/voice/bt_disconnect -m '{}'

# Stressed 😵  — X eyes + zigzag mouth + angry brows
mosquitto_pub -t bmo/system/state -m '{"emotion":"stressed"}'

# Hot  — red tint + sweat drops + squint
mosquitto_pub -t bmo/system/state -m '{"emotion":"hot"}'

# Worried  — /\ brows + darting eyes
mosquitto_pub -t bmo/system/state -m '{"emotion":"worried"}'
```

### ── Voice Pipeline ──

```bash
# Wake word detected → thinking (scanning pupils + pulsing dots)
mosquitto_pub -t bmo/voice/wake_word -m '{}'

# STT listening → wide eyes + glow (auto-expires 10 s)
mosquitto_pub -t bmo/voice/listening_start -m '{}'

# AI speaking (animated oval mouth — oscillates at 8 Hz)
mosquitto_pub -t bmo/ai/speaking_start -m '{"amplitude":[],"sample_rate_hz":10}'

# AI done speaking → back to idle
mosquitto_pub -t bmo/ai/speaking_end -m '{}'

# With amplitude envelope for lip-sync:
mosquitto_pub -t bmo/ai/speaking_start \
  -m '{"amplitude":[0.1,0.5,0.9,0.8,0.6,0.3,0.8,0.9,0.4,0.1],"sample_rate_hz":10}'
```

### ── Notifications ──

```bash
# High-priority alert (flashing border + title + message text box, holds 5 s)
mosquitto_pub -t bmo/notify/event \
  -m '{"priority":"high","title":"Door","message":"Someone at the front door"}'

mosquitto_pub -t bmo/notify/event \
  -m '{"priority":"high","title":"Meeting","message":"Meeting starts in 5 minutes"}'

mosquitto_pub -t bmo/notify/event \
  -m '{"priority":"high","title":"Timer","message":"Your 10 min timer is up"}'
```

### ── Camera Events ──

```bash
# Person detected (cancel sleep timer / wake from sleep)
mosquitto_pub -t bmo/camera/person_detected -m '{}'

# Person left (start 5-min countdown to sleep)
mosquitto_pub -t bmo/camera/person_left -m '{}'

# Face position — look left (x < 0.4)
mosquitto_pub -t bmo/camera/face_position -m '{"x":0.2}'

# Face position — look right (x > 0.6)
mosquitto_pub -t bmo/camera/face_position -m '{"x":0.8}'

# Face position — center (returns to idle pupils)
mosquitto_pub -t bmo/camera/face_position -m '{"x":0.5}'
```

### ── Direct Force (always works, even during SPEAKING/THINKING) ──

```bash
# Force any state by name — bypasses priority coalescing
mosquitto_pub -t bmo/face/set_state -m '{"state":"happy"}'
mosquitto_pub -t bmo/face/set_state -m '{"state":"sad"}'
mosquitto_pub -t bmo/face/set_state -m '{"state":"stressed"}'
mosquitto_pub -t bmo/face/set_state -m '{"state":"hot"}'
mosquitto_pub -t bmo/face/set_state -m '{"state":"worried"}'
mosquitto_pub -t bmo/face/set_state -m '{"state":"thinking"}'
mosquitto_pub -t bmo/face/set_state -m '{"state":"listening"}'
mosquitto_pub -t bmo/face/set_state -m '{"state":"speaking"}'
mosquitto_pub -t bmo/face/set_state -m '{"state":"alert"}'
mosquitto_pub -t bmo/face/set_state -m '{"state":"sleep"}'
mosquitto_pub -t bmo/face/set_state -m '{"state":"wake"}'
mosquitto_pub -t bmo/face/set_state -m '{"state":"idle"}'
```

### ── Brightness ──

```bash
# Dim to 40%
mosquitto_pub -t bmo/face/brightness -m '{"level":0.4}'

# Full brightness
mosquitto_pub -t bmo/face/brightness -m '{"level":1.0}'
```

### ── Subscribe to face events ──

```bash
# Watch all state transitions in real time
mosquitto_sub -t bmo/face/# -v

# Watch only state changes
mosquitto_sub -t bmo/face/state -v
```

---

## Complete Demo Sequence

Run these in order to tour all states (paste one line at a time, ~3 s apart):

```bash
mosquitto_pub -t bmo/face/set_state -m '{"state":"idle"}'
mosquitto_pub -t bmo/system/state -m '{"emotion":"happy"}'
mosquitto_pub -t bmo/system/state -m '{"emotion":"worried"}'
mosquitto_pub -t bmo/system/state -m '{"emotion":"stressed"}'
mosquitto_pub -t bmo/system/state -m '{"emotion":"hot"}'
mosquitto_pub -t bmo/voice/bt_disconnect -m '{}'
mosquitto_pub -t bmo/voice/wake_word -m '{}'
mosquitto_pub -t bmo/voice/listening_start -m '{}'
mosquitto_pub -t bmo/ai/speaking_start -m '{"amplitude":[]}'
mosquitto_pub -t bmo/ai/speaking_end -m '{}'
mosquitto_pub -t bmo/notify/event -m '{"priority":"high","title":"Alert","message":"This is a test notification"}'
mosquitto_pub -t bmo/camera/person_left -m '{}'
```

---

## Project Layout

```
services/bmo-face/
├── main.py               # Entry point — wires runtime + MQTT + API
├── renderer.py           # pygame-ce draw loop + FaceRuntime class
├── mqtt_client.py        # MQTT subscriber, connect_async, reconnect policy
├── api.py                # Flask REST API (/state, /health, /brightness)
├── config.py             # Config loader from config/bmo.yaml
├── requirements.txt      # Runtime + test dependencies
├── face/
│   ├── colors.py         # Palette constants + ScaleContext (scale helper)
│   ├── components.py     # build_face_layout() — geometry from screen size
│   ├── animations.py     # Pure math helpers: glow, breathing, speaking waveform
│   └── state_machine.py  # FaceStateMachine — 15 states, priority ladder, timers
├── tests/
│   ├── unit/             # State transitions, priority, sleep timer, scale math
│   ├── component/        # Blink, look direction, emotion timeouts, speaking fallback
│   └── integration/      # MQTT contract, REST API contract, queue plumbing
└── systemd/
    └── bmo-face.service  # systemd unit for auto-start on device
```

---

## Configuration (`config/bmo.yaml`)

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

## Troubleshooting

| Symptom | Fix |
| ------- | --- |
| `ConnectionRefusedError` on start | Start Mosquitto: `mosquitto -v` |
| Window doesn't open | Check `DISPLAY` env var is set; on Armbian: `export DISPLAY=:0` |
| `set_state` has no effect | Check MQTT broker is running; face service logs for errors |
| Stuck in speaking/thinking | Send `mosquitto_pub -t bmo/face/set_state -m '{"state":"idle"}'` — `set_state` always overrides |
| Low FPS on device | Set `fps_target: 24` in `config/bmo.yaml` |
