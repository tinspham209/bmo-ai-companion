# Milestone 4 — System Monitor Plan

**Status:** Software implementation and local automated/runtime checks are complete; Playbox acceptance is pending
**Priority:** Next service milestone after M3 software; M3 Playbox acceptance may continue in parallel
**Reference:** `docs/2026-07-22-01-bmo-ai-companion-specs.md` § Milestone 4
**Context:** `docs/2026-07-22-01-bmo-ai-companion-idea.md`, `docs/milestone/2/milestone-2-plan.md`, `docs/milestone/2/milestone-2-test_plan.md`, `docs/milestone/3/milestone-3-plan.md`, and `docs/milestone/3/test-plan.md`
**Validation order:** Test metric logic with fakes on the development host; verify Linux-specific providers and service operation on the FPT Playbox.
**Local verification (2026-09-29):** 64 M4 tests pass, including retained MQTT delivery/clearing against local Mosquitto and shutdown with the broker unavailable; 41 M2 face tests and 40 M3 camera tests pass. The monitor API was started locally, returned HTTP 200, bound to loopback, reported unsupported macOS sensors as degraded, and exited on SIGTERM in 0.6 seconds. Playbox acceptance remains pending.

## Goal

Build an independent, low-overhead service that samples the Playbox's system health, exposes current readings locally, and keeps BMO's emotion aligned with the specified CPU, temperature, and disk conditions over the existing MQTT broker.

## Deliverable

A standalone `bmo-monitor` service that:

- Collects CPU, RAM, temperature, root-filesystem free space, Wi-Fi link state, and Bluetooth adapter state.
- Publishes the existing `bmo/system/state` emotion contract consumed by `bmo-face`.
- Exposes localhost `GET /health` and `GET /status` endpoints for service health and current readings.
- Runs independently under systemd, reconnects to Mosquitto, and shuts down cleanly.

## Target and constraints

| Item | Target |
| --- | --- |
| Device | FPT Playbox S400, Amlogic S905X, Armbian |
| Runtime | Python 3.11+ |
| Communication | Existing local Mosquitto broker |
| Orchestration | Independent Linux systemd unit |
| Configuration | `monitor` section in the shared `config/bmo.yaml` |
| API | Localhost only; use port 5202 unless target-device validation finds a conflict |
| Resource use | Keep sampling and dependencies lightweight; measure CPU and RSS on target hardware |

## Scope

- Sample system-wide CPU utilization, RAM totals/availability, CPU/SoC temperature, and free bytes on `/`.
- Report whether a Wi-Fi interface is connected and whether a Bluetooth adapter is present and powered.
- Determine the current emotion using the confirmed M4 thresholds and precedence.
- Publish the retained current emotion and reassert it every 2 seconds using the existing MQTT topic and payload.
- Expose current readings and per-metric availability through a small localhost API.
- Handle unavailable sensors, broker outages, invalid configuration, and shutdown explicitly.

### Out of scope

- Changing thresholds or adding emotion rules for RAM, Wi-Fi, or Bluetooth.
- Publishing raw metric snapshots or introducing new MQTT topics in this milestone.
- Triggering `sad` or changing audio routing when Bluetooth disconnects; the voice service owns that interaction.
- Internet reachability checks, network configuration changes, or exposing SSIDs, MAC addresses, or paired-device names.
- Remote dashboards, alerts beyond the existing BMO face reaction, or a general monitoring framework.
- Fan control, which belongs to the hardware milestone.

## Metric and emotion contract

The specifications define collection for all six metrics but define emotion thresholds only for CPU, temperature, and disk. Those three conditions are the complete v1 emotion policy; RAM, Wi-Fi, and Bluetooth remain status telemetry until a later specification adds rules.

| Metric | v1 reading | Emotion rule |
| --- | --- | --- |
| CPU | System-wide utilization, 0–100% | `stressed` when **greater than 80%** |
| RAM | Total bytes, available bytes, and used percentage | Telemetry only; no emotion threshold is specified |
| Temperature | CPU/SoC thermal reading in °C | `hot` when **greater than 70°C** |
| Disk | Free bytes on `/` | `worried` when **less than 500,000,000 bytes** (decimal 500 MB) |
| Wi-Fi | Connected/disconnected state of the active wireless interface | Telemetry only; does not imply internet access |
| Bluetooth | Bluetooth adapter present/powered state | Telemetry only; voice service remains responsible for speaker-disconnect events |

