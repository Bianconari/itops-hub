# Architecture Decision Records

Status legend: **Accepted** / Proposed / Superseded.

---

## AD-001 — Delivery cadence: continuous through v1.5

**Status:** Accepted (Project Owner, 2026-08-23)

**Context:** 15 version milestones (v0.1→v1.5) grouped into M1–M10; agent
development with owner review.

**Decision:** Build continuously through v1.5 with risk flags raised in
progress reports; no per-milestone approval gates.

**Reason:** Owner chose minimum interaction overhead; risks are surfaced in
each §36 progress update instead.

---

## AD-002 — Windows executable built and verified via GitHub Actions

**Status:** Accepted (Project Owner, 2026-08-23)

**Context:** Development environment is Linux; the target OS is Windows 10/11.

**Decision:** `build-windows.yml` runs PyInstaller on `windows-latest` and
executes the packaged `--selftest`; artifacts are downloaded from Actions.
Owner may also build locally; scripts/docs are provided.

**Consequence:** The workflow's first real execution requires the repository
to be pushed to GitHub. Until then the workflow is written but **not
verified** — this is tracked as an open item.

---

## AD-003 — v1.5 UI language: English only

**Status:** Accepted (Project Owner, 2026-08-23)

**Decision:** Ship English; the Qt Linguist pipeline is wired from v0.3 so
Arabic (or any language) is translation + RTL-verification work later.

---

## AD-004 — License: MIT

**Status:** Accepted (Project Owner, 2026-08-23)

**Reason:** Simple, permissive, GitHub-friendly. PySide6/Qt LGPL obligations
are satisfied by dynamic linking; the app's own MIT code imposes no further
restriction.

---

## AD-005 — Desktop stack: PySide6 (keep primary stack)

**Status:** Accepted

**Context:** Spec §5 allows switching to Tauri + React + TS + FastAPI.

**Decision:** Stay on Python + PySide6.

**Reason:** Native Windows desktop target; one language/runtime across UI,
services and API; simplest packaging (PyInstaller) and testing story. The
Tauri alternative adds a second toolchain, an IPC bridge, and a rewrite of
the entire presentation layer — migration cost with no v1.5 benefit.
Re-evaluate only if v2.x becomes web-first.

---

## AD-006 — Python 3.12/3.13, requires-python >= 3.11

**Status:** Accepted

**Reason:** Stable, supported, fully supported by PySide6 ≥ 6.7, PyInstaller,
SQLAlchemy 2, FastAPI. CI matrix: 3.12 (Windows) + 3.12/3.13 (Linux);
developed and verified on 3.13.

---

## AD-007 — Data access: SQLAlchemy 2.0 + repositories + Alembic

**Status:** Accepted

**Reason:** Repository Protocols live in the domain; SQLAlchemy implements
them, so swapping SQLite → PostgreSQL later is a connection/dialect change.
Alembic gives reviewable, reversible schema history from day one (SQLite
migrations use batch mode). SQLite runs WAL + foreign keys + NORMAL sync.

---

## AD-008 — Charts: PyQtGraph

**Status:** Accepted

**Reason:** Best performance for live, high-frequency time series (CPU/RAM/
latency streams); MIT license; pure-Python packaging; programmatic theming
from the central theme tokens. Qt Charts is slower for streaming updates and
its GPL/commercial licensing is less clean for distribution.

---

## AD-009 — ICMP reachability via system `ping` subprocess (no admin, no Npcap)

**Status:** Accepted

**Context:** Raw-socket ICMP (scapy, icmplib, ping3) requires Administrator
on Windows; Npcap is an extra system dependency users must install.

**Decision:** Use the OS `ping` binary through `subprocess.run` with a
validated argument list, `shell=False`, and bounded timeouts. Reachability
is decided from the locale-independent exit code; response time is parsed
best-effort; a TCP-connect probe is offered as a fallback for ICMP-filtered
hosts. MAC addresses come from the ARP cache (`arp -a`) after scanning —
no Npcap.

**Consequence (documented limitation):** without admin rights some hosts
that drop ICMP appear offline even when reachable (use the TCP probe);
`arp` output parsing is best-effort and marked "when available" per spec.

---

## AD-010 — Local API security model (v1.5)

**Status:** Accepted (design; implementation lands in M10)

**Decision:** FastAPI binds `127.0.0.1` only by default; a per-session random
token (`secrets.token_urlsafe(32)`) is required in `X-API-Token` for all
endpoints except `/api/health`; sensitive operations additionally require an
explicit `"confirm": true` payload field; no CORS in v1.5. The API is opt-in
(not auto-started with the desktop app).

