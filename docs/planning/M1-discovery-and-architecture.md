# M1 — Discovery & Architecture

**Project:** ITOps Hub — Desktop IT Automation & Monitoring Platform
**Document:** Master Planning Response (per Master Project Spec §43)
**Status:** APPROVED — owner decisions recorded 2026-08-23 (see §12 / docs/decisions.md AD-001…AD-004); build proceeding continuously through v1.5
**Date:** 2026-08-23

---

## 1. Project Understanding

ITOps Hub is a **modular, offline-first desktop IT operations platform for Windows 10/11**, built with Python + PySide6 and SQLite, delivered as a standalone installer, and architected so a local FastAPI service (v1.5) and a future web/multi-device platform (v2.x) reuse the same core.

**Functional scope (v1.5):** Dashboard, System Information, Network Scanner (authorized networks only), Ping/Connectivity Monitor with persisted history, Disk Monitor with configurable thresholds + alerts, pluggable Log Analyzer, Backup Manager (non-destructive by design), Reports (CSV/JSON/TXT), Activity/Audit Log, and Settings.

**Non-functional bar:**
- Real functionality only — no mock data, no dummy buttons, no pretend integrations (§44).
- UI never blocks during long operations; progress and cancellation are first-class.
- Security & privacy by design: validated inputs, no `shell=True`, no secrets in repo or logs, API bound to localhost, no telemetry, all data stays local.
- Modular layered architecture: UI contains no business logic; services are shared by UI and API with zero duplication.
- Testable at unit, integration, and UI level; packaged for Windows with PyInstaller (+ installer); fully documented for handoff.

**Out of scope for v1.5 (per §3):** cloud deployment, SaaS, mobile, multi-machine remote administration, Active Directory, enterprise identity, AI assistant, full React frontend.

**Development environment note (transparent, per §44):** I develop and run all automated tests in a Linux sandbox. The core stack (psutil, SQLAlchemy, FastAPI, services, domain logic) is cross-platform and fully testable there; PySide6 UI tests run headless (`QT_QPA_PLATFORM=offscreen`). Windows-specific verification (packaged `.exe`, installer, tray notifications, Windows `ping.exe` behavior) is done via GitHub Actions `windows-latest` CI plus a short manual smoke checklist on your laptop at each release gate. I will never report a Windows-specific result as verified unless it actually was.

---

## 2. Proposed Architecture

### 2.1 Layered view (target v1.5)

```
┌─────────────────────────────────────────────────────────────┐
│ PRESENTATION                                                 │
│  ┌───────────────────────┐        ┌───────────────────────┐ │
│  │  PySide6 Desktop UI   │        │  FastAPI local API    │ │
│  │  (sidebar shell,      │        │  (localhost-only,     │ │
│  │   views, theme QSS,   │        │   token-guarded,      │ │
│  │   workers/threads)    │        │   OpenAPI docs)       │ │
│  └──────────┬────────────┘        └───────────┬───────────┘ │
└─────────────┼─────────────────────────────────┼─────────────┘
              ▼                                 ▼
┌─────────────────────────────────────────────────────────────┐
│ APPLICATION LAYER                                            │
│  Use cases / controllers · TaskManager (background jobs,    │
│  progress, CancelToken) · event bus · DTOs                  │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ SERVICE LAYER (shared by UI and API — single source of      │
│ business logic)                                              │
│  SystemInfo · NetworkScan · PingMonitor · DiskMonitor ·     │
│  LogAnalysis · Backup · Alerts · Reports · ActivityLog ·    │
│  Settings · Notifications · Scheduler                        │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ DOMAIN LAYER (pure Python, no I/O)                           │
│  Entities · value objects · interfaces (Protocols) ·        │
│  validation (CIDR, paths, thresholds, log records)          │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ INFRASTRUCTURE LAYER (implements domain interfaces)          │
│  SQLAlchemy repositories (SQLite WAL → Postgres-ready) ·    │
│  Alembic migrations · psutil/OS adapters · safe-subprocess  │
│  ping & ARP adapters · filesystem adapters · structured     │
│  logging · config store (platformdirs)                       │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
        SQLite · File System · OS APIs · Local network (authorized)
```

