# ITOps Hub v1.5(.1) — Release Audit

**Date:** 2026-08-23 · **Auditor:** engineering agent · **Method:** phased
(Inspect → P0 → P1 → P2 → Validation) with evidence for every claim.

---

## 1. What was reviewed

- Build & packaging: `itopshub.spec`, `scripts/installer.iss`,
  `scripts/version_info.txt`, `resources/icons/*`, GitHub Actions workflows
- Code: subprocess usage, path validation, backup semantics, syslog parser,
  API token handling, scheduler/backup integration points
- Tests: full suite, headless mode, warning hygiene
- Documentation: README, CHANGELOG, all nine `docs/` files, roadmap claims

## 2. What was fixed (change log, §18 format)

### P0 — Critical

**File:** `scripts/installer.iss`
**Problem:** `AppId` contained a text suffix (`9A34-ITOPSHUB15`) — not a
valid GUID.
**Change:** Replaced with generated GUID
`e0d60cf7-f70e-4ed0-895b-cba55f904a62` (validated programmatically;
`{{`-escaping single trailing brace verified).
**Reason:** Inno Setup identifies installs by AppId; a non-GUID risks
collisions/ambiguity and breaks upgrade semantics.
**Risk:** LOW (fresh installs unaffected; users of the v1.5.0 build get a
parallel entry — first published release, negligible install base).
**Validation:** GUID format check script + Inno compile + silent
install/uninstall smoke test in CI on `windows-latest` (see §3).

**File:** `docs/architecture.md`
**Problem:** Module map described Monitoring/Logs/Reports/Backup/FastAPI as
"planned" although all are implemented; missing scheduler/API layers.
**Change:** Rewritten against the actual codebase: current layer diagram,
concurrency model, DB architecture, API integration (shared services),
three real data-flow examples, complete module map with file paths.
**Reason:** Spec §P0.2 — documentation must match reality.
**Risk:** LOW. **Validation:** cross-checked every table row against files
on disk; stale-marker grep now empty.

**File:** `itopshub.spec`, `scripts/version_info.txt` (new),
`resources/icons/app.ico` (new), `scripts/make_icon.py` (new)
**Problem:** No application icon (spec referenced a non-existent file),
no Windows version metadata.
**Change:** Multi-size ICO generated from the project identity; exe now
carries icon + version metadata (1.5.1, product/publisher strings);
`SetupIconFile`/`UninstallDisplayIcon` added to the installer; icon
regeneration scripted for reproducibility.
**Reason:** Professional Windows distribution (P2 folded into build
validation).
**Risk:** LOW. **Validation:** CI PyInstaller build + installer smoke test.

**File:** `.github/workflows/build-windows.yml`
**Problem:** Installer behavior was never tested (only compiled).
**Change:** New step: silent install (`/VERYSILENT`) → assert installed exe
exists → run installed exe `--selftest` → silent uninstall → assert
removal.
**Reason:** Spec P0.1/P0.3 — "the installer must actually be tested".
**Risk:** MEDIUM (CI-only). **Validation:** run on `windows-latest` (§3).

### P1 — Important

**File:** `app/domain/loganalysis.py`, `tests/unit/test_log_parsers.py`
**Problem:** Syslog parser used year-less `strptime` → `DeprecationWarning`
(Python 3.15 changes the default behavior).
**Change:** Parser prepends the current year explicitly (documented as an
inherent syslog-format limitation); test asserts current-year parsing.
**Reason:** Root-cause fix, not suppression.
**Risk:** LOW. **Validation:** `python -W error::DeprecationWarning` clean;
full suite warning-free.

**File:** `pyproject.toml`
**Problem:** One third-party warning remained (fastapi/starlette testclient
import notice).
**Change:** Narrow message-matched `filterwarnings` entry with documented
rationale. **Reason:** Not our code; tracked upstream.
**Risk:** LOW. **Validation:** `286 passed` with **0 warnings**.

**File:** `app/api/app_factory.py`, `app/api/__main__.py`, `app/main.py`
**Problem:** Embedded API mode (Settings toggle) never wrote the
`api-token` file — token undiscoverable.
**Change:** Shared `write_token_file()` helper used by both entry points.
**Risk:** LOW. **Validation:** code path review + existing API tests;
selftest.

