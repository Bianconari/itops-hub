# Architecture

ITOps Hub is a layered desktop application with a Qt-free core, so the same
business services power the PySide6 UI (v1.0) and the local FastAPI service
(v1.5) without duplication.

## Layers

```
┌─────────────────────────────────────────────────────────────┐
│ PRESENTATION                                                 │
│  ┌───────────────────────┐        ┌───────────────────────┐ │
│  │  PySide6 Desktop UI   │        │  FastAPI local API    │ │
│  │  views · theme ·      │        │  (v1.5 — localhost,   │ │
│  │  workers (QThread)    │        │   token auth)         │ │
│  └──────────┬────────────┘        └───────────┬───────────┘ │
└─────────────┼─────────────────────────────────┼─────────────┘
              ▼                                 ▼
┌─────────────────────────────────────────────────────────────┐
│ APPLICATION — AppContainer (composition root), use cases,   │
│ background task orchestration, DTOs                          │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ SERVICES — system · network scan · monitoring · disk · logs │
│ backup · alerts · reports · activity · settings · scheduler │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ DOMAIN — entities · validation · event bus · cancellation · │
│ store Protocols (pure Python, no I/O)                        │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
         ┌────────────────────（implements Protocols）────────┐
         ▼ INFRASTRUCTURE                                    │
           SQLAlchemy repositories (SQLite WAL, Alembic) ·    │
           psutil/OS adapters · safe-subprocess ping/ARP ·    │
           filesystem adapters · sanitizing logging           │
         ▼                                                    │
         SQLite · File System · OS APIs · Local network        │
```

## Rules

1. **Dependency direction is inward only.** UI/API → application → services
   → domain; infrastructure implements domain Protocols and is wired by the
   composition root (`app/application/container.py`).
2. **No business logic in UI widgets.** Views call services; services raise
   domain errors; views translate them to user-facing messages.
3. **No I/O in the domain.** Validators, entities, the event bus, and the
   cancel token are pure and unit-testable.
4. **Services never import Qt or FastAPI.** They are synchronous and
   cooperatively cancellable (`CancelToken`), so they run unchanged inside
   QThread workers and API endpoints alike.
5. **One stylesheet, two palettes.** All styling flows from
   `app/ui/theme/tokens.py` (light/dark) through a single QSS document.

## Concurrency

- Long operations run in QThread workers (UI) or FastAPI's threadpool (API).
- Fan-out work uses bounded `ThreadPoolExecutor`s inside services.
- Monitoring is scheduler-driven: a tick submits checks to the pool, results
  are persisted, and events are published on the thread-safe `EventBus`; the
  UI bridges to the Qt main thread via queued signals.

## Data flow example (settings)

```
SettingsView (form) ──update(dict)──▶ SettingsService
      SettingsService ──validate/merge──▶ AppSettings (Pydantic)
      SettingsService ──save_raw(json)──▶ SettingRepository ──▶ SQLite
      SettingsService ──publish──▶ EventBus[settings.changed] ──▶ UI/Alerts
      SettingsService ──record──▶ ActivityLogService ──▶ audit trail
```

## Module map (current state)

| Area | Status | Where |
|---|---|---|
| Composition root, container | v0.3 ✅ | `app/application/container.py` |
| Settings model + service | v0.3 ✅ | `app/config/settings.py`, `app/services/settings_service.py` |
| Activity/audit log | v0.3 ✅ | `app/services/activity_service.py` |
| DB schema (all 7 tables) + migrations | v0.3 ✅ | `app/infrastructure/db/` |
| Theme system (light/dark) | v0.3 ✅ | `app/ui/theme/` |
| Shell + navigation + functional Settings page | v0.3 ✅ | `app/ui/main_window/`, `app/ui/views/` |
| System info + Dashboard | v0.4 (M3) | planned |
| Network scanner | v0.5 (M4) | planned |
| Monitoring / Disk / Alerts | v0.6 (M5) | planned |
| Log analyzer | v0.7 (M6) | planned |
| Reports | v0.8 (M7) | planned |
| Backup manager + scheduling | v1.2–v1.3 (M9) | planned |
| Local FastAPI service | v1.5 (M10) | planned |

Full planning detail: `docs/planning/M1-discovery-and-architecture.md`.
