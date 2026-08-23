# Local API (v1.5)

ITOps Hub ships a local FastAPI service that shares the exact service layer
the desktop UI uses — no duplicated business logic by construction.

## Running

**Embedded (opt-in):** enable *Settings → Local API → Enable local FastAPI
service* and restart the app. The server runs on a daemon thread.

**Standalone:**

```bash
python -m app.api [--host 127.0.0.1] [--port 8756]
```

Defaults come from Settings (`api.host`, `api.port`; loopback only).
The startup banner prints the session token; the `api-token` file in the
data directory (`%LOCALAPPDATA%\ITOpsHub`) is written whenever the API
starts — standalone **or** embedded via Settings.

Interactive OpenAPI documentation: **http://127.0.0.1:8756/docs**

## Security model (AD-010)

1. **Loopback binding by default.** Binding elsewhere requires passing
   `--host` explicitly (or editing settings) — a deliberate user decision
   that logs a warning.
2. **Per-session token.** Generated with `secrets.token_urlsafe(32)` on every
   application start. Required in the `X-API-Token` header for every
   `/api/*` route except `/api/health`. Comparison uses
   `secrets.compare_digest` (constant time).
3. **Operation-level confirmation.** Deleting a device requires
   `?confirm=true`; acknowledging an alert requires `{"confirm": true}`;
   scanning non-private ranges requires `"authorized": true` when the
   private-range guard is enabled.
4. **No CORS.** The API is for local tools/scripts; browser exposure is a
   future, separately reviewed feature.

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness + version (no token) |
| GET | `/api/system/info` | Static system inventory |
| GET | `/api/system/metrics` | Live metrics + threshold levels |
| POST | `/api/network/scan` | Body: `{cidr, authorized}` — runs a scan |
| GET | `/api/network/results` | Last scan of this session |
| GET | `/api/monitoring/devices` | Devices + latest status |
| POST | `/api/monitoring/devices` | Body: `{name, host, interval_seconds, timeout_ms}` |
| DELETE | `/api/monitoring/devices/{id}?confirm=true` | Delete device + history |
| POST | `/api/monitoring/check` | Check all enabled devices now |
| POST | `/api/logs/analyze` | Body: `{path}` — analyze a log file |
| POST | `/api/backups` | Body: `{source, destination, verify_mode}` where mode is `none`/`size`/`sha256` (`verify: bool` still accepted) |
| GET | `/api/backups` | Backup history |
| GET | `/api/alerts?limit=50` | Alerts + open count |
| POST | `/api/alerts/{id}/ack` | Body: `{"confirm": true}` |
| GET | `/api/reports` | Recent export files |
| POST | `/api/reports` | Body: `{report_key, format, hours, device_id}` |
| GET | `/api/activity?limit=50` | Audit trail |

Errors: invalid input → `400` with a human-readable `detail`; unknown
resources → `404`; missing/wrong token → `401`.

## Example

```bash
TOKEN=$(cat "$LOCALAPPDATA/ITOpsHub/api-token")
curl -H "X-API-Token: $TOKEN" http://127.0.0.1:8756/api/system/metrics
curl -X POST -H "X-API-Token: $TOKEN" -H "Content-Type: application/json" \
     -d '{"cidr": "192.168.1.0/24"}' http://127.0.0.1:8756/api/network/scan
```

## Verification

`tests/api/test_api.py` covers the security model (token enforcement on
every route, wrong-token rejection), every endpoint group through the real
service layer against a temporary database, validation failures, and the
confirmation semantics of destructive operations.
