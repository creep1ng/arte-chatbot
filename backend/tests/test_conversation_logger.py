"""Unit tests for the conversation_logger.py module.

Tests the ConversationLogEntry model and ConversationLogger class
that writes structured JSON conversation logs to S3 asynchronously.
"""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from backend.app.conversation_logger import ConversationLogEntry, ConversationLogger


# ---------------------------------------------------------------------------
# ConversationLogEntry model tests
# ---------------------------------------------------------------------------


class TestConversationLogEntry:
    """Tests for the ConversationLogEntry Pydantic model."""

    def test_creates_with_all_fields(self) -> None:
        """ConversationLogEntry accepts all required fields."""
        entry = ConversationLogEntry(
            session_id="abc-123",
            turn_number=1,
            timestamp="2026-05-07T20:39:00Z",
            user_message="¿Cuántos paneles necesito?",
            bot_response="Depende de tu consumo...",
            intent_type="FAQ",
            escalate=False,
            source_documents=["paneles/jinko.pdf"],
            input_tokens=150,
            output_tokens=80,
            total_tokens=230,
            response_time_ms=1234.5,
            model="gpt-5.4-nano",
            git_commit_hash="abc1234",
        )
        assert entry.session_id == "abc-123"
        assert entry.turn_number == 1
        assert entry.intent_type == "FAQ"
        assert entry.escalate is False
        assert entry.source_documents == ["paneles/jinko.pdf"]
        assert entry.input_tokens == 150
        assert entry.user_profile is None

    def test_user_profile_defaults_to_none(self) -> None:
        """user_profile field defaults to None when not provided."""
        entry = ConversationLogEntry(
            session_id="s1",
            turn_number=1,
            timestamp="2026-05-07T20:39:00Z",
            user_message="hola",
            bot_response="hola",
            intent_type="FAQ",
            escalate=False,
            source_documents=[],
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            response_time_ms=100.0,
            model="gpt-5.4-nano",
            git_commit_hash="",
        )
        assert entry.user_profile is None

    def test_redacts_sensitive_text_fields(self) -> None:
        """Sensitive values are redacted before conversation logs are persisted."""
        entry = ConversationLogEntry(
            session_id="s1",
            turn_number=1,
            timestamp="2026-05-07T20:39:00Z",
            user_message="Mi email es user@example.com y token=abc123",
            bot_response="La clave sk-testsecret123456 no debe verse",
            intent_type="FAQ",
            escalate=False,
            source_documents=[],
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            response_time_ms=100.0,
            model="gpt-5.4-nano",
            git_commit_hash="",
        )

        assert "user@example.com" not in entry.user_message
        assert "token=abc123" not in entry.user_message
        assert "sk-testsecret123456" not in entry.bot_response
        assert "[REDACTED]" in entry.user_message
        assert "[REDACTED]" in entry.bot_response

    def test_source_documents_defaults_to_empty_list(self) -> None:
        """source_documents defaults to empty list."""
        entry = ConversationLogEntry(
            session_id="s1",
            turn_number=1,
            timestamp="2026-05-07T20:39:00Z",
            user_message="hola",
            bot_response="hola",
            intent_type="FAQ",
            escalate=False,
            source_documents=[],
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            response_time_ms=100.0,
            model="gpt-5.4-nano",
            git_commit_hash="",
        )
        assert entry.source_documents == []

    def test_model_dump_json_produces_valid_json(self) -> None:
        """model_dump_json() produces valid JSON that handles special chars."""
        entry = ConversationLogEntry(
            session_id="s1",
            turn_number=1,
            timestamp="2026-05-07T20:39:00Z",
            user_message='He said "hello" and\nwent away',
            bot_response="Respuesta con 'comillas' y\nnuevas líneas",
            intent_type="FAQ",
            escalate=False,
            source_documents=[],
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            response_time_ms=500.0,
            model="gpt-5.4-nano",
            git_commit_hash="abc123",
        )
        json_str = entry.model_dump_json()
        parsed = json.loads(json_str)
        assert "hello" in parsed["user_message"]
        assert "\n" in parsed["user_message"]

    def test_model_dump_json_with_unicode(self) -> None:
        """model_dump_json() properly encodes Unicode characters."""
        entry = ConversationLogEntry(
            session_id="s1",
            turn_number=1,
            timestamp="2026-05-07T20:39:00Z",
            user_message="¿Cuántos paneles necesito para energía solar?",
            bot_response="¡Hola! Necesitas calcular tu consumo en kWh.",
            intent_type="FAQ",
            escalate=False,
            source_documents=[],
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            response_time_ms=500.0,
            model="gpt-5.4-nano",
            git_commit_hash="",
        )
        json_str = entry.model_dump_json()
        parsed = json.loads(json_str)
        assert "¿" in parsed["user_message"]
        assert "¡" in parsed["bot_response"]

    def test_with_user_profile(self) -> None:
        """ConversationLogEntry accepts user_profile when provided."""
        entry = ConversationLogEntry(
            session_id="s1",
            turn_number=1,
            timestamp="2026-05-07T20:39:00Z",
            user_message="hola",
            bot_response="hola",
            intent_type="FAQ",
            escalate=False,
            source_documents=[],
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            response_time_ms=100.0,
            model="gpt-5.4-nano",
            git_commit_hash="",
            user_profile="experto",
        )
        assert entry.user_profile == "experto"


