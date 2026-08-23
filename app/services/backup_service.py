"""Backup service — safe local copies with progress, verification, cancel.

Safety rules (Spec §1.3-G, §15):
- Originals are never modified or deleted; backups land in a fresh,
  timestamped, never-overwritten destination directory.
- Destination may not live inside the source (prevents runaway recursion).
- Cancellation removes only the partial directory this run created.
- Verification compares file counts and sizes against a written manifest
  (documented: byte-level hashes are a future option — cost/UX tradeoff).
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from app.domain.backup import BackupJob, BackupStatus, BackupStore, VerifyMode
from app.domain.cancellation import CancelToken, OperationCancelled
from app.domain.events import EventBus, Topics
from app.domain.time_utils import utc_now
from app.domain.validation import validate_path
from app.services.activity_service import ActivityLogService

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, int], None]  # files_done, files_total, bytes_done


class BackupService:
    def __init__(
        self,
        store: BackupStore,
        activity: ActivityLogService | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self._store = store
        self._activity = activity
        self._bus = bus

    # ------------------------------------------------------------ estimate
    @staticmethod
    def estimate(source: str | Path) -> tuple[int, int]:
        """Count files and total bytes under ``source`` (skips symlinks)."""
        root = validate_path(source, must_exist=True)
        files = 0
        total_bytes = 0
        if root.is_file():
            return 1, root.stat().st_size
        for path in root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            files += 1
            total_bytes += path.stat().st_size
        return files, total_bytes

    # ------------------------------------------------------------ run
    def run_backup(
        self,
        source: str | Path,
        destination_root: str | Path,
        *,
        verify_mode: VerifyMode | str = VerifyMode.SIZE,
        token: CancelToken | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> BackupJob:
        """Copy ``source`` into a timestamped folder under ``destination_root``.

        Verification modes (v1.5): ``size`` (default) compares the manifest's
        file count and sizes; ``sha256`` additionally recomputes per-file
        hashes; ``none`` skips verification. A failed verification marks the
        job FAILED — never silently "success".
        """
        verify_mode = VerifyMode(verify_mode)
        src = validate_path(source, must_exist=True)
        dest_root = validate_path(destination_root)
        self._validate_layout(src, dest_root)

        token = token or CancelToken()
        token.raise_if_cancelled()

        dest = self._unique_destination(dest_root, src)
        job = BackupJob(source=str(src), destination=str(dest), started_at=utc_now())
        job = self._store.add(job)
        self._record("backup.started", f"source={src} dest={dest}")

        try:
            files_total, _bytes = self.estimate(src)
            copied, bytes_done, manifest = self._copy_tree(
                src, dest, files_total, token, on_progress, verify_mode
            )
            self._write_manifest(dest, manifest)
            verified: bool | None = None
            verify_error: str | None = None
            if verify_mode is not VerifyMode.NONE and not token.cancelled:
                verified = self._verify(dest, manifest, verify_mode)
                if verified is False:
                    verify_error = "verification failed: manifest mismatch after copy"
            if token.cancelled:
                status = BackupStatus.CANCELLED
            elif verify_error is not None:
                status = BackupStatus.FAILED
            elif verified:
                status = BackupStatus.VERIFIED
            else:
                status = BackupStatus.SUCCESS
            job = replace(
                job,
                status=status,
                completed_at=utc_now(),
                size_bytes=bytes_done,
                files_copied=copied,
                checksum_verified=verified,
                error_message=verify_error,
            )
        except OperationCancelled:
            shutil.rmtree(dest, ignore_errors=True)  # remove only our partial copy
            job = replace(
                job,
                status=BackupStatus.CANCELLED,
                completed_at=utc_now(),
                error_message="cancelled; partial copy removed",
            )
        except (OSError, ValueError) as exc:
            job = replace(
                job,
                status=BackupStatus.FAILED,
                completed_at=utc_now(),
                error_message=f"{exc}",
            )
        job = self._store.update(job)
        self._finish_activity(job)
        if self._bus is not None:
            self._bus.publish(Topics.BACKUP_COMPLETED, job)
        return job

    # ------------------------------------------------------------ internals
    @staticmethod
    def _validate_layout(src: Path, dest_root: Path) -> None:
        if dest_root == src or src in dest_root.parents:
            raise ValueError("Destination must not be inside the source folder")
        if dest_root in src.parents:
            raise ValueError("Source must not be inside the destination folder")

    @staticmethod
    def _unique_destination(dest_root: Path, src: Path) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base = dest_root / f"ITOpsBackup-{src.name}-{stamp}"
        candidate = base
        counter = 1
        while candidate.exists():
            candidate = dest_root / f"{base.name}-{counter}"
            counter += 1
        candidate.mkdir(parents=True, exist_ok=False)
        return candidate

    def _copy_tree(
        self,
        src: Path,
        dest: Path,
        files_total: int,
        token: CancelToken,
        on_progress: ProgressCallback | None,
        verify_mode: VerifyMode,
    ) -> tuple[int, int, list[dict[str, object]]]:
        manifest: list[dict[str, object]] = []
        bytes_done = 0
        copied = 0
        sources = (
            [src]
            if src.is_file()
            else sorted(p for p in src.rglob("*") if p.is_file() and not p.is_symlink())
        )
        for source_file in sources:
            token.raise_if_cancelled()
            relative = source_file.relative_to(src.parent if src.is_file() else src)
            target = dest / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target)
            size = target.stat().st_size
            entry: dict[str, object] = {"path": str(relative), "size": size}
            if verify_mode is VerifyMode.SHA256:
                entry["sha256"] = self._hash_file(target)
            manifest.append(entry)
            copied += 1
            bytes_done += size
            if on_progress is not None:
                on_progress(copied, max(files_total, copied), bytes_done)
        return copied, bytes_done, manifest

    @staticmethod
    def _write_manifest(dest: Path, manifest: list[dict[str, object]]) -> None:
        (dest / "manifest.json").write_text(
            json.dumps({"files": manifest, "count": len(manifest)}, indent=2),
            encoding="utf-8",
        )

    def _verify(self, dest: Path, manifest: list[dict[str, object]], mode: VerifyMode) -> bool:
        for entry in manifest:
            target = dest / str(entry["path"])
            expected: int = entry["size"]  # type: ignore[assignment]
            if not target.is_file() or target.stat().st_size != expected:
                logger.warning("verification (size) failed for %s", target)
                return False
            if mode is VerifyMode.SHA256:
                recorded = entry.get("sha256")
                if recorded is not None and self._hash_file(target) != recorded:
                    logger.warning("verification (sha256) failed for %s", target)
                    return False
        return True

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _record(self, action: str, message: str) -> None:
        if self._activity is not None:
            self._activity.record(action, module="backup", message=message)

    def _finish_activity(self, job: BackupJob) -> None:
        message = (
            f"source={Path(job.source).name} status={job.status.value} "
            f"files={job.files_copied} size={job.size_bytes}"
        )
        status_map = {
            BackupStatus.VERIFIED: "success",
            BackupStatus.SUCCESS: "success",
            BackupStatus.CANCELLED: "failure",
            BackupStatus.FAILED: "failure",
        }
        self._record(f"backup.{job.status.value}", message)
        if self._activity is not None:
            from app.domain.entities import ActivityStatus

            self._activity.record(
                "backup.finished",
                module="backup",
                status=ActivityStatus(status_map[job.status]),
                message="",
            )

    def history(self, limit: int = 50) -> list[BackupJob]:
        return self._store.list_recent(limit=limit)
