"""Integration tests — repositories and services against a real SQLite DB."""

from __future__ import annotations

from app.application.container import AppContainer
from app.domain.entities import ActivityStatus
from app.domain.events import Topics
from app.domain.sanitization import sanitize_text
from app.infrastructure.db.models import ActivityLogModel, SettingModel


class TestActivityRepository:
    def test_append_assigns_id_and_persists(self, container: AppContainer):
        entry = container.activity_service.record(
            "test.action", module="tests", status=ActivityStatus.SUCCESS, message="hello"
        )
        assert entry.id is not None
        stored = container.activity_service.recent(limit=1)
        assert stored[0].action == "test.action"
        assert stored[0].status is ActivityStatus.SUCCESS

    def test_recent_orders_newest_first(self, container: AppContainer):
        for index in range(5):
            container.activity_service.record(f"action.{index}", module="tests")
        entries = container.activity_service.recent(limit=3)
        assert [e.action for e in entries] == ["action.4", "action.3", "action.2"]

    def test_message_sanitized_before_persistence(self, container: AppContainer):
        container.activity_service.record(
            "login.attempt", module="tests", message="password=supersecret failed"
        )
        session = container.new_session()
        try:
            row = session.query(ActivityLogModel).order_by(ActivityLogModel.id.desc()).first()
        finally:
            session.close()
        assert row is not None and "supersecret" not in (row.message or "")
        assert sanitize_text(row.message or "") == row.message

    def test_blank_action_rejected(self, container: AppContainer):
        try:
            container.activity_service.record("", module="tests")
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")


class TestSettingsRoundtrip:
    def test_full_roundtrip_through_service(self, container: AppContainer):
        service = container.settings_service
        service.update(
            {
                "theme": "dark",
                "disk": {"warning_percent": 70, "critical_percent": 85},
                "monitoring": {"interval_seconds": 45},
            }
        )

        # Prove persistence by rebuilding a fresh service on the same DB.
        from app.domain.events import EventBus
        from app.infrastructure.db.repositories import SettingRepository
        from app.services.settings_service import SettingsService

        session = container.new_session()
        try:
            fresh = SettingsService(SettingRepository(session), EventBus())
            settings = fresh.get()
            assert settings.theme.value == "dark"
            assert settings.disk.warning_percent == 70
            assert settings.monitoring.interval_seconds == 45
        finally:
            session.close()

    def test_settings_document_is_valid_json(self, container: AppContainer):
        import json

        container.settings_service.update({"theme": "light"})
        session = container.new_session()
        try:
            row = session.get(SettingModel, "app.settings")
        finally:
            session.close()
        assert row is not None
        parsed = json.loads(row.value)
        assert parsed["theme"] == "light"


class TestEventWiring:
    def test_settings_update_publishes_on_shared_bus(self, container: AppContainer):
        seen = []
        container.bus.subscribe(Topics.SETTINGS_CHANGED, seen.append)
        container.settings_service.update({"retention_days": 14})
        assert seen and "retention_days" in seen[0].fields
