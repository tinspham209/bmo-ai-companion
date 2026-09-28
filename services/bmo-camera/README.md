# bmo-camera

> On-device face presence, face-position, and motion events for the BMO AI Companion.

The service processes frames in memory with OpenCV and publishes JSON metadata to the local Mosquitto broker. It does not preview, record, save, or upload camera frames.

## Development on macOS

Use the MacBook built-in camera for development. Grant camera access to the terminal/Python host in **System Settings → Privacy & Security → Camera** before testing; if access was previously denied, enable it there and restart the service. Camera index and backend are configurable in `config/bmo.yaml`.

```bash
cd services/bmo-camera
bash ../../scripts/install-camera.sh
.venv/bin/python main.py
```

The service binds its status API to `http://127.0.0.1:5201`. A running `bmo-face` service and local Mosquitto broker are used for end-to-end state and event checks.

The shared `camera.active_fps` setting currently requests 30 FPS. Set it to `auto` if the backend's native mode should be left untouched; tune the numeric value to the camera's supported active mode. During `sleep`, the service requests 5 FPS and independently caps analysis at 5 FPS. Check `/status`'s `capture_fps_request_applied` field: a backend may keep capturing at its native rate even though analysis is capped.

### Existing catalog checks

```bash
# Observe camera events
mosquitto_sub -t bmo/camera/# -v

# Check health and metadata status; neither endpoint returns frames
curl -s http://127.0.0.1:5201/health
curl -s http://127.0.0.1:5201/status

# Put the face to sleep/wake to verify camera processing-rate changes
mosquitto_pub -t bmo/face/set_state -m '{"state":"sleep"}'
mosquitto_pub -t bmo/face/set_state -m '{"state":"idle"}'
```

Run the automated suite with the existing test-runner pattern:

```bash
.venv/bin/python -m pytest tests/ -v
```

Stop the foreground service with Ctrl+C. Camera images are not written to disk or published.

## Playbox deployment (later target validation)

The target camera is the Aukey webcam recorded in the hardware inventory as PC-3 FullHD (also referred to as WC-3); confirm the exact model when connecting it. Check camera permissions and available `/dev/video*` devices on Armbian, then tune the camera section in `config/bmo.yaml`.

Install dependencies from the repository root:

```bash
bash scripts/install-camera.sh
```

Install and enable `systemd/bmo-camera.service` from this service directory:

```bash
sudo cp systemd/bmo-camera.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bmo-camera
```

Confirm `/health`, `/status`, MQTT events, sleep-rate behavior, and camera release on shutdown. The MacBook test does not certify S905X performance or systemd startup.

## MQTT behavior

The service subscribes to `bmo/face/state`, synchronizes initial state through `bmo-face`'s localhost `/state` endpoint, and publishes:

- `bmo/camera/person_detected` and `bmo/camera/person_left` with `{}`.
- `bmo/camera/face_position` with `{"x": 0.0..1.0}`.
- `bmo/camera/motion` and `bmo/camera/no_motion` with `{}`.

`PERSON_LEFT` follows 10 seconds of continuous face absence. Position heartbeats keep the M2 look state active while a face remains visible. The `NO_MOTION` timeout and motion threshold are configurable starting values and must be tuned during acceptance.