**Dependency rule:** arrows point inward only. UI and API never touch infrastructure directly; services never import Qt or FastAPI; domain imports nothing from outer layers. Wiring happens once in a composition root (`app/main.py`, manual constructor injection — no DI framework).

### 2.2 Layer responsibilities

| Layer | Responsibility | Forbidden |
|---|---|---|
| UI (PySide6) | Views, navigation, theme, workers/threads, confirmation dialogs, display formatting | Business logic, direct DB/network/OS access |
| Application | Use-case orchestration, background TaskManager (progress, cancellation), event bus, DTO mapping | Qt, FastAPI imports |
| Services | Business rules: scan policies, threshold evaluation, retention, backup safety, report generation | I/O details (delegated to infrastructure via interfaces) |
| Domain | Entities, validation, Protocols (e.g., `Pinger`, `SystemMetricsSource`, `FileStorer`) | Any I/O, any framework |
| Infrastructure | SQLAlchemy repos, psutil, `subprocess` ping/ARP (validated args, `shell=False`), files, logging | Business decisions |

### 2.3 Concurrency model (UI must never freeze — §19)

- **Services are synchronous and cooperatively cancellable** (a `CancelToken` checked inside loops). This keeps them trivially reusable from both Qt workers and FastAPI threadpool endpoints.
- **UI:** long tasks run in `QThread` workers created from thin controller objects; progress/results/cancel flow through signals. Buttons show busy/disabled states.
- **Fan-out work** (network scans, multi-device ping): `ThreadPoolExecutor` (bounded, configurable max workers) inside the service.
- **Monitoring loop:** a scheduler tick submits checks to the thread pool → results persisted → events published on the in-core event bus → UI (queued connection) and Alert/Notification services react.
- **FastAPI (v1.5):** runs in a daemon thread inside the app (opt-in start), or standalone via `python -m app.api`; sync endpoints execute services in Starlette's threadpool. No unnecessary asyncio.

### 2.4 Cross-cutting concerns

- **Theme system:** centralized QSS + palette tokens applied app-wide; PyQtGraph plot colors driven by the same tokens; dark/light switch live.
- **Logging:** stdlib `logging` → rotating file in the user data dir + sanitized formatter (password/token/secret patterns redacted). All services log through it; the Activity Log service records user-facing audit events to SQLite.
- **Alerts pipeline:** Disk/Ping/Log analyzers raise domain events → AlertService deduplicates + persists → NotificationService (in-app toast + system tray where available).
- **API security model (v1.5):** bind `127.0.0.1` only; per-session random token (`secrets.token_urlsafe(32)`) required via `X-API-Token` on every endpoint except `/api/health`; token stored in a user-only-readable file so local scripts can use it; sensitive operations additionally require an explicit `"confirm": true` field. No CORS (no browser client in v1.5).

---

## 3. Proposed Repository Structure

