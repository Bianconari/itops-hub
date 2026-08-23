"""Unit tests — settings model + service behavior."""

from __future__ import annotations

import dataclasses
import json

import pytest
from app.config.settings import AppSettings, Theme
from app.domain.events import EventBus, Topics
from app.services.settings_service import SettingsService
from pydantic import ValidationError


class FakeSettingsStore:
    def __init__(self, raw: str | None = None) -> None:
        self.raw = raw
        self.saved: str | None = None

    def load_raw(self) -> str | None:
        return self.raw

    def save_raw(self, document: str) -> None:
        self.saved = document
        self.raw = document


@pytest.fixture
def store():
    return FakeSettingsStore()


@pytest.fixture
def service(store):
    return SettingsService(store, EventBus())


class TestDefaults:
    def test_defaults_when_store_empty(self, service):
        settings = service.get()
        assert settings.theme is Theme.SYSTEM
        assert settings.disk.warning_percent == 80.0
        assert settings.disk.critical_percent == 90.0
        assert settings.api.host == "127.0.0.1"
        assert settings.scan_private_only is True

    def test_corrupt_json_falls_back_to_defaults(self, store, service):
        store.raw = "{not valid json"
        assert service.get() == AppSettings()

    def test_invalid_stored_model_falls_back_to_defaults(self, store, service):
        store.raw = json.dumps({"disk": {"warning_percent": 95, "critical_percent": 80}})
        assert service.get() == AppSettings()


class TestModel:
    def test_threshold_ordering_enforced(self):
        with pytest.raises(ValidationError):
            AppSettings(disk={"warning_percent": 95, "critical_percent": 80})

    def test_bad_log_level_rejected(self):
        with pytest.raises(ValidationError):
            AppSettings(log_level="LOUD")

    def test_extra_keys_ignored(self):
        settings = AppSettings.model_validate({"theme": "dark", "future_field": 1})
        assert settings.theme is Theme.DARK


class TestUpdates:
    def test_partial_update_persists_and_publishes(self, store, service):
        events = []
        service._bus.subscribe(Topics.SETTINGS_CHANGED, events.append)

        updated = service.update({"theme": "dark"})

        assert updated.theme is Theme.DARK
        assert store.saved is not None
        assert json.loads(store.saved)["theme"] == "dark"
        assert events and "theme" in events[0].fields

    def test_nested_update_merges(self, service):
        service.update({"monitoring": {"interval_seconds": 60}})
        service.update({"monitoring": {"timeout_ms": 2000}})
        settings = service.get()
        assert settings.monitoring.interval_seconds == 60
        assert settings.monitoring.timeout_ms == 2000

    def test_invalid_update_persists_nothing(self, service):
        with pytest.raises(ValueError):
            service.update({"disk": {"warning_percent": 95, "critical_percent": 80}})
        assert service.get().disk.warning_percent == 80.0
        assert service._store.saved is None

    def test_activity_recorded_on_update(self, store):
        from app.domain.entities import ActivityEntry
        from app.services.activity_service import ActivityLogService

        class FakeActivityStore:
            def __init__(self):
                self.entries: list[ActivityEntry] = []

            def append(self, entry: ActivityEntry) -> ActivityEntry:
                stored = dataclasses.replace(entry, id=len(self.entries) + 1)
                self.entries.append(stored)
                return stored

            def recent(self, limit: int = 100) -> list[ActivityEntry]:
                return list(reversed(self.entries))[:limit]

        activity = ActivityLogService(FakeActivityStore())
        service = SettingsService(store, EventBus(), activity)
        service.update({"theme": "light"})
        entries = activity.recent(1)
        assert entries and entries[0].action == "settings.updated"
