# Changelog

All notable changes to ITOps Hub are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/).

## [Unreleased]

### Planned next (v0.4 / M3)
- System information service (psutil) and System page
- Dashboard with KPI cards, live PyQtGraph charts, snapshot recording

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
- 79 automated tests (unit / integration / offscreen UI); ruff + mypy strict
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
