# Milestone 4 — System Monitor Test Plan

**Status:** Implementation and local automated/runtime checks are complete; target Playbox acceptance remains pending
**Scope source:** `docs/milestone/4/milestone-4-plan.md`
**Requirements source:** `docs/2026-07-22-01-bmo-ai-companion-specs.md` § Milestone 4
**Related contracts:** `docs/milestone/2/milestone-2-plan.md` and `docs/milestone/2/milestone-2-test_plan.md`
**Validation order:** Static/isolated → local runtime and MQTT → system and termination on the FPT Playbox

**Latest local run (2026-09-29):** 64 M4 tests passed, including retained MQTT delivery/clearing against local Mosquitto, sustained emotion integration, and bounded shutdown without a broker; 41 M2 face tests passed, including late retained-state consumption; 40 M3 camera tests passed. The monitor API was started locally, returned HTTP 200 for `/health` and `/status`, bound only to `127.0.0.1`, reported unsupported macOS sensors as degraded, and exited on SIGTERM in 0.6 seconds. Playbox-specific checks have not run.

This document defines tests and acceptance procedures only; it does not implement tests or change production behavior. Unit and component tests use fake providers and MQTT clients; the live retained-state integration test uses local Mosquitto and skips if unavailable. Host runtime checks are development evidence only; Linux metric providers and systemd acceptance must be verified on the Playbox.

## 1. Test strategy and command catalog

Use a TDD loop for each behavior:

1. Write a failing test for a metric, decision, API, MQTT, or lifecycle contract.
2. Implement the smallest behavior that satisfies the test.
3. Run the affected tests, then the complete service suite before target acceptance.

| Purpose | Command or pattern | Notes |
| --- | --- | --- |
| Automated tests | From `services/bmo-monitor`: `.venv/bin/python -m pytest tests/ -v` | Unit tests use fakes; live retained-state test requires local Mosquitto and skips if unavailable |
| Observe emotion events | `mosquitto_sub -t bmo/system/state -v` | Payload must remain the M2 emotion contract |
| Check health | `curl -s http://127.0.0.1:5202/health` | HTTP 200 with `status=healthy` or `status=degraded` |
| Check readings | `curl -s http://127.0.0.1:5202/status` | Verify units, availability, and privacy boundary |
| Inspect Linux service | `systemctl status bmo-monitor.service` and `journalctl -u bmo-monitor.service` | Playbox only; use repository installation instructions once available |
| Compare host readings | Read-only OS tools available on the target | Discover appropriate tools and thermal/interface sources during provider inspection; do not assume fixed sensor names |

No stress/benchmark tool, numerical coverage target, or external monitoring stack is required by the current plan. The target resource profile is one hour with RSS growth no more than 20% from the initial steady-state baseline; record CPU without an additional cap.

## 2. Data flow and privacy boundary

Expected path:

```text
Local Linux counters, thermal zones, filesystem, network and BlueZ
  → in-memory metric readings and availability
  → emotion selector
  → localhost /health and /status
  → Mosquitto: bmo/system/state {"emotion":"..."}
  → bmo-face
```

Only the emotion payload is published to MQTT. Raw CPU, RAM, temperature, disk, Wi-Fi, and Bluetooth readings stay in the local service API; do not publish them, persist history, or expose SSIDs, MAC addresses, or paired-device names. Bind the API to loopback and verify it is not reachable through the Playbox's non-loopback interfaces.

## 3. Acceptance-criterion traceability

| Plan criterion | Tests | Runtime/device evidence |
| --- | --- | --- |
| **AC-01 Metrics:** collect CPU, RAM, temperature, root free space, Wi-Fi, and Bluetooth with correct units and explicit availability | TP-001–TP-006, TP-020 | Compare `/status` with local read-only OS readings; confirm provider and availability for each metric |
| **AC-02 Emotion mapping:** strict CPU >80%, temperature >70°C, disk free <500 MB; nominal → `happy` | TP-010–TP-014 | Observe a normal-state event; exercise abnormal thresholds with fake readings, not hazardous device conditions |
| **AC-03 Missing data:** missing emotion-driving readings do not count as nominal and are reported as degraded/unavailable | TP-020–TP-021 | Simulate missing providers and confirm `/health` and `/status` report the agreed degraded contract |
| **AC-04 MQTT:** unchanged retained emotion payload on initial evaluation, late subscription, reassertion, and broker recovery | TP-022–TP-025 | Subscribe to the topic, restart Mosquitto and `bmo-face`, and verify the current state is delivered |
| **AC-05 API boundary:** local readings are available without remote access or device identifiers | TP-021 | Verify loopback access, non-loopback bind behavior, and response redaction on the Playbox |
| **AC-06 Lifecycle:** systemd startup, broker recovery, and bounded SIGTERM cleanup | TP-030–TP-032 | Cold boot, broker restart, service stop, and reboot on the Playbox |
| **AC-07 Resources:** record CPU/RSS and sensor sources for one hour; RSS growth ≤20% | TP-040 | Record target measurements and compare RSS to the initial steady-state baseline |

