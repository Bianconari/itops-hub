# Data Model

SQLite via SQLAlchemy 2.0 (WAL mode, foreign keys enforced). All timestamps
are naive UTC (`app/domain/time_utils.py`). Schema is created by the initial
Alembic migration (`app/infrastructure/db/alembic/versions/`) and evolves by
reviewable migrations only — never by ad-hoc DDL.

## Entity relationships

```
devices 1 ──── N monitoring_results   (CASCADE delete with device)
system_snapshots      (independent)
backup_jobs           (independent)
alerts                (independent)
activity_logs         (independent)
settings              (single JSON document, key = "app.settings")
```

## Tables

### devices — ping-monitored endpoints (live since v0.6)
| Column | Type | Constraints / Notes |
|---|---|---|
| id | INTEGER | PK |
| name | TEXT | NOT NULL, UNIQUE |
| host | TEXT | NOT NULL (IP or hostname, validated) |
| type | TEXT | NOT NULL, default `ping` |
| enabled | BOOLEAN | NOT NULL, default 1 |
| interval_seconds | INTEGER | NOT NULL, default 30 |
| timeout_ms | INTEGER | NOT NULL, default 1500 |
| created_at / updated_at | DATETIME | NOT NULL (UTC) |

### monitoring_results — one check per device (live since v0.6)
| Column | Type | Notes |
|---|---|---|
| id | INTEGER | PK |
| device_id | INTEGER | FK → devices.id ON DELETE CASCADE |
| timestamp | DATETIME | indexed with device_id (DESC-friendly composite) |
| status | TEXT | CHECK ∈ `online` / `offline` / `warning` |
| response_time_ms | REAL | NULL when unreachable |
| error_message | TEXT | NULL |

### system_snapshots — periodic local metrics (live since v0.4)
| Column | Type | Notes |
|---|---|---|
| id | INTEGER | PK |
| timestamp | DATETIME | indexed |
| cpu_percent | REAL | NULL allowed |
| memory_percent | REAL | NULL allowed |
| disk_percent | REAL | NULL allowed; highest usage across volumes |

### backup_jobs — backup executions (live since v1.2)
id PK · source TEXT · destination TEXT · started_at · completed_at NULL ·
status CHECK ∈ `running`/`success`/`verified`/`failed`/`cancelled` ·
size_bytes · files_copied · checksum_verified · error_message NULL

### alerts — threshold/state alerts (full lifecycle live since v0.6)
id PK · type TEXT · severity CHECK ∈ `info`/`warning`/`critical` · source
TEXT · message TEXT · created_at (indexed) · acknowledged BOOLEAN default 0 ·
acknowledged_at NULL

### activity_logs — audit trail (live since v0.3)
id PK · timestamp (indexed) · action · module · status CHECK ∈
`success`/`failure`/`info` · message (sanitized, truncated to 2000 chars)

### settings — single validated JSON document (live since v0.3)
key TEXT PK (`app.settings`) · value TEXT (JSON of `AppSettings`) · updated_at

## Retention (live since v0.4)

`SnapshotService.apply_retention(days)` prunes `system_snapshots` older than
the configured `retention_days` (default 30) on every application start.
Monitoring results follow the same rule (live since v0.6); alerts and audit
logs keep 90 days by default from v1.4.

## PostgreSQL path (v2.x)

Repositories implement domain Protocols (`app/domain/interfaces.py`); models
avoid SQLite-specific types, and Alembic migrations run in batch mode. Moving
to PostgreSQL is a dialect/connection change plus migration replay, not a
core rewrite (AD-007).
