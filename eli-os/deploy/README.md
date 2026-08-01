# Eli OS Gateway — Deployment

`ARCHITECTURE.md` §8 (the home-scale deployment view) made runnable: the
gateway (`../gateway/gateway.py`) as a *managed service* instead of a
hand-started process. Two targets, both zero-dependency:

| Target | Artifact | Manager |
|--------|----------|---------|
| Dominion home box (Windows) | `ELI_OS_GATEWAY.bat` + `brayai_service.json` | BRA.Y.AI runtime (port 9999) |
| Small VPS (Linux) | `eli-os-gateway.service` | systemd |

The service is the same in both: `python gateway.py serve --port 8484`,
bound to **127.0.0.1 only**, health-checked at `GET /healthz` (returns the
loaded policy version + current top-tier share).

## Environment

Set via the launcher / unit — never committed (`.gitignore` guards `.env`):

| Var | Purpose | Default |
|-----|---------|---------|
| `ANTHROPIC_API_KEY` | Messages API auth (only needed for `/complete`) | — |
| `ELI_MODEL_TREE` | routing policy JSON | `../routing/model_tree.json` |
| `ELI_TELEMETRY` | JSONL log of record (dashboard + review read this) | `./telemetry.jsonl` |

## A. Home box — register with BRA.Y.AI

1. **Launcher.** `ELI_OS_GATEWAY.bat` follows the `BRAYAI.bat` convention:
   loads `BrightValley\eli\.env`, points `ELI_TELEMETRY` at
   `brayai\logs\eli_os_telemetry.jsonl`, and serves on 8484. Run it directly
   to smoke-test before registering.
2. **Register the service.** Add the `brayai_service.json` entry to
   `brayai/config.json` (adapt key names to the installed schema), and add
   this row to `SERVICE_CONFIGS` in the admin skill's `service_control.py`
   so the no-runtime path can manage it too:

   ```python
   "eli_os_gateway": ("python gateway.py serve --port 8484", 8484, "/healthz"),
   ```

3. **Drive it** like any other service:

   ```text
   python runtime.py start eli_os_gateway
   curl -X POST http://localhost:9999/api/services/eli_os_gateway/restart
   curl http://localhost:8484/healthz
   ```

Port **8484** is new — no collision with HomeBase (8000), BRA.Y.AI (9999),
or the 8001–8004 service_control range.

## B. VPS — systemd

```sh
sudo cp eli-os-gateway.service /etc/systemd/system/
# edit WorkingDirectory to where this repo is cloned
sudo install -d -m 700 /etc/eli-os
printf 'ANTHROPIC_API_KEY=%s\n' "$KEY" | sudo tee /etc/eli-os/gateway.env >/dev/null
sudo chmod 600 /etc/eli-os/gateway.env
sudo systemctl daemon-reload && sudo systemctl enable --now eli-os-gateway
curl -s http://127.0.0.1:8484/healthz
```

The unit is hardened (`ProtectSystem=strict`, `ProtectHome=true`,
`NoNewPrivileges=true`); telemetry goes to the unit's `StateDirectory`
(`/var/lib/eli-os/telemetry.jsonl`) — the only writable path it needs.

## Acceptance (roadmap Phase 7)

- The gateway starts and restarts **under the service manager**, not by hand.
- `GET /healthz` → 200 with the policy version the routing tests pin.
- Telemetry accumulates at the configured `ELI_TELEMETRY` path, and
  `observability/dashboard.py` renders from it unchanged.

## Exposure rule

The bind is loopback-only by design. Nothing here opens a LAN or public
port; if a client on another machine ever needs the gateway, that is a
reverse-proxy decision to be made deliberately (auth + TLS), not a default
— per the guardrails stance in `../observability/telemetry_spec.md`.