```text
itops-hub/
├── app/
│   ├── main.py                  # composition root + desktop entry point (--version, --selftest)
│   ├── application/             # use cases, task_manager, event_bus, dtos
│   ├── domain/                  # entities, interfaces (Protocols), validation
│   ├── services/                # system, network, monitoring, disk, logs,
│   │                            # backup, alerts, reports, activity, settings,
│   │                            # notifications, scheduler
│   ├── infrastructure/
│   │   ├── db/                  # engine/session, models, repositories, alembic/
│   │   ├── system/              # psutil adapter, ping/ARP subprocess adapters
│   │   ├── filesystem/          # backup file operations, exporters
│   │   └── logging/             # setup, sanitizing formatter
│   ├── api/                     # FastAPI app factory, routers, schemas, auth
│   ├── ui/
│   │   ├── main_window/         # sidebar shell, page router
│   │   ├── views/               # dashboard, system, network, monitoring, logs,
│   │   │                        # backups, reports, alerts, settings
│   │   ├── widgets/             # KPI cards, tables, toasts (reusable)
│   │   ├── workers/             # QThread workers (no logic, only bridging)
│   │   └── theme/               # QSS, palettes, theme service
│   └── config/                  # settings schema (pydantic), defaults, paths
├── tests/
│   ├── unit/  ├── integration/  ├── ui/  └── fixtures/        # incl. sample logs
├── docs/
│   ├── architecture.md  ├── data-model.md  ├── api.md
│   ├── security.md  ├── testing.md  ├── deployment.md
│   ├── user-guide.md  ├── decisions.md
│   └── planning/M1-discovery-and-architecture.md              # this document
├── scripts/                     # build.ps1, run_dev.sh, make_installer.iss helper
├── resources/
│   ├── icons/  ├── themes/  └── i18n/                          # Qt .ts/.qm from M2
├── .github/workflows/           # ci.yml (lint+type+tests, ubuntu+windows), build-windows.yml
├── data/  ├── reports/          # runtime-generated, .gitkeep'd, gitignored content
├── .env.example  ├── .gitignore  ├── LICENSE
├── pyproject.toml               # ruff/black/mypy/pytest config + project metadata
├── requirements.txt  ├── requirements-dev.txt
├── README.md  └── CHANGELOG.md
```

**Deviations from §9 (documented):**
1. `app/models/` is replaced by `app/infrastructure/db/models/` (SQLAlchemy models are persistence detail) + `app/application/dtos/`. Avoids a layer leak.
2. `data/` and `reports/` exist in-repo only as gitkept placeholders. **Real runtime data** (SQLite DB, logs, exports) lives in OS-appropriate per-user dirs (`%LOCALAPPDATA%\ITOpsHub`, Documents\ITOpsHub for exports) via `platformdirs` — correct behavior for an installed Windows app.
3. Added `.github/workflows/` — needed for the CI-built Windows executable (see §12 Q2).

---

## 4. MVP Scope (v1.0)

| # | Capability | v1.0 includes |
|---|---|---|
| 1 | Desktop shell | PySide6 sidebar app (Dashboard, System, Network, Monitoring, Logs, Reports, Alerts, Settings), dark/light themes |
| 2 | Dashboard | KPI cards (CPU/RAM/disk), OS/hostname/IP/network status, live charts, recent alerts & activity, health summary |
| 3 | System Information | Hostname, OS/version, CPU, RAM, storage, adapters, IPs, uptime, hardware basics |
| 4 | Network Scanner | CIDR input validation, authorized-use notice, default RFC1918/loopback/link-local guard with explicit override, concurrent scan with progress + cancel, hostname + best-effort MAC (ARP cache), response time, export |
| 5 | Ping Monitor | Device CRUD (name/host/interval/timeout), Online/Offline/Warning states, response time, failure count, last seen, history persisted |
| 6 | Disk Monitor | All drives, total/used/free/%, configurable warn/crit thresholds (80/90 default), alerts |
| 7 | Log Analyzer | Pluggable parser registry + generic fallback; INFO/WARN/ERROR/CRITICAL counts, top repeated errors, timestamp patterns, basic anomaly indicators; large-file streaming + cancel |
| 8 | Storage | SQLite (WAL) via SQLAlchemy + Alembic; retention prune for history tables |
| 9 | Reports | CSV / JSON / TXT export with metadata header; default export dir setting |
| 10 | Activity Log | Audit trail of app actions (scan/backup/alerts/settings), sanitized |
| 11 | Notifications | In-app toasts + system-tray notifications (where available) |
| 12 | Settings | Theme, intervals, thresholds, export dir, log level, notification prefs |
| 13 | Tests | Unit + integration + offscreen UI tests; CI on ubuntu + windows |
| 14 | Packaging | PyInstaller onedir build; GitHub Actions Windows artifact; `--selftest` smoke mode |

Deferred beyond v1.0 per §2: Backup Manager (v1.2), settings import/export (v1.2), scheduling (v1.3), FastAPI (v1.5), PDF export (optional later).

---

## 5. v1.5 Scope

Everything in v1.0, plus the increments from v1.1–v1.4, delivered as one stable release:

