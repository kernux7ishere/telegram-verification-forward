"""Discord webhook delivery with retries and client-side rate limiting."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

from app.message_processor import ALPHANUMERIC, NUMERIC, VerificationCode

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10.0
MAX_BACKOFF_SECONDS = 60.0


@dataclass
class SendResult:
    """Outcome of a webhook delivery, truthy when the send succeeded."""

    success: bool
    status_code: Optional[int] = None
    attempts: int = 0
    error: str = ""

    def __bool__(self) -> bool:  # lets callers keep treating this as a bool
        return self.success


class DiscordSender:
    """Formats verification codes and pushes them to a Discord webhook."""

    def __init__(
        self,
        webhook_url: str,
        max_retries: int = 3,
        username: str = "Telegram Verification",
    ) -> None:
        self.webhook_url = webhook_url
        self.max_retries = max(1, max_retries)
        self.username = username
        self.disabled = not webhook_url.startswith("https://")
        if self.disabled:
            logger.error("Discord webhook URL is missing or invalid; sending is disabled")

        self.sent_count = 0
        self.failed_count = 0

    # -- formatting ---------------------------------------------------------

    def format_message(self, code: VerificationCode) -> dict:
        """Build the webhook JSON payload for a code."""
        if code.type == NUMERIC:
            content = f"🔑 Login code: {code.code}"
        elif code.type == ALPHANUMERIC:
            content = f"🌐 Web login code: {code.code}"
        else:
            content = f"📩 Verification code: {code.code}"

        return {
            "content": content,
            "username": self.username,
            "allowed_mentions": {"parse": []},
        }

    # -- sending ------------------------------------------------------------

    async def send_code(self, code: VerificationCode) -> SendResult:
        """Send one verification code, respecting rate limits and retries."""
        if self.disabled:
            return SendResult(False, error="webhook disabled")

        payload = self.format_message(code)
        result = await self.send_with_retry(payload)

        if result.success:
            self.sent_count += 1
            logger.info("Discord: sent %s code %s", code.type, code.code)
        else:
            self.failed_count += 1
            logger.error(
                "Discord: failed to send code %s after %d attempt(s): %s",
                code.code,
                result.attempts,
                result.error,
            )
        return result

    async def send_with_retry(self, payload: dict) -> SendResult:
        """POST ``payload`` with exponential backoff on transient failures."""
        status: Optional[int] = None
        error = ""

        for attempt in range(1, self.max_retries + 1):
            try:
                response = await asyncio.to_thread(self._post, payload)
                status = response.status_code
            except requests.RequestException as exc:
                status, error = None, str(exc)
                logger.warning("Discord: request error on attempt %d: %s", attempt, exc)
            else:
                if 200 <= status < 300:
                    return SendResult(True, status, attempt)

                if status == 429:
                    retry_after = self._retry_after(response)
                    logger.warning("Discord: 429 received, retrying in %.1fs", retry_after)
                    error = "rate limited by Discord"
                    if attempt < self.max_retries:
                        await asyncio.sleep(retry_after)
                    continue

                error = f"HTTP {status}: {response.text[:200]}"
                if 400 <= status < 500 and status != 429:
                    # 401/403/404 mean the webhook is gone or wrong: stop trying.
                    if status in (401, 403, 404):
                        self.disabled = True
                        logger.error("Discord: webhook rejected (%s); disabling sender", status)
                    return SendResult(False, status, attempt, error)

            if attempt < self.max_retries:
                await asyncio.sleep(min(2 ** (attempt - 1), MAX_BACKOFF_SECONDS))

        return SendResult(False, status, self.max_retries, error or "unknown error")

    def _post(self, payload: dict) -> requests.Response:
        return requests.post(self.webhook_url, json=payload, timeout=REQUEST_TIMEOUT)

    @staticmethod
    def _retry_after(response: requests.Response) -> float:
        header = response.headers.get("Retry-After")
        try:
            if header is not None:
                return max(0.5, min(float(header), MAX_BACKOFF_SECONDS))
        except (TypeError, ValueError):
            pass
        try:
            body = response.json()
            return max(0.5, min(float(body.get("retry_after", 1.0)), MAX_BACKOFF_SECONDS))
        except (ValueError, AttributeError, TypeError):
            return 1.0

    async def send_alert(self, text: str) -> SendResult:
        """Push a plain-text operational alert (critical errors) to Discord."""
        if self.disabled:
            return SendResult(False, error="webhook disabled")
        payload = {
            "content": f"⚠️ {text}"[:1900],
            "username": self.username,
            "allowed_mentions": {"parse": []},
        }
        return await self.send_with_retry(payload)
