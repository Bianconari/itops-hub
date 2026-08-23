# Deployment & Build (Windows)

## Prerequisites

- Windows 10/11 x64
- Python 3.12+ (3.12/3.13 supported)
- For the installer: [Inno Setup 6](https://jrsoftware.org/isinfo.php)
  (installed automatically in CI via Chocolatey)

## Build the application

```powershell
git clone <repository-url>
cd itops-hub
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

# onedir windowed build -> dist\ITOpsHub\ITOpsHub.exe
pyinstaller itopshub.spec --noconfirm

# smoke test the packaged app (exit code 0 = healthy)
.\dist\ITOpsHub\ITOpsHub.exe --selftest
echo $LASTEXITCODE
```

## Build the installer

```powershell
iscc scripts\installer.iss     # -> dist\ITOpsHub-Setup.exe
```

## CI builds (recommended path)

`.github/workflows/build-windows.yml` runs on every `v*` tag (and on demand):
PyInstaller build → packaged selftest → Inno Setup installer → two artifacts
(`ITOpsHub-windows-x64`, `ITOpsHub-Setup`).

Release procedure:

```bash
# 1. ensure the full gate is green locally
./scripts/run_tests.sh

# 2. tag and push
git tag v1.5.0 && git push origin v1.5.0
# 3. download artifacts from GitHub Actions and attach to the GitHub release
```

## Installation

Run `ITOpsHub-Setup.exe`. Per-user data (SQLite, logs) is created on first
launch in `%LOCALAPPDATA%\ITOpsHub`; exports default to `Documents\ITOpsHub`.

Note: executables are unsigned (zero-cost budget, AD-008), so Windows
SmartScreen shows a warning on first run — choose *More info → Run anyway*.

## Upgrade

Install over the existing installation (same directory). The database is
migrated automatically on launch by Alembic (`run_migrations()` at startup);
user data lives outside the install directory and is untouched.

## Uninstall

Via *Apps & Features* / the uninstaller. The uninstaller removes only the
application files; `%LOCALAPPDATA%\ITOpsHub` (database + logs) is kept
deliberately — delete it manually if you want a full wipe.

## Runtime layout

| Path | Contents |
|---|---|
| `%LOCALAPPDATA%\ITOpsHub\itops.db` | SQLite database (WAL) |
| `%LOCALAPPDATA%\ITOpsHub\logs\` | rotating application logs |
| `%LOCALAPPDATA%\ITOpsHub\api-token` | per-session local API token |
| `Documents\ITOpsHub\` | default export destination |