1. **Backup Manager (from v1.2)** — source/dest selection, timestamped naming, progress + cancel, verification (file count + sizes + optional SHA-256 manifest), logging, explicit confirmation for any overwrite; never deletes originals. Status persisted in `backup_jobs`.
2. **Monitoring improvements (v1.1)** — richer charts (history time ranges: 1h / 24h / 7d), latency graphs, better failure handling, enhanced notifications, UX polish.
3. **Background task manager + scheduling (v1.3)** — central TaskManager UI (running/completed/cancelled jobs); SchedulerService (interval-based, headless-capable) for scheduled monitoring rounds, scheduled backups, snapshot collection, and retention pruning.
4. **Hardening (v1.4)** — performance pass, expanded tests, service-layer refinement, better packaging.
5. **Local FastAPI service (v1.5)** — opt-in start (from Settings or `python -m app.api`), localhost-only, token auth, OpenAPI/ReDoc docs at `/docs`, endpoints per §11, served by the **same services the UI uses** (verified by shared-service integration tests — no duplicated logic).
6. **Reporting** — advanced report generation (filters, time ranges, metadata) in CSV/JSON/TXT; PDF only if trivial.
7. **Production packaging** — PyInstaller + Inno Setup installer (`ITOpsHub-Setup.exe`), upgrade/uninstall documented. Note: code-signing certificate is a paid item → excluded under the zero-cost budget (§41); SmartScreen warning on first run is a documented known limitation.
8. **Documentation & release process** — all §30 docs complete, security review recorded, regression suite green, CHANGELOG, handoff verification.

---

## 6. Data Model

SQLite via SQLAlchemy 2.0 (WAL mode). Types below are logical; exact DDL generated by Alembic migrations. Bold marks justified additions to §10's entity list.

### devices
| Column | Type | Notes |
|---|---|---|
| id | PK int | |
| name | text NOT NULL | unique per user |
| host | text NOT NULL | IP or hostname, validated |
| type | text | default `ping` (future types) |
| enabled | bool | default true |
| **interval_seconds** | int | default 30 — spec requires per-device interval |
| **timeout_ms** | int | default 1500 — spec requires per-device timeout |
| created_at / updated_at | timestamp | UTC |

### monitoring_results
`id` PK · `device_id` FK→devices (CASCADE) · `timestamp` UTC (indexed with device_id) · `status` CHECK(online/offline/warning) · `response_time_ms` real NULL · `error_message` text NULL
Index: `(device_id, timestamp DESC)` for fast history queries.

### system_snapshots
`id` PK · `timestamp` indexed UTC · `cpu_percent` real · `memory_percent` real · `disk_percent` real (max usage across volumes — documented semantics)

### backup_jobs
`id` PK · `source` text · `destination` text · `started_at` UTC · `completed_at` NULL · `status` CHECK(running/success/verified/failed/cancelled) · `size_bytes` int NULL · `files_copied` int NULL · `checksum_verified` bool NULL · `error_message` NULL

### alerts
`id` PK · `type` text (disk_threshold/device_offline/log_anomaly/…) · `severity` CHECK(info/warning/critical) · `source` text · `message` text · `created_at` indexed · `acknowledged` bool default false · `acknowledged_at` NULL

### activity_logs
`id` PK · `timestamp` indexed · `action` text · `module` text · `status` CHECK(success/failure/info) · `message` text (sanitized)

### settings *(addition — justification below)*
`key` text PK · `value` text (JSON) · `updated_at`
**Justification:** §1.3-J requires structured, reliable, import/exportable settings. A single transactional store alongside operational data is simpler and more reliable than a separate config file; values validated by a pydantic schema on read.

**Deliberately not added:** `network_scan_results` table — v1.5 keeps scan results session-scoped + exportable; persistence of scan history is deferred (would be a small, contained addition later).

**Retention rules (§20):** configurable; defaults — prune `monitoring_results` and `system_snapshots` older than 30 days (nightly scheduler job), keep alerts/activity 90 days. Downsampling can be added later without schema change.

---

