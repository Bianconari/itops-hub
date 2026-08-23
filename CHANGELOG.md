# Changelog

All notable changes to ITOps Hub are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/).

## [Unreleased]

### Future (v2.x roadmap)
- Web dashboard, remote monitoring agents, PostgreSQL, authentication

## [1.5.0] — 2026-08-23 — Stable Local API Release (M10)

### Added
- **Local FastAPI service** (`app/api`): loopback-only by default, opt-in
  embedded start (Settings) or standalone `python -m app.api`; per-session
  32-byte token (`X-API-Token`, constant-time compare) on every route except
  `/api/health`; confirmation semantics on destructive operations; OpenAPI
  docs at `/docs`; 17 endpoint groups covering system, network, monitoring,
  logs, backups, alerts, reports, and activity — all through the same
  service layer the UI uses (verified live + 25 API tests)
- Production packaging: windowed onedir PyInstaller spec, Inno Setup
  installer script, CI builds exe + installer and runs the packaged selftest
- Complete documentation set: `api.md`, `security.md` (v1.5 review record),
  `testing.md`, `deployment.md`, `user-guide.md`; three new ADRs
  (AD-017–019); README rewritten for v1.5
- Session-per-operation repositories hardened across all stores (AD-019)

## [1.3.0] — 2026-08-23 — Scheduling (M9)

### Added
- `SchedulerService`: headless interval scheduler (30s ticks) — per-device
  monitoring rounds, snapshot recording, retention pruning (daily), and
  scheduled backup profiles; started/stopped with the application
- Backup profiles persisted in settings with enable/disable and delete

## [1.2.0] — 2026-08-23 — Backup Manager (M9)

### Added
- `BackupService` + `backup_jobs` persistence: timestamped never-overwritten
  destinations, manifest verification (size/count), cooperative cancel that
  removes only its own partial copy, source/destination layout safety rules,
  audit logging and events
- Backups page: run with progress (files/MB), cancel, verification toggle,
  history table, scheduled-profile management
- Settings export/import (JSON) with validation and confirmation

## [0.8.0] — 2026-08-23 — Reports (M7)

### Added
- `ReportService` with six datasets: monitoring history, per-device latency,
  alerts, activity/audit, disk usage, system snapshots — time ranges
  (1h/24h/7d) and CSV/JSON/TXT output through the shared export service
- Reports page with dataset/range/format controls and recent-exports list

## [0.7.0] — 2026-08-23 — Log Analyzer (M6)

### Added
- Pluggable parser registry with confidence-based auto-detection:
  Python-logging, syslog (severity-inferred), and generic level-tag fallback
- `LogAnalysisService`: streaming chunked analysis (bounded memory),
  progress + cancellation, level counts, normalized top-error grouping,
  timestamp spans, anomaly detection (error bursts, logging gaps)
- Logs page with file picker, progress, summary, top-errors table, and
  export; sample fixtures for three formats

## [0.6.0] — 2026-08-23 — Monitoring, Disk Alerts, Alerts Lifecycle (M5)

### Added
- Device CRUD with validation; `MonitorService` state machine
  (online/offline/warning-by-latency), concurrent rounds, consecutive-failure
  tracking, persisted history with retention
- `AlertService` lifecycle: deduplicated raise, auto-resolve on recovery,
  acknowledge; `DiskService` threshold alerts with auto-ack on clearance
- Monitoring page (devices table, check-now, auto-check, latency history
  chart, disk volumes card) and Alerts page (filters, acknowledge)
- Repositories moved to session-per-operation for thread safety (AD-019)

## [0.5.0] — 2026-08-23 — Network Scanner (M4)

### Added
- Network domain model (`HostResult`, `ScanResult`, `PingResult`) and
  Protocols (`Pinger`, `HostnameResolver`, `ArpSource`)
- `NetworkScanService`: validated CIDR input, authorization guard (public
  ranges require an explicit override when `scan_private_only` is on), host
  cap, bounded ThreadPoolExecutor fan-out, cooperative cancellation with
  partial results, progress callback, hostname resolution for reachable
  hosts, best-effort MAC enrichment from the ARP cache, activity logging and
  `scan.completed` events
- Production adapters: `SystemPinger` (OS `ping` via argument-list
  `subprocess.run`, `shell=False`, locale-independent exit-code + TTL
  reachability check, best-effort latency parsing — AD-009),
  `SocketHostnameResolver`, `ArpTable` (Windows `arp -a` / Linux
  `/proc/net/arp` parsing with MAC normalization)
