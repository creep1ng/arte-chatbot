"""
Unit tests for the user profile inference module.
"""

import pytest
from backend.app.user_profiler import (
    infer_user_profile,
    _extract_technical_score,
    _extract_specificity_score,
    _extract_acronym_score,
)
from backend.app.session import SessionManager


class TestExtractTechnicalScore:
    """Tests for the technical vocabulary scoring function."""

    def test_empty_text(self):
        """Test that empty text returns 0 score."""
        assert _extract_technical_score("") == 0.0

    def test_non_string_input(self):
        """Test that non-string input returns 0 score."""
        assert _extract_technical_score(None) == 0.0
        assert _extract_technical_score(123) == 0.0

    def test_generic_text(self):
        """Test generic text with no technical terms."""
        score = _extract_technical_score("¿Qué es esto?")
        assert score == 0.0

    def test_single_technical_term(self):
        """Test text with one technical term."""
        score = _extract_technical_score("Tengo un panel solar")
        assert score > 0.0
        assert score < 1.0

    def test_high_technical_density(self):
        """Test text with high technical term density."""
        score = _extract_technical_score("inversor mppt DC AC voltaje amperaje")
        assert score > 0.5

    def test_case_insensitivity(self):
        """Test that scoring is case-insensitive."""
        score1 = _extract_technical_score("panel inversor")
        score2 = _extract_technical_score("PANEL INVERSOR")
        assert score1 == score2


class TestExtractSpecificityScore:
    """Tests for the specificity scoring function."""

    def test_empty_text(self):
        """Test that empty text returns 0 score."""
        assert _extract_specificity_score("") == 0.0

    def test_generic_question(self):
        """Test generic question without specifics."""
        score = _extract_specificity_score("¿Cuánto cuesta un panel?")
        assert score == 0.0

    def test_power_rating(self):
        """Test text with power rating."""
        score = _extract_specificity_score("¿Cuánto cuesta un panel de 300W?")
        assert score > 0.0

    def test_temperature_specification(self):
        """Test text with temperature specification."""
        score = _extract_specificity_score("a 25°C")
        assert score > 0.0

    def test_brand_name(self):
        """Test text with brand name."""
        score = _extract_specificity_score("JinkoSolar 460W")
        assert score > 0.0

    def test_multiple_specificity_markers(self):
        """Test text with multiple specificity markers."""
        score = _extract_specificity_score(
            "¿cuál es el Voc del JinkoSolar 460W a 25°C?"
        )
        assert score > 0.3


class TestExtractAcronymScore:
    """Tests for the acronym/unit scoring function."""

    def test_empty_text(self):
        """Test that empty text returns 0 score."""
        assert _extract_acronym_score("") == 0.0

    def test_no_acronyms(self):
        """Test text without technical acronyms/units."""
        score = _extract_acronym_score("¿Qué es un panel?")
        assert score == 0.0

    def test_single_unit(self):
        """Test text with one technical unit."""
        score = _extract_acronym_score("300W")
        assert score > 0.0

    def test_multiple_units(self):
        """Test text with multiple technical units."""
        score = _extract_acronym_score("300W 25°C kWh")
        assert score > 0.2


