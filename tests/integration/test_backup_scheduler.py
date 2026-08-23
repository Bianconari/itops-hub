"""Integration tests — backup service, scheduler ticks, settings portability."""

from __future__ import annotations

import json
import pathlib

import pytest
from app.application.container import AppContainer
from app.config.settings import AppSettings
from app.domain.backup import BackupStatus
from app.domain.cancellation import CancelToken
from app.services.backup_service import BackupService
from app.services.settings_service import SettingsService
from tests.fakes import FakePinger


@pytest.fixture
def source_tree(tmp_path):
    source = tmp_path / "projects"
    (source / "docs").mkdir(parents=True)
    (source / "report.txt").write_text("hello " * 100)
    (source / "docs" / "deep.txt").write_text("world" * 200)
    (source / "empty.bin").write_bytes(b"\x00" * 1024)
    return source


@pytest.fixture
def backup(container: AppContainer) -> BackupService:
    assert container.backup_service is not None
    return container.backup_service


class TestBackupService:
    def test_estimate_counts_files_and_bytes(self, backup, source_tree):
        files, total_bytes = backup.estimate(source_tree)
        assert files == 3
        assert (
            total_bytes
            == (source_tree / "report.txt").stat().st_size
            + (source_tree / "docs" / "deep.txt").stat().st_size
            + 1024
        )

    def test_run_backup_copies_and_verifies(self, backup, source_tree, tmp_path):
        dest_root = tmp_path / "backups"
        job = backup.run_backup(source_tree, dest_root, verify_mode="size")
        assert job.status is BackupStatus.VERIFIED
        assert job.files_copied == 3
        assert job.error_message is None
        backup_dir = __import__("pathlib").Path(job.destination)
        assert (backup_dir / "report.txt").exists()
        assert (backup_dir / "docs" / "deep.txt").exists()
        manifest = json.loads((backup_dir / "manifest.json").read_text())
        assert manifest["count"] == 3
        assert backup_dir.parent == dest_root

    def test_single_file_backup(self, backup, source_tree, tmp_path):
        job = backup.run_backup(
            source_tree / "report.txt", tmp_path / "backups", verify_mode="size"
        )
        assert job.status is BackupStatus.VERIFIED
        assert job.files_copied == 1

    def test_destination_inside_source_rejected(self, backup, source_tree):
        with pytest.raises(ValueError, match="inside the source"):
            backup.run_backup(source_tree, source_tree / "nested")

    def test_missing_source_rejected(self, backup, tmp_path):
        with pytest.raises(ValueError):
            backup.run_backup(tmp_path / "nope", tmp_path / "backups")

    def test_never_overwrites_previous_backup(self, backup, source_tree, tmp_path):
        first = backup.run_backup(source_tree, tmp_path / "backups")
        (source_tree / "report.txt").write_text("changed")
        second = backup.run_backup(source_tree, tmp_path / "backups")
        assert first.destination != second.destination
        assert __import__("pathlib").Path(first.destination).exists()

    def test_cancellation_removes_partial_copy(self, backup, source_tree, tmp_path):
        dest_root = tmp_path / "backups"
        token = CancelToken()
        seen = []

        def on_progress(done, total, bytez):
            seen.append(done)
            if done >= 1:
                token.cancel()

        job = backup.run_backup(source_tree, dest_root, token=token, on_progress=on_progress)
        assert job.status is BackupStatus.CANCELLED
        leftovers = list(dest_root.glob("ITOpsBackup-*")) if dest_root.exists() else []
        assert leftovers == [], "partial backup must be removed on cancel"
        jobs = backup.history()
        assert jobs[0].status is BackupStatus.CANCELLED

    def test_sha256_mode_records_hashes_and_verifies(self, backup, source_tree, tmp_path):
        job = backup.run_backup(source_tree, tmp_path / "backups", verify_mode="sha256")
        assert job.status is BackupStatus.VERIFIED
        manifest = json.loads((pathlib.Path(job.destination) / "manifest.json").read_text())
        assert all("sha256" in entry for entry in manifest["files"])
        assert len(manifest["files"][0]["sha256"]) == 64

    def test_tampered_copy_fails_verification(self, backup, source_tree, tmp_path):
        job = backup.run_backup(source_tree, tmp_path / "backups", verify_mode="sha256")
        assert job.status is BackupStatus.VERIFIED
        dest = pathlib.Path(job.destination)
        manifest = json.loads((dest / "manifest.json").read_text())

        # corrupt one copied file -> verification must report failure
        victim = dest / manifest["files"][0]["path"]
        victim.write_bytes(b"tampered")
        from app.domain.backup import VerifyMode

        assert backup._verify(dest, manifest["files"], VerifyMode.SHA256) is False
        assert backup._verify(dest, manifest["files"], VerifyMode.SIZE) is False

        # restore original bytes -> verification passes again (sha matches)
        original = pathlib.Path(job.source) / manifest["files"][0]["path"]
        victim.write_bytes(original.read_bytes())
        assert backup._verify(dest, manifest["files"], VerifyMode.SHA256) is True

    def test_none_mode_skips_verification(self, backup, source_tree, tmp_path):
        job = backup.run_backup(source_tree, tmp_path / "backups", verify_mode="none")
        assert job.status is BackupStatus.SUCCESS
        assert job.checksum_verified is None

    def test_invalid_mode_rejected(self, backup, source_tree, tmp_path):
        with pytest.raises(ValueError):
            backup.run_backup(source_tree, tmp_path / "backups", verify_mode="md5")

    def test_history_recorded(self, backup, source_tree, tmp_path):
        backup.run_backup(source_tree, tmp_path / "backups")
        jobs = backup.history()
        assert len(jobs) == 1
        assert jobs[0].status is BackupStatus.VERIFIED