- `ExportService`: reusable CSV/JSON/TXT writers with metadata headers,
  timestamped filenames, never-overwrite behavior — used by the scanner now
  and by reports in v0.6–v0.8
- Network page: CIDR input, authorization checkbox, scan/cancel with
  progress, sortable results table, reachable-only filter, per-format export
  buttons, error surfacing (authorization/limit messages), stale-result
  protection on instant cancel
- Settings: `scan_max_hosts` (default 1024) + UI control; scan concurrency
  control retained
- `ScanWorker` QThread; `docs/data-model.md` added
- 47 new tests (192 total); real
  end-to-end scan verified against loopback (6/6 hosts, resolution, ARP,
  export, audit trail)

## [0.4.0] — 2026-08-23 — System Module & Dashboard (M3)

### Added
- `SystemInfoService` over a new `SystemMetricsSource` Protocol: static system
  facts (hostname, OS, CPU model/cores/frequency, RAM, boot time, adapters),
  drive usages, live metrics, and threshold-classified `SystemStatus`
- Production `PsutilSystemSource` adapter (no admin rights; CPU model via
  `PROCESSOR_IDENTIFIER` on Windows / `/proc/cpuinfo` on Linux)
- `SnapshotService` + `SystemSnapshotRepository`: persisted history with
  time-range queries and retention pruning (applied on app start)
- Alert read feed (`AlertService` + `AlertRepository`) powering the dashboard
  panel (raising/acknowledging arrives in v0.6)
- Dashboard view: overall health card (hostname, OS, IPv4, interfaces, uptime),
  CPU/RAM/Disk KPI cards with severity accents, live 10-minute PyQtGraph
  utilization chart (CPU/Memory/Disk), recent alerts + activity feeds,
  pause/resume, snapshot recording at the configured cadence
- Reusable widgets: `KpiCard`, `TimeSeriesChart` (token-themed pyqtgraph
  wrapper); workers: `OneShotWorker`, `MetricsPoller` (QThread, UI never blocks)
- System view: full inventory with storage-volume and network-adapter tables,
  threshold-colored usage, off-thread refresh with loading/error states
- Settings: new system snapshot interval control
- 66 new tests (145 total): domain units, service fakes, repository
  integration, psutil adapter contracts, offscreen UI (KPI/chart/dashboard/
  system view incl. error paths); fixed a real teardown race in OneShotWorker
  (moveToThread pattern replaced with a QThread subclass)

## [0.3.0] — 2026-08-23 — Core Setup (M2)

### Added
- Repository skeleton, layered architecture (UI / application / services /
  domain / infrastructure), manual DI composition root (`AppContainer`)
- Complete v1.5 database schema (7 tables) with Alembic initial migration;
  SQLite WAL engine with foreign keys enforced; programmatic migration runner
- Pydantic v2 settings model + `SettingsService` (partial nested updates,
  corruption fallback to defaults, change events, audit entries)
- Activity/audit log service with credential sanitization
- Centralized theme system: light/dark design tokens, single QSS document,
  `ThemeService` with live toggle and system-scheme detection
- Application shell: sidebar navigation, stacked pages, status bar,
  placeholder pages honestly labeled with their target version
- Fully functional Settings page (theme, log level, defaults, thresholds,
  retention, export dir, notifications, scanner options)
- Rotating sanitized file logging; `EventBus`; `CancelToken`; domain
  validators (CIDR, host, path, thresholds)
- Entry points: `python -m app.main [--version|--selftest]`
- CI (lint/type/test on ubuntu + windows, Qt offscreen) and Windows
  PyInstaller build workflow (first execution pending repo push — AD-002)
- 145 automated tests (unit / integration / offscreen UI); ruff + mypy strict
  clean; docs: architecture, decisions, M1 planning; MIT license

## [0.2.0] — 2026-08-23 — Architecture (M1)

### Added
- Full discovery & architecture plan: layers, data model, technology
  decisions (AD-001…AD-016), risk register, milestone plan with exit
  criteria (`docs/planning/M1-discovery-and-architecture.md`)
- Owner decisions recorded: continuous delivery to v1.5, CI-built Windows
  artifacts, English-only v1.5, MIT license

## [0.1.0] — 2026-08-23 — Planning (M1)

### Added
- Master project specification intake and scope definition; v1.5 target
  release definition; out-of-scope list (cloud/SaaS/mobile/AD/AI)
