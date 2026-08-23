# Testing

## Commands

```bash
pytest                          # full suite (UI offscreen), warning-clean
pytest --ignore=tests/ui        # headless run — UI modules not collected
pytest tests/unit      # domain + services with fakes
pytest tests/api       # local FastAPI service (TestClient)
ruff format --check . && ruff check .   # lint + format gates
mypy                   # strict typing over domain/services/application
python -m app.main --selftest          # headless core verification
```

`pytest -m "not ui"` deselects UI tests but still *collects* them (PySide6
import required) — use `--ignore=tests/ui` on headless machines. The suite
runs warning-clean; the single filtered warning is a third-party
fastapi/starlette import notice, matched narrowly by message in
`pyproject.toml` with the reason documented inline.

CI (`.github/workflows/ci.yml`) runs all of the above on every push and PR
across ubuntu-latest (py3.12, py3.13) and windows-latest (py3.12).

## Suite shape (v1.5)

| Layer | What it proves |
|---|---|
| `tests/unit` | Pure domain logic: validators, parsers (3 log formats + fallback), message normalization, threshold classification, formatters, settings model round-trips, event bus, cancellation, sanitization, backup sizing math via fakes, monitor state machine |
| `tests/integration` | Real SQLite + Alembic migrations, all repositories (CRUD, history queries, retention pruning), monitoring/alert/disk service flows, backup happy/failure/cancel paths, scheduler ticks (devices, snapshots, scheduled backups), psutil adapter contracts, real `ping` subprocess behavior (skipped gracefully where ICMP is forbidden) |
| `tests/ui` | Offscreen Qt: shell navigation, theme switching, settings persistence, dashboard KPI/chart updates + snapshot cadence, monitoring CRUD + checks + history chart, alerts acknowledge flow, log analysis flow, network scan flow + export, reports generation |
| `tests/api` | Token enforcement on every route, wrong-token rejection, all endpoint groups through the real service layer, validation errors, destructive-op confirmations |

## Conventions

- **Fakes, not mocks**: test doubles implement domain Protocols
  (`tests/fakes.py`) — deterministic pingers, stores, and sources.
- **No sleeps for logic**: async UI flows use `qtbot.waitUntil`/`waitSignal`;
  scheduler tests drive `tick_once()` directly.
- **Honest skips**: ICMP-dependent integration tests skip with a clear
  reason where the environment forbids them; they run on Windows CI.
- **Regression before release**: full suite + lint + types + selftest must
  be green on all platforms before tagging (see deployment.md).

## Coverage philosophy

Happy path, failure path, and edge cases per feature (Master Spec §37):
invalid inputs, mid-operation cancellation, corruption fallbacks (settings),
unwritable destinations (exports), duplicate names, threshold boundaries,
locale-tolerant ping parsing, and teardown/thread-safety races (a real
abort-causing race was found and fixed this way in v0.4).