## 7. Technology Decisions

Each will be recorded in `docs/decisions.md` (ADR format) after sign-off.

| # | Decision | Choice & rationale |
|---|---|---|
| D1 | Language/runtime | **Python 3.12** (support 3.11+). Mature support across PySide6 ≥6.6, PyInstaller, SQLAlchemy 2, FastAPI. |
| D2 | Desktop stack | **Keep PySide6** (no switch to Tauri Option A). Tauri+React+TS would add a second toolchain/runtime, longer builds, a JS/Python IPC bridge to maintain, and higher packaging complexity — with no v1.5 benefit since the target is a native Windows desktop app. Migration cost would be a rewrite of the entire presentation layer. Re-evaluate only if v2.0 becomes web-first. |
| D3 | ORM/data access | **SQLAlchemy 2.0** + repository pattern + **Alembic** migrations. Repositories isolate SQL; PostgreSQL later = dialect + connection change, not a core rewrite. SQLite WAL for concurrent reads during writes. |
| D4 | System metrics | **psutil** — cross-platform, no admin rights needed. |
| D5 | Charts | **PyQtGraph** (MIT). Best performance for live, high-frequency time series (CPU/RAM/latency), simple packaging, programmatic theming. Qt Charts is slower for streaming updates and its licensing (GPL/commercial) is less clean for distribution. |
| D6 | ICMP/ping & MAC | **System `ping` via `subprocess.run` with list arguments, `shell=False`, validated host, bounded timeout** — works without admin rights (raw-socket libs like scapy/icmplib need elevation on Windows). Reachability from locale-independent exit codes; latency parsed best-effort; optional TCP-connect probe fallback for ICMP-blocked hosts. MAC via ARP cache (`arp -a`) parsing after ping — no Npcap dependency. Limitations documented (see R2). |
| D7 | Local API | **FastAPI + uvicorn**, localhost bind, per-session token auth, OpenAPI auto-docs. Runs embedded (daemon thread, opt-in) or standalone (`python -m app.api`). |
| D8 | Validation/schemas | **Pydantic v2** for settings model and API schemas. |
| D9 | Config/paths | **platformdirs** for OS-correct data/log/export locations. `.env` only for developer overrides; no secrets by design. |
| D10 | DI | Manual composition root (constructor injection). No framework — fewer deps, fully explicit, easy to test. |
| D11 | Testing | **pytest** + pytest-qt (offscreen) + httpx/TestClient; fake `Pinger`/`SystemMetricsSource` behind domain Protocols for deterministic unit/integration tests. |
| D12 | Packaging | **PyInstaller (onedir)** + **Inno Setup** installer; built on GitHub Actions `windows-latest` (free tier) with artifact upload. `--selftest` CLI mode for smoke-testing the packaged exe. |
| D13 | Quality tooling | Ruff (lint + format), MyPy (strict on domain/services/application), pre-commit. |
| D14 | i18n | Qt Linguist pipeline (tr() + .ts/.qm) wired from M2 so languages are translation-only additions; v1.5 ships English (+ Arabic if owner selects — Q3). |
| D15 | Scheduling | Custom minimal interval-based SchedulerService (background thread, survives UI-less API mode). No APScheduler dependency; calendar cron syntax deferred. |

---

## 8. Risks