## 4. Layer 1 — Static and isolated tests

These tests must not require Linux sensors, a physical Playbox, Mosquitto, or systemd. Inject metric values, clocks, and MQTT behavior.

### Unit tests

- **TP-001 Configuration validation**
  - Valid monitor configuration loads all configured thresholds, sample interval, disk path, API port, MQTT host/port, and Wi-Fi selection.
  - Missing or invalid required values (zero/negative intervals, out-of-range thresholds, invalid ports, malformed interface selection) fail explicitly.

- **TP-002 CPU sampling**
  - Given deterministic successive counter samples, calculate system-wide utilization in the range 0–100%.
  - Cover first sample, zero elapsed time, counter reset/decrease, and invalid counters; no division errors or fabricated nominal readings.

- **TP-003 RAM sampling**
  - Return total bytes, available bytes, and used percentage with stable units.
  - Reject impossible totals/availability and report the reading unavailable rather than returning misleading values.

- **TP-004 Temperature sampling**
  - Convert supported sensor units to °C correctly, including Linux millidegree input.
  - Cover multiple candidate zones, missing sensor, unreadable data, and implausible values. The chosen CPU/SoC source must be explicit; do not silently substitute another sensor.

- **TP-005 Root disk sampling**
  - Measure free bytes on the configured root path and report filesystem errors explicitly.
  - Test exact boundaries at 499,999,999, 500,000,000, and 500,000,001 bytes; only the first value triggers `worried`.

- **TP-006 Wi-Fi and Bluetooth readings**
  - Normalize wireless interface/link and Bluetooth adapter present/powered states.
  - Cover missing interface, disconnected link, absent adapter, BlueZ unavailable, and unknown state.
  - Do not include speaker connectivity in the M4 adapter-state contract; M5 owns speaker connection events.

### Emotion selection tests

- **TP-010 CPU threshold:** exactly 80% is not `stressed`; a value strictly above 80% selects `stressed`.
- **TP-011 Temperature threshold:** exactly 70°C is not `hot`; a value strictly above 70°C selects `hot`.
- **TP-012 Disk threshold:** exactly 500,000,000 bytes is not `worried`; one byte below selects `worried`; one byte above remains nominal.
- **TP-013 Nominal state:** valid CPU, temperature, and disk readings with no active alert select `happy`. RAM, Wi-Fi, and Bluetooth do not affect this M4 emotion decision.
- **TP-014 Concurrent conditions and recovery:** `hot` wins over `stressed` and `worried`; `stressed` wins over `worried`. Clearing the winning condition selects the next active emotion or `happy`.
- Verify the current emotion is published immediately on change and reasserted every 2 seconds while all emotion-driving readings are valid.

### Failure and API tests

- **TP-020 Missing/stale metric behavior**
  - Each emotion-driving metric (CPU, temperature, disk) becomes unavailable independently and at startup.
  - Missing data never produces a new `happy` result.
  - Loss of a required reading clears retained state; recovery to valid readings publishes the newly selected emotion.
  - Health returns HTTP 200 with `{"status":"degraded"}` when CPU, temperature, or disk is unavailable; optional metric failures do not degrade health.

- **TP-021 `/health` and `/status` contract**
  - `/health` returns HTTP 200 with `{"status":"healthy"}` or `{"status":"degraded"}`; status includes current values, units, per-metric availability, selected emotion, and last successful sample time.
  - Verify no SSID, MAC address, paired-device name, raw MQTT metric payload, or historical store appears.
  - Verify API binding is loopback-only; on target, confirm requests through a non-loopback address are unavailable.
  - `/status` returns HTTP 200 with the fixed metric keys `cpu`, `ram`, `temperature`, `disk`, `wifi`, and `bluetooth`.

## 5. Layer 2 — MQTT and local runtime tests

Use local Mosquitto and the running M2 face service when available. Keep threshold simulation in injected/fake providers; do not add a production endpoint that lets callers force system readings.

- **TP-022 MQTT schema**
  - Every publish uses `bmo/system/state` and exactly one allowed payload shape: `{"emotion":"happy"}`, `{"emotion":"stressed"}`, `{"emotion":"hot"}`, or `{"emotion":"worried"}`.
  - Publish at QoS 1 with the retain flag set; reject extra fields, invalid emotion names, and raw metric data.
  - Confirm unchanged valid readings are reasserted no faster than every 2 seconds.

- **TP-023 Initial state and broker recovery**
  - Start with valid readings and verify the current emotion is published after initial evaluation.
  - Stop/restart Mosquitto; confirm metric sampling continues, publishing recovers, and the retained current emotion is re-published.
  - Verify broker outage does not block `/health` or `/status`; errors remain visible.

- **TP-024 Independent face/monitor startup**
  - Publish a retained emotion, then start a new MQTT subscriber to `bmo/system/state`.
  - Verify the late subscriber receives the retained current emotion; the M2 `FaceMqttClient` integration test must queue the valid emotion event.
  - Publish an empty retained tombstone and verify a later subscriber receives no stale emotion; M2 ignores the empty payload.