The exact comparisons above preserve the specification's strict inequalities: CPU at 80%, temperature at 70°C, and disk free space at exactly 500,000,000 bytes do not trigger their respective emotions. The disk cutoff uses decimal MB. Per the confirmed M4 decision, `happy` means all three emotion-driving readings are available and none of their alert conditions is active; RAM, Wi-Fi, and Bluetooth are telemetry only and do not change emotion.

If an emotion-driving reading is unavailable, report that metric as unavailable and mark service health degraded. Do not treat a missing reading as nominal or publish a false `happy` state. Do not add an `unknown` emotion to the existing face contract.

Only one emotion is sent at a time. When multiple alert conditions are active, precedence is `hot > stressed > worried`. The selected emotion is published immediately on change and reasserted every 2 seconds while its readings remain valid. This keeps the state visible despite M2's 3-second `happy` and 5-second other emotion timeouts. A recovery to nominal publishes `happy`; if a required reading becomes unavailable, clear the retained state instead of publishing a false `happy`.

## Runtime flow

1. Load and validate the `monitor` section from `config/bmo.yaml`.
2. Discover supported local metric sources. On Linux, inspect the available thermal zones and wireless interfaces rather than assuming fixed sensor or interface names.
3. Sample metrics on a configurable interval using a monotonic clock for elapsed-time logic. Mark unsupported or failed readings unavailable and surface the failure in logs and `/status`.
4. Evaluate the emotion-driving readings with the exact v1 thresholds. Do not apply extra thresholds or hysteresis unless target testing demonstrates a need and the behavior is documented.
5. Connect to the existing local MQTT broker and publish `bmo/system/state` with the existing payload shape, `{"emotion":"happy|stressed|hot|worried"}`. Publish it retained at QoS 1 on initial evaluation and after broker reconnection, and reassert the current emotion every 2 seconds. Clear the retained value with an empty retained payload when a required reading becomes unavailable or the service shuts down. The face subscriber ignores the empty tombstone; do not add an `unknown` emotion or publish raw metrics.
6. Serve `GET /health` and `GET /status` on localhost. Keep the API responsive if an individual optional metric is unavailable; health must not claim full health when a required emotion-driving reading is unavailable.
7. On SIGTERM, stop sampling, stop MQTT, and close the API cleanly.

The topic name and JSON emotion schema remain unchanged. Retained delivery provides the current state to a late-starting face service; periodic reassertion keeps persistent monitor conditions visible. Empty retained tombstones clear stale state without expanding the emotion schema.

## Proposed service layout

```text
services/bmo-monitor/
├── main.py                 # Service entry point and lifecycle
├── metrics.py              # Host metric providers and availability
├── state.py                # Threshold evaluation and emotion selection
├── mqtt_client.py          # State publishing and reconnect
├── api.py                  # Local /health and /status endpoints
├── config.py               # monitor section from config/bmo.yaml
├── requirements.txt
├── README.md
├── systemd/
│   └── bmo-monitor.service
└── tests/
    ├── unit/
    ├── component/
    └── integration/
```

Keep metric collection separate from emotion selection so unit tests can inject readings without depending on Playbox hardware. Use the lightest reliable local providers available on Armbian; do not add a daemon, external service, or heavy monitoring stack.

## Configuration proposal

Add a `monitor` section to the existing shared configuration; do not create another general-purpose config file.

```yaml
monitor:
  sample_interval_seconds: 5
  emotion_reassert_interval_seconds: 2
  cpu_stress_percent: 80
  temperature_hot_c: 70
  disk_worried_free_bytes: 500000000
  disk_path: /
  api_port: 5202
  mqtt_broker: localhost
  mqtt_port: 1883
  wifi_interface: auto
```

The three thresholds, decimal disk units, and 2-second reassert interval are fixed M4 decisions. Keep the sample interval and interface selection validated. Do not add device identifiers or credentials to this config.

## Confirmed decisions and target assumptions

### Decisions confirmed before implementation

- Disk cutoff is decimal 500 MB (`500,000,000` bytes).
- Simultaneous-alert precedence is `hot > stressed > worried`.
- `happy` depends only on valid, nominal CPU, temperature, and disk readings. RAM, Wi-Fi, and Bluetooth remain telemetry only.
- Emotion state is retained, reasserted every 2 seconds, and cleared when an emotion-driving reading becomes unavailable.
- Bluetooth collection means adapter presence/power only; voice owns speaker-disconnect behavior.
- `/health` returns HTTP 200 with `{"status":"healthy"}` or `{"status":"degraded"}`.
- The target resource profile is one hour; RSS growth must be at most 20% from the initial steady-state baseline. Record CPU without an additional CPU cap.

