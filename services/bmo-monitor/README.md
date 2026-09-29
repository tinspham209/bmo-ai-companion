# bmo-monitor

System statistics and emotion mapping service for the BMO AI Companion. The service collects host metrics locally, exposes status through a loopback-only API, and publishes the current emotion to the local Mosquitto broker.

## Development and installation

Install dependencies from the repository root:

```bash
bash scripts/install-monitor.sh
```

Run the service from its directory:

```bash
cd services/bmo-monitor
.venv/bin/python main.py
```

The API binds to `127.0.0.1:5202`:

```bash
curl -s http://127.0.0.1:5202/health
curl -s http://127.0.0.1:5202/status
```

Run automated tests:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Measurements and emotions

The service reports CPU utilization, RAM totals/availability, CPU/SoC temperature, free bytes on `/`, Wi-Fi link state, and Bluetooth adapter presence/power state. It publishes only `bmo/system/state` with `{"emotion":"happy|stressed|hot|worried"}`. Emotion thresholds are fixed to CPU >80%, temperature >70°C, and root free space <500,000,000 bytes. Simultaneous alert priority is `hot > stressed > worried`; `happy` applies when the three threshold inputs are valid and nominal. Other collected metrics are telemetry only.

The current emotion is retained and reasserted every two seconds so a late-starting face service receives it and M2's transient face timeout does not hide an ongoing system condition. If a required metric becomes unavailable, the service clears the retained state and reports degraded health rather than publishing a false `happy`.

`/health` returns HTTP 200 with `{"status":"healthy"}` or `{"status":"degraded"}`. `/status` includes metric values, units, availability, the selected emotion, and last sample time. No SSID, MAC address, or paired-device name is returned.

## Playbox validation

The target is the FPT Playbox S400 running Armbian. Confirm the CPU/SoC thermal zone, wireless interface, and local `bluetoothctl` provider on the target. Unsupported readings are reported unavailable; they are not substituted with nominal values.

Install and enable the systemd unit from this service directory:

```bash
sudo cp systemd/bmo-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bmo-monitor
```

Check `/health`, `/status`, the retained `bmo/system/state` event, broker restart recovery, SIGTERM cleanup, and independent face/monitor startup. For the one-hour resource profile, record CPU/RSS and verify RSS growth is at most 20% from the initial steady-state baseline. Do not force unsafe CPU load, overheat the device, or exhaust disk space to test thresholds; automated tests cover those boundaries with synthetic readings.
