"""Shared pytest fixtures.

``QT_QPA_PLATFORM=offscreen`` is set before any Qt import so UI tests run
headless on Linux CI and in sandboxes.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from app.application.container import AppContainer
from app.config.paths import AppPaths


@pytest.fixture
def tmp_paths(tmp_path):
    """Isolated AppPaths pointing at a per-test directory."""
    return AppPaths.create(base=tmp_path / "itops-data")


@pytest.fixture
def container(tmp_paths):
    """Fully wired application core on an isolated database."""
    app_container = AppContainer.build(paths=tmp_paths, console=False)
    yield app_container
    app_container.close()