### Target assumptions to validate

- The Playbox exposes a trustworthy CPU/SoC temperature reading through a local Linux interface.
- The selected root filesystem `/` is the correct disk volume for the 500 MB warning.
- A 5-second initial sampling interval is responsive enough for the face and adds negligible load.
- Wi-Fi interface discovery can identify the active wireless interface without hard-coding `wlan0`.
- Bluetooth adapter status can be read from the installed local `bluetoothctl` command without exposing device identifiers.
- The M2 subscriber accepts retained emotion messages and ignores empty retained tombstones.

### Over-engineering removed or constrained

- No new MQTT telemetry topic, database, history store, dashboard, or remote API.
- No connectivity probes to public hosts and no automatic Wi-Fi/Bluetooth reconfiguration.
- No raw sensor data in MQTT; full readings are available only through localhost `/status`.
- No RAM/network/Bluetooth emotion rules, fan control, or speaker fallback in M4.
- No generic plugin framework; keep only small injectable metric providers needed for tests and host differences.

## Revised implementation plan

### Phase 1 — Provider and configuration foundation

- [ ] **T0** Inspect the Playbox's Armbian interfaces for CPU counters, memory, root disk space, thermal zones, wireless link, and Bluetooth adapter state. Record available sources and failures; do not infer temperature from unrelated sensors.
- [x] **T1** Create the service skeleton and validated `monitor` configuration in `config/bmo.yaml`, including the API port, sample/reassert intervals, fixed thresholds, disk path, and interface selection.
- [x] **T2** Implement injectable metric providers. Normalize units, include metric availability, and report provider errors explicitly.

### Phase 2 — Metric sampling and emotion policy

- [x] **T3** Collect system-wide CPU utilization from successive samples; avoid blocking the entire service for each CPU reading.
- [x] **T4** Collect RAM, CPU/SoC temperature, root-filesystem free bytes, Wi-Fi link state, and Bluetooth adapter state.
- [x] **T5** Implement pure emotion selection for strict CPU, temperature, and disk thresholds; cover nominal and simultaneous-alert conditions using the agreed precedence.
- [x] **T6** Keep unsupported readings out of the nominal result; expose per-metric availability and prevent missing data from generating `happy`.

### Phase 3 — MQTT and local API

- [x] **T7** Publish only the existing `bmo/system/state` schema as retained state; reassert every 2 seconds and clear the retained value when required readings are unavailable.
- [x] **T8** Implement loopback `GET /health` and `GET /status` with metric values, units, per-metric availability, selected emotion, and last successful sample time. Do not expose SSIDs, MAC addresses, or paired-device names.
- [x] **T9** Test broker outage/reconnect without blocking or terminating metric collection; surface publish failures.

### Phase 4 — Lifecycle, deployment, and acceptance

- [x] **T10** Add SIGTERM cleanup, `scripts/install-monitor.sh`, and `services/bmo-monitor/systemd/bmo-monitor.service`, following repository deployment conventions.
- [x] **T11** Document local development, Linux installation, API checks, MQTT observation, and troubleshooting in the service README.
- [ ] **T12** Complete development-host tests and target Playbox acceptance; record sensor sources, resource use, and any unresolved deviations.

## Test plan

### Unit tests

- Valid and invalid monitor configuration, including zero/negative intervals and invalid thresholds.
- CPU utilization calculation from deterministic successive counter samples.
- RAM, disk byte/unit conversion, temperature conversion, and unavailable/invalid provider values.
- Wi-Fi and Bluetooth state normalization without exposing identifiers.
- Exact threshold boundaries: 80% CPU, 70°C, and 500,000,000 bytes are nominal; values strictly beyond each threshold trigger the specified emotion.
- All-nominal result requires valid CPU, temperature, and disk readings.
- Missing required readings never produce a false `happy` result.
- Simultaneous alert conditions follow the approved precedence and do not produce nondeterministic results.

### Component and integration tests