# ---------------------------------------------------------------------------
# ConversationLogger tests
# ---------------------------------------------------------------------------


class TestConversationLogger:
    """Tests for the ConversationLogger class."""

    @pytest.fixture
    def mock_s3_client(self) -> MagicMock:
        """Create a mock S3Client with put_object."""
        mock = MagicMock()
        mock.put_object = MagicMock()
        return mock

    @pytest.fixture
    def logger_instance(self, mock_s3_client: MagicMock) -> ConversationLogger:
        """Create a ConversationLogger with a mock S3 client."""
        return ConversationLogger(
            s3_client=mock_s3_client,
            bucket="test-bucket",
            prefix="conversations",
        )

    @staticmethod
    def _make_entry(
        session_id: str = "abc-123",
        turn_number: int = 1,
        timestamp: str = "2026-05-07T20:39:00Z",
    ) -> ConversationLogEntry:
        """Helper to create a minimal ConversationLogEntry."""
        return ConversationLogEntry(
            session_id=session_id,
            turn_number=turn_number,
            timestamp=timestamp,
            user_message="test question",
            bot_response="test answer",
            intent_type="FAQ",
            escalate=False,
            source_documents=[],
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            response_time_ms=100.0,
            model="gpt-5.4-nano",
            git_commit_hash="abc123",
        )

    def test_upload_builds_correct_s3_key(
        self,
        logger_instance: ConversationLogger,
        mock_s3_client: MagicMock,
    ) -> None:
        """_upload builds S3 key as {prefix}/{session_id}/{turn_number}_{timestamp}.json."""
        entry = self._make_entry(
            session_id="session-xyz",
            turn_number=3,
            timestamp="2026-05-07T20:39:00Z",
        )

        logger_instance._upload(entry)

        expected_key = "conversations/session-xyz/3_2026-05-07T20:39:00Z.json"
        mock_s3_client.put_object.assert_called_once()
        call_kwargs = mock_s3_client.put_object.call_args[1]
        assert call_kwargs["key"] == expected_key

    def test_upload_passes_json_bytes_to_put_object(
        self,
        logger_instance: ConversationLogger,
        mock_s3_client: MagicMock,
    ) -> None:
        """_upload calls put_object with entry.model_dump_json().encode('utf-8')."""
        entry = self._make_entry()

        logger_instance._upload(entry)

        call_kwargs = mock_s3_client.put_object.call_args[1]
        data = call_kwargs["data"]
        assert isinstance(data, bytes)
        parsed = json.loads(data)
        assert parsed["session_id"] == "abc-123"
        assert parsed["turn_number"] == 1

    def test_upload_sets_content_type_json(
        self,
        logger_instance: ConversationLogger,
        mock_s3_client: MagicMock,
    ) -> None:
        """_upload passes content_type='application/json'."""
        entry = self._make_entry()
        logger_instance._upload(entry)

        call_kwargs = mock_s3_client.put_object.call_args[1]
        assert call_kwargs["content_type"] == "application/json"

    def test_upload_raises_on_s3_failure(
        self,
        mock_s3_client: MagicMock,
    ) -> None:
        """_upload propagates S3UploadError when put_object fails."""
        from backend.app.s3_client import S3UploadError

        mock_s3_client.put_object.side_effect = S3UploadError("upload failed")
        conv_logger = ConversationLogger(
            s3_client=mock_s3_client,
            bucket="test-bucket",
            prefix="conversations",
        )
        entry = self._make_entry()

        with pytest.raises(S3UploadError):
            conv_logger._upload(entry)

    def test_log_turn_calls_upload(
        self,
        logger_instance: ConversationLogger,
        mock_s3_client: MagicMock,
    ) -> None:
        """log_turn calls _upload and completes successfully."""
        entry = self._make_entry()

        asyncio.run(logger_instance.log_turn(entry))

        mock_s3_client.put_object.assert_called_once()

    def test_log_turn_silently_catches_upload_error(
        self,
        mock_s3_client: MagicMock,
    ) -> None:
        """log_turn catches all exceptions silently (logs warning, never raises)."""
        from backend.app.s3_client import S3UploadError

        mock_s3_client.put_object.side_effect = S3UploadError("upload failed")
        conv_logger = ConversationLogger(
            s3_client=mock_s3_client,
            bucket="test-bucket",
            prefix="conversations",
        )
        entry = self._make_entry()

        # Should NOT raise
        asyncio.run(conv_logger.log_turn(entry))

    def test_log_turn_silently_catches_unexpected_error(
        self,
        mock_s3_client: MagicMock,
    ) -> None:
        """log_turn catches unexpected exceptions (not just S3 errors)."""
        mock_s3_client.put_object.side_effect = RuntimeError("boom")
        conv_logger = ConversationLogger(
            s3_client=mock_s3_client,
            bucket="test-bucket",
            prefix="conversations",
        )
        entry = self._make_entry()

        # Should NOT raise
        asyncio.run(conv_logger.log_turn(entry))