class TestScheduler:
    def test_tick_checks_due_devices(self, container: AppContainer):
        assert container.scheduler_service is not None
        assert container.monitor_service is not None
        container.monitor_service._pinger = FakePinger(reachable={"127.0.0.1"}, latency=15.0)
        device = container.monitor_service.add_device("Sched", "127.0.0.1", 30, 800)

        container.scheduler_service.tick_once()
        # pool is async — wait briefly for the submitted check to land
        import time

        deadline = time.time() + 5
        rows = []
        while time.time() < deadline:
            rows = container.monitor_service.status_rows()
            if rows and rows[0].last_result is not None:
                break
            time.sleep(0.05)
        assert rows[0].last_result is not None
        assert rows[0].device.id == device.id

    def test_tick_records_snapshot(self, container: AppContainer):
        assert container.scheduler_service is not None
        assert container.snapshot_service is not None
        before = len(container.snapshot_service.history(hours=1))
        container.scheduler_service.tick_once()
        import time

        deadline = time.time() + 5
        while time.time() < deadline:
            if len(container.snapshot_service.history(hours=1)) > before:
                break
            time.sleep(0.05)
        assert len(container.snapshot_service.history(hours=1)) > before

    def test_tick_runs_scheduled_backup_profile(
        self, container: AppContainer, source_tree, tmp_path
    ):
        assert container.scheduler_service is not None
        assert container.settings_service is not None
        container.settings_service.update(
            {
                "backup_profiles": [
                    {
                        "name": "projects",
                        "source": str(source_tree),
                        "destination": str(tmp_path / "scheduled"),
                        "interval_hours": 24,
                        "enabled": True,
                        "verify": True,
                    }
                ]
            }
        )
        container.scheduler_service.tick_once()
        import time

        deadline = time.time() + 15
        ran = False
        while time.time() < deadline:
            if list((tmp_path / "scheduled").glob("ITOpsBackup-*")):
                ran = True
                break
            time.sleep(0.1)
        assert ran, "scheduled backup did not run"

    def test_start_stop_lifecycle(self, container: AppContainer):
        assert container.scheduler_service is not None
        container.scheduler_service.start()
        assert container.scheduler_service.running
        container.scheduler_service.stop()
        assert not container.scheduler_service.running


class TestSettingsPortability:
    def test_export_import_roundtrip(self, container: AppContainer, tmp_path):
        assert container.settings_service is not None
        service: SettingsService = container.settings_service
        service.update({"theme": "dark", "disk": {"warning_percent": 70}})
        target = tmp_path / "settings-export.json"
        service.export_to(target)

        service.update({"theme": "light", "disk": {"warning_percent": 80}})
        imported = service.import_from(target)
        assert imported.theme.value == "dark"
        assert imported.disk.warning_percent == 70
        assert service.get().theme.value == "dark"

    def test_import_invalid_file_rejected(self, container: AppContainer, tmp_path):
        assert container.settings_service is not None
        bad = tmp_path / "bad.json"
        bad.write_text("{broken")
        with pytest.raises(ValueError, match="Invalid settings file"):
            container.settings_service.import_from(bad)

    def test_backup_profiles_validate(self):
        with pytest.raises(ValueError):
            AppSettings(backup_profiles=[{"name": "", "source": "/x", "destination": "/y"}])
        settings = AppSettings(
            backup_profiles=[
                {"name": "ok", "source": "/x", "destination": "/y", "interval_hours": 12}
            ]
        )
        assert settings.backup_profiles[0].interval_hours == 12
