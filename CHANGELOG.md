# Changelog

All notable changes to ITOps Hub are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/).

## [Unreleased]

### Planned next (v0.5 / M4)
- Network scan service (CIDR validation, concurrent checks, cancel, ARP/hostname)
- Network scanner page with results table and export

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