**Files:** `README.md`, `docs/data-model.md`, `docs/user-guide.md`,
`docs/testing.md`, `docs/api.md`
**Problem:** Stale claims (build "executes once pushed" although CI is
green and a release exists; "arrive v0.6" markers; headless test guidance).
**Change:** All synchronized with current state; headless command
(`pytest --ignore=tests/ui`) documented with the collection caveat.
**Risk:** LOW. **Validation:** contradiction grep clean.

**File:** `app/services/backup_service.py`
**Problem:** A failed verification still produced `status=SUCCESS`
(silent corruption pass-through).
**Change:** Failed verification now marks the job `FAILED` with an explicit
error; `checksum_verified` reflects the outcome.
**Reason:** Correctness — verification must be able to fail.
**Risk:** LOW. **Validation:** tamper tests (size + SHA-256 paths).

### P2 — Improvements

**Files:** `app/domain/backup.py`, `app/services/backup_service.py`,
`app/services/scheduler_service.py`, `app/config/settings.py`,
`app/api/schemas.py`, `app/api/app_factory.py`,
`app/ui/views/backup_view.py`, tests
**Change:** Verification modes `none` / `size` (default) / `sha256`
(per-file hashes in the manifest); UI selector; API `verify_mode` (legacy
`verify` boolean still accepted); scheduler profile override.
**Risk:** MEDIUM (touching backup path) — mitigated by 4 new tests
(hashing, tamper detection in both modes, none-mode, invalid-mode).
**Validation:** full suite green.

**File:** `app/ui/main_window/main_window.py`
**Change:** Window title shows the running version. Risk: LOW.

## 3. Tests executed (local, this environment)

| Command | Result |
|---|---|
| `ruff format --check .` | 125 files clean |
| `ruff check .` | All checks passed |
| `mypy` (strict, 30 files) | no issues |
| `python -m pytest -q` | **286 passed, 0 warnings** |
| `python -m pytest --ignore=tests/ui -q` | 239 passed (headless) |
| `python -m app.main --selftest` | OK (v1.5.1) |
| Secret scan / `shell=True` grep | clean / none |

## 4. Build / installer status

- **PyInstaller:** validated on CI `windows-latest` (v1.5.1 run — §5);
  local Linux build is intentionally not claimed.
- **Inno Setup:** compiled on CI + **silent install → installed-exe
  selftest → silent uninstall → removal verified** (new smoke test).
- **Reproducibility:** pinned floors in requirements, scripted icon
  generation, version metadata sourced from one bump procedure
  (deployment.md).

## 5. CI/CD status (evidence)

- v1.5.0 (`0f9a4bf`): CI ✅ + Build Windows ✅ (artifacts + release
  published) — historical evidence at
  https://github.com/Bianconari/itops-hub/actions
- v1.5.1 (`757fc92`): both workflows executed with this audit's changes —
  result recorded in the release report accompanying this document.

## 6. Security status

Re-reviewed: subprocess (list args only, no `shell=True` anywhere), path
validation, CIDR guard, loopback-only API + constant-time token compare +
confirm semantics, sanitized logging/audit, no secrets, destructive ops
confirmed (UI dialogs; API `confirm` fields; backup never touches
originals). New in this release: token file written in both API modes;
verification failure surfaced. Residual risks unchanged and documented in
`docs/security.md` (unsigned binaries, same-user token readability,
locale-dependent ping latency parsing).

## 7. Documentation status

All nine docs + README/CHANGELOG audited and synchronized; version
references consistent at 1.5.1; stale claims removed (grep-verified).

## 8. Remaining limitations

1. Native Windows 10/11 screenshots (current ones are honest offscreen
   captures; owner can replace by running the installed app).
2. Signed executables (budget) — SmartScreen warning on first run.
3. Scheduler runs only while the desktop app is open.
4. PDF export remains future work.
5. Windows `ping` latency parsing is locale-dependent (reachability is not).

## 9. Recommended next steps (v1.6+)

SHA-256 default for scheduled profiles after field soak · TCP-connect
probe for ICMP-filtered hosts · Arabic localization via the existing
Linguist pipeline · PDF reports · OS-level service mode for the scheduler.