- **TP-025 Emotion lifetime and sustained condition**
  - Keep a valid abnormal fake reading active beyond M2's timeout (3 seconds for `happy`, 5 seconds for other mapped emotions).
  - Verify M4 reasserts the retained state every 2 seconds and M2 remains in the mapped state while the condition persists.
  - Clear the condition and verify the newly selected emotion is published and retained.

- **M2 integration**
  - Publish representative monitor events through the actual broker and verify the M2 face service accepts each permitted emotion payload.
  - Check the face state promptly after publication, across a sustained condition, and after recovery; MQTT observation alone does not prove face integration.

- **TP-030 SIGTERM lifecycle**
  - Run the service with API and MQTT active, then send SIGTERM.
  - Verify the process exits within 5 seconds, the API listener closes, MQTT clears retained state when connected, and no worker remains. The local macOS smoke run exited in 0.6 seconds and closed the listener.
  - Repeat while the broker is unavailable; the monitor still exits cleanly.

## 6. Layer 3 — System and Playbox acceptance

Run after isolated tests pass. MacBook host readings do not prove Linux temperature, Wi-Fi, Bluetooth, filesystem, or systemd behavior.

| Procedure | Expected result | Mode |
| --- | --- | --- |
| Inspect available CPU, memory, thermal, root filesystem, wireless, and BlueZ sources | Each selected provider is identified; unsupported readings are explicit | Human-assisted on Playbox |
| Compare `/status` readings with available local OS read-only readings | Values and units are plausible; root disk is `/`; selected temperature source is CPU/SoC | Human-assisted on Playbox |
| Check wireless and Bluetooth status while connected | API matches actual link/adapter state and does not reveal identifiers | Human-assisted; do not disable Wi-Fi if it would interrupt remote access |
| **TP-031** Install and enable `bmo-monitor.service`, then cold boot | Service starts without an interactive shell, reports truthful health, and publishes its retained initial emotion | Human-only on Playbox |
| **TP-032** Restart Mosquitto while monitoring | Sampling continues and the retained current emotion is republished after reconnect | Playbox integration |
| Restart `bmo-face` while monitor stays running | The retained current emotion is delivered without a metric transition | Playbox integration |
| Send SIGTERM during normal sampling and during broker outage | Service stops within 5 seconds and closes API/MQTT resources without hanging | Automated TP-030 plus Playbox check |
| Observe a normal system state | `/status` agrees with the OS and the approved nominal emotion is published | Human-assisted on Playbox |
| Validate abnormal thresholds | Use fake-provider tests for CPU, temperature, and disk boundaries; do not deliberately overheat the board, exhaust storage, or sustain unsafe CPU load | Automated fakes; no hazardous hardware stress |
| Run a one-hour service profile | Record CPU and sensor availability; RSS growth is at most 20% from the initial steady-state baseline | Human-only on Playbox |

### TP-040 One-hour resource profile

- After five minutes at steady state, record the monitor process RSS baseline and CPU usage.
- Continue sampling RSS at least every five minutes for one hour while checking that `/health` remains available and systemd does not restart the service.
- Pass when peak RSS is no more than 120% of the baseline. Record average/peak CPU and sensor availability; CPU is observational and has no separate cap.

## 7. Confirmed test contract

| Decision | Expected behavior |
| --- | --- |
| Disk threshold | Decimal 500 MB = 500,000,000 bytes |
| Simultaneous emotion precedence | `hot > stressed > worried` |
| Meaning of `happy` | CPU, temperature, and disk readings are available and nominal; RAM/Wi-Fi/Bluetooth do not affect emotion |
| Emotion lifetime | Retained emotion is reasserted every 2 seconds while required readings are valid |
| Late face startup | Retained current state is delivered to a new subscriber; an empty tombstone clears stale state |
| Degraded health | HTTP 200 with `{"status":"degraded"}` for missing required metrics; optional metric failures do not degrade health |
| Bluetooth scope | Adapter present/powered only |
| Resource profile | One hour; RSS growth ≤20% from initial steady-state baseline; record CPU |

The target sensor/provider inventory and one-hour resource profile still require the physical Playbox. Keep those acceptance items unchecked until the device results are recorded.

## 8. Regression and exit criteria

After any implementation change, rerun the full service pytest command and repeat affected MQTT/API checks. Protect these cross-service behaviors:

- M2 continues to receive only its documented `bmo/system/state` emotion payload.
- Monitor broker failure does not stop metric sampling or produce a false healthy state.
- A missing CPU, temperature, or disk reading cannot be interpreted as nominal.
- API remains loopback-only and does not expose network/device identifiers.
- Independent monitor and face service starts/restarts do not leave the face indefinitely stale once the current-state contract is finalized.

M4 is ready for sign-off only when AC-01 through AC-07 have passing automated or documented device results and the one-hour Playbox resource profile passes. Local macOS results do not satisfy target-only sensor, systemd, or performance checks.
