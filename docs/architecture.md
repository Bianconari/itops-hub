# Architecture

ITOps Hub v1.5 is a layered desktop application with a Qt-free core, so the
same business services power the PySide6 UI, the background scheduler, and
the local FastAPI service without duplication.

## Layers (as implemented)

```
┌─────────────────────────────────────────────────────────────┐
│ PRESENTATION                                                 │
│  ┌───────────────────────┐        ┌───────────────────────┐ │
│  │  PySide6 Desktop UI   │        │  FastAPI local API    │ │
│  │  9 views · workers    │        │  (loopback, token     │ │
│  │  (QThread) · theme    │        │   auth, OpenAPI)      │ │
│  └──────────┬────────────┘        └───────────┬───────────┘ │
└─────────────┼─────────────────────────────────┼─────────────┘
              ▼                                 ▼
┌─────────────────────────────────────────────────────────────┐
│ APPLICATION — AppContainer (composition root, manual DI),   │
│ SchedulerService (background rounds/snapshots/backups)      │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ SERVICES (business logic, framework-free)                    │
│  SystemInfo · NetworkScan · Monitor · Disk · LogAnalysis ·   │
│  Backup · Alerts · Reports · Export · Settings · Activity ·  │
│  Snapshots · Scheduler                                      │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ DOMAIN (pure Python, no I/O)                                │
│  entities · validation · Protocols · event bus ·            │
│  cancellation · sanitization                                │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
         ┌────────────（implements Protocols）─────────────┐
         ▼ INFRASTRUCTURE                                 │
           SQLAlchemy repositories (SQLite WAL, session-   │
           per-operation) · Alembic migrations · psutil    │
           adapters · safe-subprocess ping/ARP · rotating  │
           sanitized logging · export writers              │
         ▼                                                 │
         SQLite · File System · OS APIs · Local network     │
```

## Rules (enforced in review)

1. **Dependency direction is inward only.** UI/API → application → services
   → domain; infrastructure implements domain Protocols and is wired once in
   the composition root (`app/application/container.py`).
2. **No business logic in UI widgets.** Views call services; services raise
   domain errors; views translate them into user-facing messages.
3. **No I/O in the domain.** Validators, entities, the event bus, and the
   cancel token are pure and unit-testable.
4. **Services never import Qt or FastAPI.** They are synchronous and
   cooperatively cancellable (`CancelToken`), so the same service call runs
   unchanged inside QThread workers, scheduler jobs, and API endpoints.
5. **One stylesheet, two palettes.** All styling flows from
   `app/ui/theme/tokens.py` (light/dark) through a single QSS document;
   charts are themed from the same tokens.

## Concurrency model

- Long operations run in QThread workers (`app/ui/workers/`) — scans,
  monitor rounds, log analysis, backups, exports; the UI thread only
  receives queued signals (never blocks).
- Fan-out work uses bounded `ThreadPoolExecutor`s inside services
  (scans, monitor rounds, scheduler jobs).
- `SchedulerService` runs on its own daemon thread with 30s ticks:
  per-device monitoring rounds, snapshot recording, retention pruning
  (daily), and scheduled backup profiles. It never overlaps a job with
  itself and survives individual job failures.
- The FastAPI service runs standalone (`python -m app.api`) or embedded on
  a daemon thread (opt-in via Settings); sync endpoints execute through
  Starlette's threadpool onto the same services.

## Database architecture

- SQLite in WAL mode with foreign keys enforced; **session-per-operation**
  repositories (thread-safe across UI, workers, scheduler, and API).
- Schema: 7 tables (`devices`, `monitoring_results`, `system_snapshots`,
  `backup_jobs`, `alerts`, `activity_logs`, `settings`) created by the
  initial Alembic migration; the app runs `run_migrations()` at every
  startup, so upgrades apply automatically.
- Retention: snapshots and monitoring results older than
  `retention_days` (default 30) are pruned on startup and daily by the
  scheduler. See `docs/data-model.md`.

## API integration (no duplicated logic)

`create_app(container)` (in `app/api/app_factory.py`) receives the same
`AppContainer` the desktop UI uses. Every endpoint delegates to a service
method; the API layer adds only HTTP concerns: Pydantic request schemas,
token middleware (`X-API-Token`, constant-time compare, exempting
`/api/health` and the OpenAPI routes), and 400/404 error mapping.
The UI and the API are therefore consistent by construction.

## Data flow examples

**Settings change**
```
SettingsView ──update(dict)──▶ SettingsService ──merge+validate──▶ AppSettings
      └──save_raw(json)──▶ SettingRepository ──▶ SQLite
      └──publish──▶ EventBus[settings.changed] ──▶ UI/alerts
      └──record──▶ ActivityLogService ──▶ audit trail
```

**Scheduled backup profile**
```
SchedulerService tick ── due? ──▶ BackupService.run_backup(source, dest)
      ── walk + copy (cancel-aware) ──▶ manifest.json + verification
      ──▶ backup_jobs row ──▶ EventBus[backup.completed] ──▶ audit trail
```

**API scan request**
```
POST /api/network/scan ── token middleware ──▶ NetworkScanService.scan()
      ── validate CIDR + authorization guard ──▶ ThreadPoolExecutor pings
      ──▶ ARP/hostname enrichment ──▶ JSON payload (no UI involvement)
```

## Module map (current state — all implemented)

| Area | Where |
|---|---|
| Composition root, container, retention | `app/application/container.py` |
| Background scheduler | `app/services/scheduler_service.py` |
| Settings model + service (import/export) | `app/config/settings.py`, `app/services/settings_service.py` |
| Activity/audit log | `app/services/activity_service.py` |
| System info + live metrics | `app/services/system_service.py`, `app/infrastructure/system/psutil_source.py` |
| Snapshots + retention | `app/services/snapshot_service.py` |
| Alerts lifecycle (raise/dedup/ack/resolve) | `app/services/alert_service.py` |
| Disk thresholds | `app/services/disk_service.py` |
| Monitoring (states, rounds, history) | `app/services/monitor_service.py` |
| Network scanner (guard, cancel, export) | `app/services/network_scan_service.py`, `app/infrastructure/network/` |
| Log analyzer (parser registry, anomalies) | `app/domain/loganalysis.py`, `app/services/log_analysis_service.py` |
| Backups (verify, cancel-safe) | `app/services/backup_service.py` |
| Reports + exports (CSV/JSON/TXT) | `app/services/report_service.py`, `app/services/export_service.py` |
| Local API + token auth | `app/api/` |
| Theme system (light/dark) | `app/ui/theme/` |
| Shell + 9 views | `app/ui/main_window/`, `app/ui/views/` |
| Workers (QThread bridges) | `app/ui/workers/` |

Planning history and per-milestone detail: `docs/planning/`.
Decisions: `docs/decisions.md` (19 ADRs).
