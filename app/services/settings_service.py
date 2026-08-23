"""Settings service — load, validate, and update the settings document.

The stored document is a JSON string in the local SQLite settings table. On
any corruption or validation failure the service falls back to defaults
(logging a warning) rather than crashing — a desktop app must always start.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.config.settings import AppSettings
from app.domain.entities import ActivityStatus
from app.domain.events import EventBus, SettingsChanged, Topics
from app.domain.interfaces import SettingsStore
from app.domain.sanitization import sanitize_text
from app.services.activity_service import ActivityLogService

logger = logging.getLogger(__name__)

_DOCUMENT_KEY = "app.settings"


class SettingsService:
    """Typed façade over the raw settings store."""

    def __init__(
        self,
        store: SettingsStore,
        bus: EventBus,
        activity: ActivityLogService | None = None,
    ) -> None:
        self._store = store
        self._bus = bus
        self._activity = activity
        self._cached: AppSettings | None = None

    def get(self) -> AppSettings:
        """Current settings (defaults when nothing/invalid is stored)."""
        if self._cached is not None:
            return self._cached
        raw = self._store.load_raw()
        settings: AppSettings | None = None
        if raw:
            try:
                settings = AppSettings.model_validate(json.loads(raw))
            except (json.JSONDecodeError, ValueError):
                logger.warning("Stored settings are invalid; falling back to defaults")
        self._cached = settings or AppSettings()
        return self._cached

    def update(self, changes: Mapping[str, Any]) -> AppSettings:
        """Apply a (possibly nested, partial) change set and persist it.

        Raises ``pydantic.ValidationError`` when the merged result would be
        invalid — nothing is persisted in that case.
        """
        current = self.get()
        merged = _deep_merge(current.model_dump(mode="json"), dict(changes))
        new_settings = AppSettings.model_validate(merged)
        self._store.save_raw(json.dumps(new_settings.model_dump(mode="json"), indent=2))
        old = current
        self._cached = new_settings
        changed_fields = tuple(sorted(key for key in _leaf_differences(old, new_settings) if key))
        self._bus.publish(Topics.SETTINGS_CHANGED, SettingsChanged(fields=changed_fields))
        if self._activity is not None:
            summary = ", ".join(changed_fields) if changed_fields else "no effective change"
            self._activity.record(
                action="settings.updated",
                module="settings",
                status=ActivityStatus.SUCCESS,
                message=sanitize_text(f"Changed: {summary}") or None,
            )
        return new_settings

    # ------------------------------------------------------------ portability
    def export_to(self, path: str | Path) -> Path:
        """Write current settings to a JSON file (for transfer/backup)."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        document = {"application": "ITOps Hub", "settings": self.get().model_dump(mode="json")}
        target.write_text(json.dumps(document, indent=2), encoding="utf-8")
        if self._activity is not None:
            self._activity.record(
                "settings.exported", module="settings", message=f"file={target.name}"
            )
        return target

    def import_from(self, path: str | Path) -> AppSettings:
        """Validate and apply settings from an export file.

        Raises ValueError when the file is unreadable or invalid; nothing is
        applied in that case.
        """
        source = Path(path)
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
            payload = document.get("settings", document)
            new_settings = AppSettings.model_validate(payload)
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid settings file: {exc}") from exc
        except ValueError:
            raise
        return self.update(new_settings.model_dump(mode="json"))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into ``base`` (returns a new dict)."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], dict(value))
        else:
            result[key] = value
    return result


def _leaf_differences(old: AppSettings, new: AppSettings) -> set[str]:
    """Top-level setting keys whose values differ between two snapshots."""
    old_dump = old.model_dump()
    new_dump = new.model_dump()
    return {key for key in new_dump if new_dump[key] != old_dump.get(key)}
