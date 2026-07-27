"""Tests for code extraction, classification and false-positive filtering."""

import pytest

from app.message_processor import (
    ALPHANUMERIC,
    NUMERIC,
    MessageProcessor,
    VerificationCode,
)


@pytest.fixture()
def processor():
    return MessageProcessor(min_confidence=0.5)


# --- happy paths -----------------------------------------------------------


def test_extracts_numeric_login_code(processor):
    text = "Login code: 15825. Do not give this code to anyone, even if they say they are from Telegram!"
    codes = processor.extract_codes(text)

    assert len(codes) == 1
    assert codes[0].code == "15825"
    assert codes[0].type == NUMERIC
    assert codes[0].pattern_matched == "numeric"
    assert codes[0].confidence >= 0.9


def test_extracts_alphanumeric_web_login_code(processor):
    codes = processor.extract_codes("Web login code: sEHa-bQyZcM")

    assert len(codes) == 1
    assert codes[0].code == "sEHa-bQyZcM"
    assert codes[0].type == ALPHANUMERIC
    assert codes[0].pattern_matched == "dashed_alnum"


@pytest.mark.parametrize(
    ("text", "expected", "pattern"),
    [
        ("Your Instagram code is 483-921", "483-921", "instagram"),
        ("G-482 913 is your Google verification code", "482 913", "google"),
        ("Your verification code is 8391027", "8391027", "numeric"),
        ("kod potwierdzenia: 4821", "4821", "numeric"),
    ],
)
def test_extracts_supported_shapes(processor, text, expected, pattern):
    codes = processor.extract_codes(text)

    assert [c.code for c in codes] == [expected]
    assert codes[0].pattern_matched == pattern


def test_dashed_code_is_not_split_into_two_numbers(processor):
    codes = processor.extract_codes("Verification code: 483-921")

    assert len(codes) == 1
    assert codes[0].code == "483-921"


def test_multiple_codes_are_returned_best_first(processor):
    codes = processor.extract_codes("Login code: 15825 — backup code 4471")

    assert len(codes) == 2
    assert codes[0].code == "15825"
    assert codes[0].confidence >= codes[1].confidence


def test_message_id_is_carried_through(processor):
    codes = processor.extract_codes("Login code: 15825", telegram_message_id=42)

    assert codes[0].telegram_message_id == 42
    assert codes[0].raw_message.startswith("Login code")


# --- false positives -------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "Do not give this code to anyone.",
        "Your account was accessed from a new device.",
    ],
)
def test_returns_nothing_without_a_code(processor, text):
    assert processor.extract_codes(text) == []


def test_ignores_date_fragments(processor):
    assert processor.extract_codes("New login on 2024-01-15 from Berlin") == []


def test_ignores_version_and_time_fragments(processor):
    assert processor.extract_codes("Updated to app version 10.2.1234 today") == []


def test_ignores_the_service_account_id(processor):
    assert processor.extract_codes("Message from code 777000 service") == []


def test_ignores_currency_amounts(processor):
    assert processor.extract_codes("You were charged $1499 for the plan") == []


def test_bare_year_without_context_is_dropped(processor):
    assert processor.extract_codes("Copyright 2024 Telegram Messenger") == []


def test_year_looking_code_with_context_is_kept(processor):
    codes = processor.extract_codes("Login code: 2024")

    assert [c.code for c in codes] == ["2024"]


def test_hyphenated_english_word_is_not_a_code(processor):
    assert processor.extract_codes("This is a well-known issue with your account") == []


def test_repeated_digits_are_penalised(processor):
    # Still forwarded when the message clearly announces a code, but scored
    # below an ordinary one so a threshold bump filters it out first.
    repeated = processor.extract_codes("Your code is 11111")
    ordinary = processor.extract_codes("Your code is 15825")

    assert [c.code for c in repeated] == ["11111"]
    assert repeated[0].confidence < ordinary[0].confidence
    assert processor.extract_codes("Call us on 11111") == []


def test_confidence_threshold_is_respected():
    text = "Reference 483920 for the transaction"
    assert MessageProcessor(min_confidence=0.9).extract_codes(text) == []
    assert MessageProcessor(min_confidence=0.3).extract_codes(text)


# --- helpers ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("15825", NUMERIC),
        ("483-921", NUMERIC),
        ("482 913", NUMERIC),
        ("sEHa-bQyZcM", ALPHANUMERIC),
        ("AB12CD", ALPHANUMERIC),
    ],
)
def test_classify_code(processor, code, expected):
    assert processor.classify_code(code) == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("15825", True),
        ("sEHa-bQyZcM", True),
        ("483-921", True),
        ("777000", False),
        ("well-known", False),
        ("12", False),
        ("", False),
    ],
)
def test_is_valid_code(processor, code, expected):
    assert processor.is_valid_code(code) is expected


def test_filter_false_positives(processor):
    candidates = ["15825", "777000", "12", "sEHa-bQyZcM", "well-known"]

    assert processor.filter_false_positives(candidates) == ["15825", "sEHa-bQyZcM"]


def test_verification_code_serialises():
    code = VerificationCode(
        code="15825",
        type=NUMERIC,
        confidence=0.95,
        pattern_matched="numeric",
        raw_message="Login code: 15825",
    )
    payload = code.to_dict()

    assert payload["code"] == "15825"
    assert payload["confidence"] == 0.95
    assert payload["timestamp"].endswith("+00:00")