| # | Risk | Sev | Mitigation |
|---|---|---|---|
| R1 | **Windows verification gap** — I develop/test on Linux; Windows behavior must be verified | High | Cross-platform core + CI matrix (ubuntu + windows) from M2; Windows exe built by CI each release; short manual smoke checklist for owner per milestone; honest status reporting |
| R2 | Ping/MAC without admin rights: raw ICMP unavailable; `ping`/`arp` output varies by locale | Medium | Locale-independent exit-code reachability; best-effort latency/MAC flagged "when available" (spec allows); TCP probe fallback; limitations documented in user guide |
| R3 | PyInstaller + PySide6 packaging pitfalls (missing DLLs/plugins, AV false positives) | Medium | Onedir builds; CI builds exe every release from M8; `--selftest` mode; early packaging spike in M2 to de-risk |
| R4 | SQLite write contention (monitor loop + UI + API) | Medium | WAL mode, short sessions, single-writer discipline, stress test in integration suite |
| R5 | Backup operations touching user data | High | Non-destructive design: never deletes/overwrites originals without explicit confirmation; verification step; dry-run size estimate; tests for failure mid-copy |
| R6 | Log format diversity → weak analysis | Medium | Parser registry + format auto-detection with confidence scoring + generic fallback; sample logs in test fixtures |
| R7 | Scope creep toward v2 features | Medium | §3 enforced; changes only via decisions.md with owner approval |
| R8 | Unsigned exe → SmartScreen warning | Low | Accepted under zero-cost budget (§41); documented; signing = future paid option |
| R9 | Long-running scans on large subnets | Low | Host-count cap with warning, bounded thread pool, cancellable, streaming UI updates |
| R10 | PyQtGraph theming consistency dark/light | Low | Central theme service drives both QSS and plot palettes; visual snapshot test offscreen |

---

## 9. Assumptions

| # | Assumption | Why | Impact |
|---|---|---|---|
| A1 | Single user, single machine; desktop UI has no login (OS user session is the boundary); API guarded by localhost + per-session token | Desktop tool reality | Medium |
| A2 | Windows 10/11 x64 is the only *packaged* target; Linux/macOS run from source for development | Spec §23 | Low |
| A3 | No admin elevation requested; admin-dependent capabilities degrade gracefully and are documented | Usability for support techs | Medium |
| A4 | User is responsible for scanning only networks they are authorized to administer; UI shows an authorization notice | Legal safety; spec §1.3-C | Low |
| A5 | Runtime data in `%LOCALAPPDATA%\ITOpsHub` (DB, logs) and `Documents\ITOpsHub` (exports) | Windows conventions | Low |
| A6 | PDF export deferred (spec §1.3-H permits) | Keep MVP lean | Low |
| A7 | Git repo initialized locally in the workspace; publishing to GitHub done by owner (I have no credentials) — CI builds require the GitHub repo | Credential boundary | Medium |
| A8 | Zero-cost: all deps FOSS; GitHub free tier; no code-signing cert | §41 | Low |
| A9 | v1.5 API is opt-in (does not auto-start with the app) unless owner prefers otherwise | Security-default | Low |
| A10 | English UI in v1.5 unless owner adds Arabic (Q3); i18n plumbing exists from M2 | Scope control | Low |

---

## 10. Milestones

| M | Version | Scope | Exit criteria (evidence) |
|---|---|---|---|
| M1 | v0.1–v0.2 | Discovery & architecture (this document) | Owner sign-off on plan + Q1–Q4 decisions |
| M2 | v0.3 | Repo skeleton, config, logging, DB + migrations, theme system, main window nav, CI (lint/type/test, ubuntu+windows), packaging spike | CI green on both OSes; `python -m app.main --version` works; offscreen UI smoke test passes |
| M3 | v0.4 | SystemInfo service + Dashboard v1 (KPI cards, live charts, snapshots) | Service tests pass; dashboard renders offscreen with stubbed + real metrics; snapshots persisted |
| M4 | v0.5 | Network scan service + UI (validation, concurrency, cancel, ARP/hostname, export) | Unit tests incl. invalid CIDR/timeout/cancel; integration test with fake Pinger; manual authorized scan on owner's LAN |
| M5 | v0.6 | Ping monitor (devices CRUD, states, history), disk monitor + alerts, notifications | Deterministic monitor tests (fake clock/pinger); threshold tests; alerts persisted; history query tests |
| M6 | v0.7 | Log analyzer (parser registry, stats, anomalies, streaming, UI) | Parser tests on fixture logs (incl. unknown format); large-file cancel test |
| M7 | v0.8 | Reports service (CSV/JSON/TXT), activity log UI, settings complete | Export round-trip tests; audit events for all key actions; settings persistence tests |
| M8 | v0.9–v1.0 | MVP hardening, regression suite, packaging (PyInstaller + installer), README/docs pass | **All §27 acceptance criteria green incl. CI-built exe**; tag v1.0 |
| M9 | v1.1–v1.3 | Monitoring improvements, Backup Manager, reports advanced, settings import/export, TaskManager UI, SchedulerService | Backup success/failure/verification tests incl. mid-copy failure; scheduled jobs run headless; tag checkpoints |
| M10 | v1.4–v1.5 | Hardening, FastAPI local API + OpenAPI + token auth, shared-service verification, security review, final docs, installer | **All §28 acceptance criteria green**; API integration tests; security review doc; regression green; tag v1.5 |

