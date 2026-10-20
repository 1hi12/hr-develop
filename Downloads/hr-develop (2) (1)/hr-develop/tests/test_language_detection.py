"""
Tests unitaires — language_detection.py
Fonctions pures : aucun mock nécessaire.
"""
import pytest
from app.agent.tools.cv_extractor.language_detection import (
    detect_language,
    get_localized_prompts,
    get_localized_thinking_messages,
    get_localized_parse_response_fallback,
)


class TestDetectLanguage:

    # ── Détection français ────────────────────────────────────
    def test_french_text_detected(self):
        text = "Poste de développeur avec expérience en formation et compétences techniques"
        assert detect_language(text) == "fr"

    def test_french_accents_detected(self):
        assert detect_language("Ingénieur logiciel avec expérience") == "fr"

    def test_french_special_chars_cedilla(self):
        assert detect_language("Maîtrise de la conception et réalisation") == "fr"

    def test_french_keywords_stage_emploi(self):
        assert detect_language("Offre de stage emploi en développement") == "fr"

    def test_french_verbs_detected(self):
        assert detect_language("Être capable de faire et vouloir progresser") == "fr"

    # ── Détection anglais ─────────────────────────────────────
    def test_english_text_detected(self):
        text = "We are looking for a candidate with experience and skills in development"
        assert detect_language(text) == "en"

    def test_english_keywords_job(self):
        assert detect_language("Job position required skills experience team") == "en"

    def test_english_common_words(self):
        assert detect_language("The candidate will work with our team and have responsibilities") == "en"

    def test_english_internship(self):
        assert detect_language("Internship position available for qualified candidates") == "en"

    # ── Cas limites ───────────────────────────────────────────
    def test_empty_string_returns_en(self):
        assert detect_language("") == "en"

    def test_single_french_accent_detected(self):
        assert detect_language("é") == "fr"

    def test_case_insensitive_french(self):
        assert detect_language("POSTE DE CANDIDAT COMPÉTENCES") == "fr"

    def test_numbers_only_returns_en(self):
        assert detect_language("1234567890") == "en"


class TestGetLocalizedPrompts:

    # ── Langue française ──────────────────────────────────────
    def test_french_returns_dict(self):
        result = get_localized_prompts("fr")
        assert isinstance(result, dict)

    def test_french_has_all_keys(self):
        result = get_localized_prompts("fr")
        expected_keys = [
            "filter_prompt_prefix",
            "explanation_prompt_prefix",
            "no_candidates_message",
            "header_template",
            "candidate_template",
            "summary_template",
            "email_sent",
            "email_unavailable",
            "email_error",
            "email_enabled",
            "email_disabled",
            "emails_sent_count",
        ]
        for key in expected_keys:
            assert key in result, f"Clé manquante: {key}"

    def test_french_email_sent_value(self):
        result = get_localized_prompts("fr")
        assert "Email envoyé" in result["email_sent"]

    def test_french_filter_prompt_contains_poste(self):
        result = get_localized_prompts("fr")
        assert "poste" in result["filter_prompt_prefix"].lower() or "Description" in result["filter_prompt_prefix"]

    # ── Langue anglaise ───────────────────────────────────────
    def test_english_returns_dict(self):
        result = get_localized_prompts("en")
        assert isinstance(result, dict)

    def test_english_has_all_keys(self):
        result = get_localized_prompts("en")
        expected_keys = [
            "filter_prompt_prefix",
            "explanation_prompt_prefix",
            "no_candidates_message",
            "header_template",
            "candidate_template",
            "summary_template",
            "email_sent",
        ]
        for key in expected_keys:
            assert key in result

    def test_english_email_sent_value(self):
        result = get_localized_prompts("en")
        assert "Email sent" in result["email_sent"]

    def test_english_filter_prompt_contains_job(self):
        result = get_localized_prompts("en")
        assert "Job" in result["filter_prompt_prefix"] or "job" in result["filter_prompt_prefix"]

    # ── Langue inconnue → anglais par défaut ──────────────────
    def test_unknown_language_returns_english(self):
        result = get_localized_prompts("ar")
        assert "Email sent" in result["email_sent"]

    def test_fr_and_en_prompts_are_different(self):
        fr = get_localized_prompts("fr")
        en = get_localized_prompts("en")
        assert fr["email_sent"] != en["email_sent"]
        assert fr["email_enabled"] != en["email_enabled"]


class TestGetLocalizedThinkingMessages:

    def test_french_thinking_messages_keys(self):
        result = get_localized_thinking_messages("fr")
        assert "starting_filter" in result
        assert "cv_selected" in result
        assert "cv_rejected" in result
        assert "separator" in result

    def test_english_thinking_messages_keys(self):
        result = get_localized_thinking_messages("en")
        assert "starting_filter" in result
        assert "cv_selected" in result
        assert "cv_rejected" in result

    def test_french_cv_selected_contains_selectionne(self):
        result = get_localized_thinking_messages("fr")
        assert "SÉLECTIONNÉ" in result["cv_selected"]

    def test_english_cv_selected_contains_selected(self):
        result = get_localized_thinking_messages("en")
        assert "SELECTED" in result["cv_selected"]

    def test_unknown_language_returns_english(self):
        result = get_localized_thinking_messages("de")
        assert "SELECTED" in result["cv_selected"]


class TestGetLocalizedParseFallback:

    def test_french_fallback_has_excellent_keywords(self):
        result = get_localized_parse_response_fallback("fr")
        assert "excellent_keywords" in result
        assert len(result["excellent_keywords"]) > 0

    def test_english_fallback_has_excellent_keywords(self):
        result = get_localized_parse_response_fallback("en")
        assert "excellent" in result["excellent_keywords"]

    def test_french_domain_match_unknown_is_french(self):
        result = get_localized_parse_response_fallback("fr")
        assert result["domain_match_unknown"] == "Inconnu"

    def test_english_domain_match_unknown_is_english(self):
        result = get_localized_parse_response_fallback("en")
        assert result["domain_match_unknown"] == "Unknown"

    def test_french_and_english_are_different(self):
        fr = get_localized_parse_response_fallback("fr")
        en = get_localized_parse_response_fallback("en")
        assert fr["domain_match_unknown"] != en["domain_match_unknown"]