---

## AD-011 — Settings stored in SQLite as one validated JSON document

**Status:** Accepted

**Reason:** Spec requires structured, reliable, import/exportable settings.
A single `settings` table row (`key='app.settings'`) validated by a Pydantic
model gives transactional writes, trivial export/import (v1.2), and
corruption fallback to defaults. Alternative (separate config file) splits
state across two stores.

---

## AD-012 — Manual DI (composition root), no framework

**Status:** Accepted

**Reason:** The dependency graph is small; explicit constructor injection in
`AppContainer` is fully traceable and trivially testable.

---

## AD-013 — Concurrency model: sync services + CancelToken + thread pools

**Status:** Accepted

**Reason:** Services stay Qt-free and reusable from FastAPI threadpool
endpoints. The UI wraps work in QThread workers; fan-out (scans, multi-ping)
uses bounded ThreadPoolExecutors; monitoring loops are scheduler-driven and
submit checks to the pool. asyncio is not used for the core (no benefit for
subprocess/psutil workloads).

---

## AD-014 — Runtime data locations via platformdirs

**Status:** Accepted

**Reason:** Installed Windows apps must not write into Program Files or the
repository. Data/logs → `%LOCALAPPDATA%\ITOpsHub`; exports default to
`Documents\ITOpsHub`. `ITOPS_HUB_DATA_DIR` overrides for dev/tests.

---

## AD-015 — Scheduling: custom interval-based SchedulerService (v1.3)

**Status:** Accepted

**Reason:** v1.3 needs interval jobs (monitor rounds, backups, snapshot,
retention prune) that also run in headless API mode. A minimal thread-based
scheduler avoids the APScheduler dependency; calendar/cron syntax is a
future addition behind the same interface.

---

## AD-016 — Quality tooling: ruff + mypy strict (core layers) + pytest-qt

**Status:** Accepted

**Reason:** Ruff covers lint+format; mypy strict runs over
domain/services/application (infrastructure is checked via import-following);
UI tests run offscreen (`QT_QPA_PLATFORM=offscreen`) so they execute in CI
on all OSes without a display server.

---

## AD-017 — Local API: per-session token, loopback-only, opt-in

**Status:** Accepted (v1.5 implementation)

**Decision:** Implemented exactly as AD-010 designed: `secrets.token_urlsafe(32)`
generated at container build, `X-API-Token` required everywhere except
`/api/health` (constant-time compare), confirmation semantics on destructive
operations, no CORS. Runs embedded (daemon thread, opt-in via Settings) or
standalone (`python -m app.api`). Verified by a dedicated API test suite and
a live boot smoke test.

## AD-018 — Backup verification: manifest + size/count comparison

**Status:** Accepted (v1.5)

**Context:** Spec §1.3-G requires verification; full SHA-256 hashing doubles
backup time on large data sets.

**Decision:** Every backup writes `manifest.json` (per-file sizes); the
verification pass re-stats each file against the manifest and marks the job
`verified`. Byte-level hashing remains an opt-in future enhancement behind
the same interface. Cancellation removes only the partial directory the run
created; originals and previous backups are never touched.

## AD-019 — Session-per-operation repositories

**Status:** Accepted (v0.6, retained at v1.5)

**Context:** Services run on worker threads (monitor rounds, scans, API) —
a shared SQLAlchemy session is not thread-safe.

**Decision:** Every repository method opens its own short session over the
WAL-enabled engine. Concurrency is modest (single user) and SQLite WAL
handles it; this also future-proofs the PostgreSQL path.


---

## AD-020 — PDF export via reportlab (v1.6)

**Status:** Accepted

**Context:** Reports needed PDF; the alternative (QTextDocument→QPrinter)
would drag the Qt GUI stack into the headless API process.

**Decision:** `reportlab` (BSD, pure Python) inside the shared
`ExportService` writer — one `_write_pdf` path serves every report, scan,
and log-analysis export, in the app and the API alike. Branded, paginated
tables (wrapped cells, repeating header row); no GUI dependency.

## AD-021 — Toast notifications via bus→signal bridge (v1.6)

**Status:** Accepted

**Decision:** Domain events are published on the in-process `EventBus` from
worker threads; a small `EventBusBridge` (QObject) re-emits them as Qt
signals (queued to the main thread). `ToastManager` stacks in-app cards
(bottom-right, severity-colored, auto-dismiss); `QSystemTrayIcon` delivers
desktop messages for warning/critical. Both channels are settings-gated
(notifications.in_app / desktop).