Progress reported after each milestone in the exact §36 format, with evidence.

---

## 11. Acceptance Criteria

### v1.0 (§27) — verification method per criterion

| Criterion | Verified by |
|---|---|
| App launches without critical errors | CI Windows job runs `python -m app.main --selftest`; owner smoke checklist |
| Dashboard / System info / Disk / Scanner / Ping / Log analyzer work | Unit + integration + offscreen UI tests; owner manual checklist |
| Export works | Automated round-trip tests (write→read→compare) |
| SQLite storage works | Integration tests against temp DB; migration up/down tests |
| UI responsive during long ops | pytest-qt tests (no blocking) + design (workers/threads); manual check during real scan |
| Core tests pass | CI gate (ubuntu + windows matrix) |
| Windows executable builds | GitHub Actions build-windows workflow artifact |
| README complete; no secrets in repo | Docs review; pre-commit secret scan |

### v1.5 (§28) — additionally

Backup Manager stability (incl. failure-path tests) · monitoring history ranges + retention (integration tests) · alerts lifecycle (tests + manual ack) · scheduling architecture ready (headless scheduler integration test) · FastAPI service works + OpenAPI exists (TestClient + live startup test) · API integration tests · **UI and API share the same services** (enforced by import rules + shared-service test suite; no duplicated business logic) · packaging documented (deployment.md) · security review completed (docs/security.md checklist) · regression suite passes · final release checklist.

---

## 12. Questions Requiring Owner Decision

These change schedule, scope, or delivery — decided before M2 (defaults in parentheses; if you have no preference I proceed with the default and record it in decisions.md):

1. **Delivery cadence** — pause for your review at every milestone gate, or build continuously to the v1.0 MVP gate, or run straight through v1.5 with risk flags only? *(Default: continuous to v1.0, full review, then continue.)*
2. **Windows executable verification** — I cannot run Windows in my sandbox. Build the exe via GitHub Actions `windows-latest` (requires the repo pushed to GitHub), or via build scripts you run locally on your laptop, or both? *(Default: both.)*
3. **UI language for v1.5** — English only (i18n-ready), or English + Arabic (adds RTL verification work)? *(Default: English only.)*
4. **License** — MIT, Apache-2.0, or GPL-3.0? All are compatible with PySide6's LGPL for this app. *(Default: MIT.)*

Low-risk items I will decide and document (not asking): charts library (PyQtGraph), ping method (subprocess `ping`, no Npcap), settings stored in SQLite, data locations, Alembic for migrations, manual DI, interval-based scheduler. See §7 and §9.

---

## Progress Update

**Milestone:** M1 — Discovery & Architecture

**Status:** Completed — owner answered Q1–Q4 (continuous through v1.5; CI-built Windows artifacts; English-only v1.5; MIT) and approved proceeding

**Completed**

* Full 12-section planning response per §43
* Layered architecture, data model, technology decisions, risk register, milestone plan with exit criteria

**Artifacts**

* `itops-hub/docs/planning/M1-discovery-and-architecture.md` (this document)

**Tests**

* None yet — planning phase (first tests land in M2)

**Issues**

* Windows-specific runtime verification depends on Q2 decision (CI vs local vs both)

**Assumptions**

* A1–A10 in §9, pending owner override

**Next**

* M2 — Core setup: repo skeleton, CI, DB layer, theme system, main window shell, packaging spike

**Version**

* v0.1 (Planning) → v0.2 (Architecture) upon sign-off
