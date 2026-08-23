# Security Documentation

Security by design (Master Spec §15). This document is the v1.5 security
review record.

## Threat model summary

A single-user Windows desktop tool that reads local system state, scans
networks the user administers, and stores results locally. The local API is
an additional, loopback-only consumer of the same services.

## Controls implemented

### Input validation
- All user input is validated in the pure domain layer
  (`app/domain/validation.py`): CIDR networks, hosts/IPs, paths, thresholds.
  Pydantic validates settings and API bodies; failures never reach storage.
- API bodies are validated by FastAPI/Pydantic with strict schemas
  (`app/api/schemas.py`); domain `ValueError`s map to HTTP 400.

### Safe command execution
- The only subprocess usage is the OS `ping` and Windows `arp -a`, invoked
  with **argument lists, `shell=False`**, validated hosts, and bounded
  timeouts (`app/infrastructure/network/`). No string interpolation into
  commands anywhere in the codebase.
- `shell=True` is never used (grep-verified; ruff rule S603 reviewed at each
  call site with `noqa` justification comments).

### Path safety
- Backup destinations may not be inside sources and vice versa
  (`BackupService._validate_layout`); destinations are always fresh
  timestamped directories — originals are never modified or deleted.
- Exports never overwrite existing files (counter suffix).
- Path validation rejects empty/NUL paths; `must_exist` where appropriate.

### Network scanning
- Authorization guard: non-private CIDR ranges are refused unless the user
  explicitly confirms authorization (UI checkbox / API `"authorized": true`)
  while `scan_private_only` is enabled.
- Scan size cap (`scan_max_hosts`, default 1024) bounds every scan.
- Only reachability/ARP-cache data is collected — no vulnerability probing,
  no OS fingerprinting, no offensive capability.

### Local API (AD-010)
- Loopback-only default binding; per-session 32-byte token; constant-time
  comparison; confirmation semantics on destructive endpoints; no CORS.
- Documented residual risk: any local process under the same user can read
  the token file. Acceptable for a single-user workstation tool; documented
  for future multi-user review.

### Secrets & logging
- The application handles **no credentials by design** — nothing to leak.
- Defense-in-depth sanitization: `app/domain/sanitization.py` redacts
  key=value credential patterns and Bearer tokens from every log record
  (rotating file handler) and from audit-trail messages before persistence.
- CI runs `detect-private-key` pre-commit hook; repository secret scans are
  clean (verified each release).

### Data privacy
- No telemetry, no external API calls, no cloud upload. All data stays in
  `%LOCALAPPDATA%\ITOpsHub` (SQLite + logs) and the user's export folder.

## Review checklist (v1.5 — passed)

- [x] No `shell=True` anywhere; subprocess args are lists with validated inputs
- [x] No SQL string building — SQLAlchemy parameterized queries only
- [x] No secrets/credentials in repository or code (automated scan)
- [x] User-provided paths validated; destructive ops require confirmation
- [x] API loopback-only + token + confirm semantics; tests enforce all of it
- [x] Logs sanitized; audit trail sanitized
- [x] Dependencies pinned with `>=` floors from mainstream sources (PyPI)
- [x] Uninstaller preserves user data; app never deletes user originals

## Known residual risks (accepted, documented)

1. Unsigned executables → SmartScreen warning on first install (budget: AD).
2. Token file readable by same-user processes (single-user model).
3. System `ping` latency parsing is locale-dependent → response times may be
   omitted on non-English Windows; reachability is unaffected (AD-009).