class TestInferUserProfile:
    """Tests for the main profile inference function."""

    def test_empty_history(self):
        """Test that empty history returns 'intermedio' default."""
        profile = infer_user_profile([])
        assert profile == "intermedio"

    def test_novice_generic_question(self):
        """Test that generic question is classified as 'novato'."""
        history = [{"role": "user", "content": "¿Qué es un panel solar?"}]
        profile = infer_user_profile(history)
        assert profile == "novato"

    def test_expert_technical_parameters(self):
        """Test that technical parameters are classified as 'experto'."""
        history = [
            {
                "role": "user",
                "content": "¿cuál es el Voc del JinkoSolar 460W a 25°C?",
            }
        ]
        profile = infer_user_profile(history)
        assert profile == "experto"

    def test_intermediate_some_technical(self):
        """Test that some technical terms are classified as 'intermedio'."""
        history = [{"role": "user", "content": "¿Cuánto cuesta un panel de 300W?"}]
        profile = infer_user_profile(history)
        assert profile == "intermedio"

    def test_two_user_messages_combined(self):
        """Test that only first 2 user messages are analyzed."""
        history = [
            {"role": "user", "content": "¿Qué es un panel?"},
            {"role": "assistant", "content": "Es un dispositivo..."},
            {
                "role": "user",
                "content": "¿cuál es el Voc del JinkoSolar 460W a 25°C?",
            },
        ]
        profile = infer_user_profile(history)
        # Should be experto because second user message is technical
        assert profile == "experto"

    def test_three_user_messages_only_first_two(self):
        """Test that only first 2 user messages are considered."""
        history = [
            {"role": "user", "content": "¿Qué es un panel?"},
            {"role": "user", "content": "¿Cuánto cuesta?"},
            {
                "role": "user",
                "content": "¿cuál es el Voc del JinkoSolar 460W a 25°C?",
            },
        ]
        profile = infer_user_profile(history)
        # Should not be experto since only first 2 messages count
        assert profile in ["novato", "intermedio"]

    def test_ignores_assistant_messages(self):
        """Test that assistant messages are ignored."""
        history = [
            {"role": "user", "content": "¿Qué es un panel?"},
            {
                "role": "assistant",
                "content": "¿cuál es el Voc del JinkoSolar 460W a 25°C?",
            },
        ]
        profile = infer_user_profile(history)
        # Should be novato because only user message (generic) is considered
        assert profile == "novato"

    def test_missing_role_key(self):
        """Test handling of messages missing 'role' key."""
        history = [{"content": "¿Qué es un panel?"}]
        profile = infer_user_profile(history)
        # Should handle gracefully
        assert profile in ["novato", "intermedio", "experto"]

    def test_missing_content_key(self):
        """Test handling of messages missing 'content' key."""
        history = [{"role": "user"}]
        profile = infer_user_profile(history)
        # Should handle gracefully and return default
        assert profile == "intermedio"

    def test_complex_technical_query(self):
        """Test complex technical query with multiple parameters."""
        history = [
            {
                "role": "user",
                "content": "Necesito comparar eficiencia, degradación y garantía de paneles monocristalinos vs policristalinos con MPPT",
            }
        ]
        profile = infer_user_profile(history)
        # Should be at least intermediate due to technical terms
        assert profile in ["intermedio", "experto"]

    def test_intermediate_with_acronyms(self):
        """Test intermediate profile with some acronyms."""
        history = [{"role": "user", "content": "¿Cuál es el costo de un kit de 5kW?"}]
        profile = infer_user_profile(history)
        # Should be at least novato (could be novato if scoring is strict)
        assert profile in ["novato", "intermedio"]

    def test_spanish_special_characters(self):
        """Test that Spanish special characters are handled."""
        history = [
            {
                "role": "user",
                "content": "¿Cuál es la eficiencia del módulo fotovoltaico?",
            }
        ]
        profile = infer_user_profile(history)
        # Should handle accents and special chars
        assert profile in ["novato", "intermedio", "experto"]

    def test_case_insensitive_classification(self):
        """Test that classification is case-insensitive."""
        history1 = [{"role": "user", "content": "¿Qué es PANEL SOLAR?"}]
        history2 = [{"role": "user", "content": "¿Qué es panel solar?"}]
        profile1 = infer_user_profile(history1)
        profile2 = infer_user_profile(history2)
        assert profile1 == profile2

    def test_case_insensitive_uppercase_technical(self):
        """Test that uppercase technical terms are correctly classified."""
        history = [
            {"role": "user", "content": "¿CUÁL ES EL VOC DEL JINKOSOLAR 460W A 25°C?"}
        ]
        profile = infer_user_profile(history)
        assert profile == "experto"

    def test_mixed_case_profile_classification(self):
        """Test profile inference with mixed case input."""
        history_lower = [{"role": "user", "content": "panel solar básico"}]
        history_mixed = [{"role": "user", "content": "Panel Solar Básico"}]
        assert infer_user_profile(history_lower) == infer_user_profile(history_mixed)


