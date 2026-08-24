# ITOps Hub — User Guide

ITOps Hub is a local, offline-first desktop tool for everyday IT operations:
monitor your machines, scan the networks you administer, analyze logs, back
up data, and export reports — all without sending anything anywhere.

## First steps

Launch **ITOps Hub**. The left sidebar switches between modules:

Dashboard · System · Network · Monitoring · Logs · Backups · Reports ·
Alerts · Settings

Everything works offline. Your data lives in `%LOCALAPPDATA%\ITOpsHub`.

## Dashboard

Live health at a glance: overall status (Healthy / Warning / Critical),
CPU / Memory / Disk KPI cards (colored by thresholds), a 10-minute live
utilization chart, recent alerts, and the audit trail. **Pause** freezes
live collection; snapshots are recorded at the interval set in Settings and
pruned after the retention window.

## System

Full inventory: hostname, OS/build/architecture, CPU model and cores,
frequency, total memory, boot time and uptime, storage volumes (with usage
levels), and network adapters with IPv4/IPv6 addresses. **Refresh**
recollects off-thread — the UI never freezes.

## Network scanner

1. Enter a CIDR network (e.g. `192.168.1.0/24`).
2. Press **Scan**. For non-private ranges, tick *I am authorized to
   administer this network* first — ITOps Hub refuses unauthorized scans by
   default.
3. Watch progress; **Cancel** stops cleanly with partial results.
4. Filter *Only reachable*, sort columns, and export to CSV/JSON/TXT.

Results include reachability, response time, hostname (when reverse DNS
knows it), and MAC (when present in the local ARP cache). Scan only networks
you own or administer.

## Monitoring

Add devices (**Add**): name, host/IP, check interval, timeout. The page
shows current state (Online / Warning / Offline — Warning means reachable
but slower than the latency threshold), last response, last seen, and
consecutive failures. **Check all now** runs one round; with *Auto check*
the app re-checks every 30 seconds, and the background scheduler checks each
device on its own interval. Select a device and a time range to view its
latency history and availability. The Disk volumes card shows usage against
your thresholds; breaches raise alerts automatically.

## Alerts & notifications

Threshold breaches (disk), unreachable devices, and recoveries land in the
Alerts page with severity colors. Raised alerts also pop up as **toast
cards** (bottom-right, click to open Alerts) and — for warning/critical —
**system-tray messages**; both channels can be toggled in Settings →
Notifications. Acknowledge alerts you have handled;
filters show unacknowledged ones only. Alerts are deduplicated — a flapping
condition raises one open alert until resolved.

## Logs

Pick any log file and **Analyze**. ITOps Hub auto-detects the format
(Python logging, syslog, or generic level-tagged lines; more parsers can be
added), counts levels, groups the most repeated errors, spans timestamps,
and flags anomalies (error bursts, logging gaps). Export the summary to
CSV/JSON/TXT.

## Backups

Choose a **source** (folder or file) and a **destination**, then **Run
backup**. Copies land in a fresh timestamped folder — your originals are
never modified or deleted. Verification is selectable: **Sizes & count** (fast), **SHA-256**
(thorough — recomputes per-file hashes), or **None**; a failed
verification marks the job FAILED, never silently successful. Cancelling removes only the partial copy it created.
Save **profiles** to schedule backups (e.g. every 24 h) — the background
scheduler runs them automatically while the app is open.

## Reports

Build reports from live data — monitoring history, per-device latency,
alerts, activity, disk usage, system snapshots — in **CSV/JSON/TXT/PDF**
with metadata headers (PDF: branded, paginated tables). Previously generated files are listed for quick access.

## Local API

Settings → *Local API* enables a loopback-only FastAPI service sharing the
same engine (docs at `http://127.0.0.1:<port>/docs`). It requires the
per-session token from `%LOCALAPPDATA%\ITOpsHub\api-token` (written
whenever the API starts — embedded or standalone). See `docs/api.md`.

## Settings

Theme (light/dark/system), language architecture, log level, monitoring
defaults, snapshot interval, disk thresholds, retention, export folder,
notification preferences, scanner limits, local API, and backup profiles.
Export/import settings as JSON for transfer between machines.
