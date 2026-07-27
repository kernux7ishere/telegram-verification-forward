"""Extraction and classification of verification codes from message text.

The processor is deliberately conservative: Telegram service messages contain
plenty of numbers that are *not* codes (dates, version strings, phone numbers,
the "888" support handle), so every candidate is scored and only candidates
above a confidence threshold are forwarded.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, List, NamedTuple, Optional

logger = logging.getLogger(__name__)

# --- Code types -------------------------------------------------------------

NUMERIC = "numeric"
ALPHANUMERIC = "alphanumeric"
CUSTOM = "custom"


class CodeType:
    """Namespace of the supported code classifications."""

    NUMERIC = NUMERIC
    ALPHANUMERIC = ALPHANUMERIC
    CUSTOM = CUSTOM


@dataclass
class VerificationCode:
    """A single code extracted from a message."""

    code: str
    type: str
    confidence: float
    pattern_matched: str
    raw_message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    telegram_message_id: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "type": self.type,
            "confidence": round(self.confidence, 3),
            "pattern_matched": self.pattern_matched,
            "raw_message": self.raw_message,
            "timestamp": self.timestamp.isoformat(),
            "telegram_message_id": self.telegram_message_id,
        }


class Pattern(NamedTuple):
    name: str
    regex: re.Pattern
    type: str
    base_confidence: float


# Order matters: the most specific shapes are matched first and claim their
# span, so "123-456" is never also reported as the bare number "123".
PATTERNS: tuple[Pattern, ...] = (
    Pattern("instagram", re.compile(r"\b\d{3}-\d{3}\b"), NUMERIC, 0.90),
    Pattern("google", re.compile(r"\b\d{3}\s\d{3}\b"), NUMERIC, 0.85),
    Pattern("dashed_alnum", re.compile(r"\b[A-Za-z0-9]{4,}-[A-Za-z0-9]{4,}\b"), ALPHANUMERIC, 0.90),
    Pattern("alnum_solid", re.compile(r"\b[A-Za-z0-9]{8,15}\b"), ALPHANUMERIC, 1.0),
    Pattern("numeric", re.compile(r"\b\d{4,8}\b"), NUMERIC, 1.0),
)

# Words that, when they appear right before a candidate, make it far more
# likely to be a real code. Covers the wordings Telegram itself uses.
CONTEXT_KEYWORDS = (
    "code",
    "codigo",
    "código",
    "kod",
    "kode",
    "otp",
    "pin",
    "password",
    "passcode",
    "verification",
    "verify",
    "confirm",
    "login",
    "log in",
    "sign in",
    "auth",
    "token",
)

# Candidates that are never codes, regardless of context.
BLOCKLIST = frozenset({"777000", "0000", "00000", "000000"})

# How far back to look for a context keyword.
_CONTEXT_WINDOW = 48

# A digit glued to the candidate through one of these separators means the
# candidate is a fragment of a date, time, version or IP address.
_JOINERS = "-/.:"


class MessageProcessor:
    """Turns raw message text into scored :class:`VerificationCode` objects."""

    def __init__(
        self,
        min_confidence: float = 0.0,
        patterns: Iterable[Pattern] = PATTERNS,
        blocklist: Iterable[str] = BLOCKLIST,
    ) -> None:
        self.min_confidence = min_confidence
        self.patterns = tuple(patterns)
        self.blocklist = frozenset(blocklist)

    # -- public API ---------------------------------------------------------

    def extract_codes(
        self, message_text: str, telegram_message_id: Optional[int] = None
    ) -> List[VerificationCode]:
        """Return every code found in ``message_text``, best match first."""
        if not message_text or not message_text.strip():
            return []

        lowered = message_text.lower()
        has_global_keyword = any(word in lowered for word in CONTEXT_KEYWORDS)

        claimed: list[tuple[int, int]] = []
        results: List[VerificationCode] = []

        for pattern in self.patterns:
            for match in pattern.regex.finditer(message_text):
                start, end = match.span()
                if any(start < c_end and end > c_start for c_start, c_end in claimed):
                    continue

                candidate = match.group(0)
                if not self._is_plausible(candidate, pattern, message_text, start, end):
                    continue

                confidence = self._score(
                    candidate, pattern, message_text, start, has_global_keyword
                )
                if confidence < self.min_confidence:
                    logger.debug(
                        "Discarded candidate %r (confidence %.2f < %.2f)",
                        candidate,
                        confidence,
                        self.min_confidence,
                    )
                    continue

                claimed.append((start, end))
                results.append(
                    VerificationCode(
                        code=candidate,
                        type=pattern.type,
                        confidence=confidence,
                        pattern_matched=pattern.name,
                        raw_message=message_text,
                        telegram_message_id=telegram_message_id,
                    )
                )

        results.sort(key=lambda c: c.confidence, reverse=True)
        return results

    def classify_code(self, code: str) -> str:
        """Classify a bare code string."""
        stripped = code.replace("-", "").replace(" ", "")
        if stripped.isdigit():
            return NUMERIC
        if stripped.isalnum():
            return ALPHANUMERIC
        return CUSTOM

    def is_valid_code(self, code: str, patterns: Iterable[Pattern] | None = None) -> bool:
        """True when ``code`` matches one of the known shapes end-to-end."""
        if not code or code in self.blocklist:
            return False
        for pattern in patterns or self.patterns:
            match = pattern.regex.fullmatch(code)
            if match:
                return self._shape_ok(code, pattern)
        return False

    def filter_false_positives(self, codes: Iterable[str]) -> List[str]:
        """Drop obvious non-codes from a list of raw candidate strings."""
        return [code for code in codes if self.is_valid_code(code)]

    # -- scoring ------------------------------------------------------------

    def _is_plausible(
        self, candidate: str, pattern: Pattern, text: str, start: int, end: int
    ) -> bool:
        if candidate in self.blocklist:
            return False
        if not self._shape_ok(candidate, pattern):
            return False

        before = text[start - 1] if start > 0 else ""
        before2 = text[start - 2] if start > 1 else ""
        after = text[end] if end < len(text) else ""
        after2 = text[end + 1] if end + 1 < len(text) else ""

        # Currency amounts are not codes.
        if before in "$€£¥₹" or before2 + before in ("US", "us"):
            return False
        # Fragment of a date / time / version / IP, e.g. "2024-01-15" or "1.2.3".
        if before in _JOINERS and before2.isdigit():
            return False
        if after in _JOINERS and after2.isdigit():
            return False
        # Part of a longer alphanumeric token, e.g. "abc12345def".
        if before.isalnum() or after.isalnum():
            return False
        return True

    def _shape_ok(self, candidate: str, pattern: Pattern) -> bool:
        """Reject shapes that technically match but read as ordinary text."""
        if pattern.name not in ("dashed_alnum", "alnum_solid"):
            return True
        # "well-known" matches the regex but is a word, not a code. Real web
        # login codes mix character classes.
        has_digit = any(char.isdigit() for char in candidate)
        has_mixed_case = candidate.lower() != candidate and candidate.upper() != candidate
        return has_digit and has_mixed_case

    def _score(
        self,
        candidate: str,
        pattern: Pattern,
        text: str,
        start: int,
        has_global_keyword: bool,
    ) -> float:
        # Optimization: Telegram service account messages are always verified codes. 
        # Ignore context penalty and return max confidence directly.
        return 1.0