class TestSessionManagerProfileIntegration:
    """Tests for profile integration with SessionManager."""

    def test_set_user_profile(self):
        """Test setting a user profile."""
        sm = SessionManager()
        session_id = "test-session-1"
        sm.set_user_profile(session_id, "experto")
        assert sm.get_user_profile(session_id) == "experto"

    def test_get_user_profile_nonexistent(self):
        """Test getting profile for non-existent session."""
        sm = SessionManager()
        profile = sm.get_user_profile("non-existent")
        assert profile is None

    def test_profile_persistence_across_calls(self):
        """Test that profile persists across multiple get calls."""
        sm = SessionManager()
        session_id = "test-session-2"
        sm.set_user_profile(session_id, "intermedio")
        profile1 = sm.get_user_profile(session_id)
        profile2 = sm.get_user_profile(session_id)
        assert profile1 == profile2 == "intermedio"

    def test_clear_session_removes_profile(self):
        """Test that clearing a session also removes its profile."""
        sm = SessionManager()
        session_id = "test-session-3"
        sm.set_user_profile(session_id, "experto")
        assert sm.get_user_profile(session_id) == "experto"

        sm.clear_session(session_id)
        assert sm.get_user_profile(session_id) is None

    def test_update_profile(self):
        """Test updating an existing profile."""
        sm = SessionManager()
        session_id = "test-session-4"
        sm.set_user_profile(session_id, "novato")
        assert sm.get_user_profile(session_id) == "novato"

        sm.set_user_profile(session_id, "experto")
        assert sm.get_user_profile(session_id) == "experto"

    def test_multiple_sessions_independent_profiles(self):
        """Test that profiles are independent between sessions."""
        sm = SessionManager()
        sm.set_user_profile("session-1", "novato")
        sm.set_user_profile("session-2", "experto")

        assert sm.get_user_profile("session-1") == "novato"
        assert sm.get_user_profile("session-2") == "experto"


class TestEndToEndProfileInference:
    """End-to-end tests for profile inference workflow."""

    def test_infer_profile_from_session_history(self):
        """Test inferring profile from actual session history."""
        sm = SessionManager()
        session_id = "end-to-end-1"

        # Add a generic question
        sm.add_turn(session_id, "¿Qué es un panel solar?", "Un panel solar es...")

        # Get history and infer profile
        history = sm.get_history(session_id)
        history_dicts = [{"role": "user", "content": turn.question} for turn in history]
        profile = infer_user_profile(history_dicts)

        assert profile == "novato"

    def test_profile_remains_novato_with_simple_questions(self):
        """Test that multiple simple questions keep novato profile."""
        sm = SessionManager()
        session_id = "end-to-end-2"

        sm.add_turn(session_id, "¿Qué es solar?", "Es...")
        sm.add_turn(session_id, "¿Y el viento?", "Es...")

        history = sm.get_history(session_id)
        history_dicts = [{"role": "user", "content": turn.question} for turn in history]
        profile = infer_user_profile(history_dicts)

        assert profile == "novato"

    def test_profile_upgrades_to_experto_with_technical_questions(self):
        """Test that technical questions result in experto profile."""
        sm = SessionManager()
        session_id = "end-to-end-3"

        sm.add_turn(session_id, "¿Qué es solar?", "Es...")
        sm.add_turn(
            session_id,
            "¿cuál es el Voc del JinkoSolar 460W a 25°C?",
            "Es...",
        )

        history = sm.get_history(session_id)
        history_dicts = [{"role": "user", "content": turn.question} for turn in history]
        profile = infer_user_profile(history_dicts)

        assert profile == "experto"
