# Publishing to GitHub

The repository is ready to publish (clean history, conventional commits,
CI workflows included). Two supported paths:

## Option A — from the git bundle (preserves all 28 commits)

Download `itops-hub.bundle` (single file, full history) and on your machine:

```bash
git clone itops-hub.bundle itops-hub
cd itops-hub
git remote set-url origin https://github.com/<your-user>/itops-hub.git
git push -u origin main
```

Create the empty repository first at
<https://github.com/new> (name `itops-hub`, **no** README/.gitignore/license —
they already exist), or with GitHub CLI:

```bash
gh repo create itops-hub --public --source . --remote origin --push
```

## Option B — fresh push without the bundle

Copy the project folder (or download the workspace as archive), then:

```bash
cd itops-hub
git remote add origin https://github.com/<your-user>/itops-hub.git
git push -u origin main
```

## After the first push

1. **CI runs automatically** (`ci.yml`): lint + strict types + 282 tests on
   ubuntu (py3.12/3.13) and windows (py3.12).
2. **Build the Windows artifacts** by tagging the release:

   ```bash
   git tag v1.5.0
   git push origin v1.5.0
   ```

   `build-windows.yml` then produces two Actions artifacts:
   `ITOpsHub-windows-x64` (portable app) and `ITOpsHub-Setup` (installer).
   Download from the repo's **Actions** tab → the workflow run → Artifacts.

3. (Optional) Create a GitHub **Release** for `v1.5.0` and attach
   `ITOpsHub-Setup.exe` so it is publicly downloadable.

## Repository hygiene already in place

- MIT `LICENSE`, complete `README.md`, `CHANGELOG.md`, docs set, CI badges
- `.gitignore` excludes runtime data, DBs, logs, build outputs, `.env`
- No secrets anywhere (verified by scan; pre-commit includes
  `detect-private-key`)
