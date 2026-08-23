"""OS-appropriate filesystem locations for ITOps Hub.

Runtime data never lives inside the repository. On Windows the default base
directory is ``%LOCALAPPDATA%\\ITOpsHub``; on Linux/macOS the XDG data dir is
used. Tests and development runs inject an explicit base directory.

The ``ITOPS_HUB_DATA_DIR`` environment variable overrides the base directory
(same purpose as ``.env.example``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir, user_documents_dir

APP_NAME = "ITOpsHub"
ENV_DATA_DIR = "ITOPS_HUB_DATA_DIR"


@dataclass(frozen=True)
class AppPaths:
    """Resolved filesystem locations used by the application."""

    base: Path

    @classmethod
    def create(cls, base: Path | None = None) -> AppPaths:
        """Build paths from an explicit base, env override, or the OS default."""
        if base is None:
            env_base = os.environ.get(ENV_DATA_DIR, "").strip()
            base = Path(env_base) if env_base else None
        if base is None:
            base = Path(user_data_dir(APP_NAME, appauthor=False))
        return cls(base=base)

    @property
    def db_path(self) -> Path:
        return self.base / "itops.db"

    @property
    def log_dir(self) -> Path:
        return self.base / "logs"

    @property
    def log_file(self) -> Path:
        return self.log_dir / "itops-hub.log"

    @property
    def default_export_dir(self) -> Path:
        """Default directory for exported reports (Documents/ITOpsHub)."""
        try:
            documents = Path(user_documents_dir())
        except Exception:
            documents = Path.home()
        return documents / APP_NAME

    def ensure(self) -> None:
        """Create the runtime directories if they do not exist."""
        self.base.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