- `/health` and `/status` report accurate service and per-metric availability; one missing optional network metric does not crash the service.
- MQTT messages use only `bmo/system/state` and exactly `{"emotion":"..."}`; no raw readings or new topic are emitted.
- Initial/reconnect publication is retained at QoS 1; late subscribers receive it and a tombstone clears stale state.
- The current emotion is reasserted every 2 seconds and remains visible beyond M2's transient timeout; recovery changes the retained emotion.
- SIGTERM exits within a bounded interval and closes API/MQTT resources.
- Unit/component tests run without hardware or a broker using fake providers and a fake MQTT client; the retained-state integration test exercises local Mosquitto when available.

**Test command once the service exists:** from `services/bmo-monitor`, `.venv/bin/python -m pytest tests/ -v`.

## Acceptance criteria and traceability

| ID | Acceptance criterion | Covered by |
| --- | --- | --- |
| AC-01 | CPU, RAM, temperature, root free space, Wi-Fi, and Bluetooth are reported with correct units and explicit availability | T0–T4, provider tests, Playbox `/status` check |
| AC-02 | Strict CPU >80%, temperature >70°C, and disk free <500 MB conditions map to the specified emotions; nominal valid readings map to `happy` | T5–T6, threshold unit tests |
| AC-03 | Missing CPU/temperature/disk readings are not treated as nominal; health and status expose degraded/unavailable readings | T2/T6/T8, failure tests |
| AC-04 | M2 receives the unchanged retained `bmo/system/state` payload on initial evaluation, late subscription, reassertion, and broker recovery | T7/T9, MQTT contract, late-subscriber, and restart checks |
| AC-05 | Local API exposes current readings without remote access or device identifiers | T8, API contract and Playbox boundary check |
| AC-06 | Service starts under systemd, survives broker restart, and releases resources on SIGTERM | T9–T10, Playbox lifecycle checks |
| AC-07 | Target CPU/RSS and sensor sources are recorded for one hour; RSS growth is at most 20% from the initial steady-state baseline | T0/T12, target acceptance record |

### Stage A — Development host and isolated tests

- [x] Run the full pytest suite using fake metric providers and fake MQTT; the live retained-state check also passes against local Mosquitto.
- [x] Exercise every threshold boundary, unavailable sensor, malformed config, broker outage, and termination case.
- [x] Run the local API/MQTT smoke checks; verify loopback binding and degraded status for unsupported host sensors.
- [x] Treat host readings as development-only; macOS results do not validate Armbian thermal, wireless, Bluetooth, or disk providers.

### Stage B — FPT Playbox S400 / Armbian

- [ ] Confirm the exact thermal source and units against a local OS reading; verify it is the CPU/SoC sensor.
- [ ] Confirm root free bytes, active Wi-Fi interface link state, and BlueZ adapter state without interrupting the broker or remote access.
- [ ] Install/enable the systemd unit, cold-boot, and verify the service becomes healthy and publishes the current emotion.
- [ ] Compare `/status` to local read-only system tools; verify CPU, RAM, temperature, disk, Wi-Fi, and Bluetooth fields are plausible and unavailable readings are explicit.
- [ ] Observe MQTT emotion events and verify that normal readings map to `happy`; validate abnormal thresholds through unit/fake-provider tests rather than deliberately overheating the board, exhausting storage, or sustaining unsafe CPU load.
- [ ] Restart Mosquitto and verify sampling continues and the retained current emotion is published after reconnection; restart `bmo-face` and verify it consumes the retained state.
- [ ] Send SIGTERM and verify a clean exit; reboot and verify systemd starts the monitor without a logged-in shell.
- [ ] Record CPU/RSS and sensor availability during a one-hour run; confirm RSS growth is at most 20% from the initial steady-state baseline.

## Confirmed decisions

| Decision | Confirmed behavior | Status |
| --- | --- | --- |
| Disk threshold units | 500,000,000 bytes (decimal 500 MB) | Confirmed |
| Simultaneous emotion precedence | `hot > stressed > worried` | Confirmed |
| Meaning of `happy` | CPU/temp/disk valid and nominal; RAM/Wi-Fi/Bluetooth telemetry only | Confirmed |
| Emotion lifetime | Reassert selected emotion every 2 seconds while readings are valid | Confirmed |
| Late face startup | Retained current state; clear retained value on invalid required readings or graceful shutdown | Confirmed |
| Health response | HTTP 200 with `status=healthy` or `status=degraded` | Confirmed |
| Bluetooth | Adapter present/powered only | Confirmed |
| Resource profile | One hour; RSS growth ≤20% from baseline; record CPU | Confirmed |
| Linux sensor/provider availability | Discover thermal zone, Wi-Fi interface, and Bluetooth adapter on Armbian | Pending Playbox |
