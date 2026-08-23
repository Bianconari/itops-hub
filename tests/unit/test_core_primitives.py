"""Unit tests — sanitization, event bus, cancellation."""

from __future__ import annotations

import threading

from app.domain.cancellation import CancelToken, OperationCancelled
from app.domain.events import EventBus, Topics
from app.domain.sanitization import sanitize_text


class TestSanitizeText:
    def test_redacts_key_value_pairs(self):
        text = "login failed password=hunter2 attempt=1"
        assert "hunter2" not in (cleaned := sanitize_text(text))
        assert "password=***" in cleaned

    def test_redacts_common_keys(self):
        for key in ("api_key", "apiKey", "secret", "token", "authorization", "pwd"):
            cleaned = sanitize_text(f"{key}=abc123 reason=x")
            assert "abc123" not in cleaned

    def test_redacts_bearer_tokens(self):
        cleaned = sanitize_text("Authorization: Bearer eyJhbGciOi.payload.sig")
        assert "eyJhbGciOi" not in cleaned
        assert "***" in cleaned

    def test_preserves_normal_text(self):
        text = "Scan of 192.168.1.0/24 completed in 3.2s, 254 hosts checked"
        assert sanitize_text(text) == text

    def test_none_passthrough(self):
        assert sanitize_text(None) is None


class TestEventBus:
    def test_publish_reaches_subscribers(self):
        bus = EventBus()
        seen = []
        bus.subscribe("t", seen.append)
        bus.publish("t", 42)
        assert seen == [42]

    def test_unsubscribe(self):
        bus = EventBus()
        seen = []
        bus.subscribe("t", seen.append)
        bus.unsubscribe("t", seen.append)
        bus.publish("t", 1)
        assert seen == []

    def test_unknown_topic_is_noop(self):
        bus = EventBus()
        bus.publish(Topics.SETTINGS_CHANGED, None)  # must not raise

    def test_failing_subscriber_does_not_break_others(self):
        bus = EventBus()
        seen = []

        def bad(_payload):
            raise RuntimeError("boom")

        bus.subscribe("t", bad)
        bus.subscribe("t", seen.append)
        bus.publish("t", "x")
        assert seen == ["x"]

    def test_publish_from_worker_thread(self):
        bus = EventBus()
        seen: list[int] = []
        bus.subscribe("t", seen.append)
        thread = threading.Thread(target=lambda: bus.publish("t", 7))
        thread.start()
        thread.join(timeout=5)
        assert seen == [7]


class TestCancelToken:
    def test_initial_state_not_cancelled(self):
        assert not CancelToken().cancelled

    def test_cancel_is_sticky(self):
        token = CancelToken()
        token.cancel()
        assert token.cancelled
        token.cancel()
        assert token.cancelled

    def test_raise_if_cancelled(self):
        token = CancelToken()
        token.cancel()
        try:
            token.raise_if_cancelled()
        except OperationCancelled:
            pass
        else:
            raise AssertionError("expected OperationCancelled")

    def test_wait_returns_true_after_cancel(self):
        token = CancelToken()
        threading.Timer(0.05, token.cancel).start()
        assert token.wait(timeout=5)
