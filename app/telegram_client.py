"""Pyrogram user-bot that watches for Telegram's own verification messages.

Pyrogram is imported lazily so the rest of the package (and the test suite) can
be used on a machine where the Telegram stack is not installed.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

STATUS_OFFLINE = "offline"
STATUS_CONNECTING = "connecting"
STATUS_ONLINE = "online"
STATUS_ERROR = "error"

MAX_BACKOFF_SECONDS = 60.0
AUTH_FAILURE_PAUSE_SECONDS = 3600.0

MessageCallback = Callable[[str, Optional[int]], Awaitable[None]]


class TelegramClient:
    """Connects as a user account and forwards matching messages to a callback."""

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        phone: str = "",
        password: str = "",
        session_string: str = "",
        session_name: str = "verification_forwarder",
        source_chat_id: int = 777000,
        workdir: str = "./data",
    ) -> None:
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.password = password
        self.session_string = session_string
        self.session_name = session_name
        self.source_chat_id = source_chat_id
        self.workdir = workdir

        self._client: Any = None
        self._callback: Optional[MessageCallback] = None
        self._status = STATUS_OFFLINE
        self._connected_at: Optional[datetime] = None
        self._last_message_time: Optional[datetime] = None
        self._last_error: str = ""
        self._stop_event: Optional[asyncio.Event] = None

    # -- state --------------------------------------------------------------

    @property
    def status(self) -> str:
        return self._status

    @property
    def last_error(self) -> str:
        return self._last_error

    async def is_connected(self) -> bool:
        return self._status == STATUS_ONLINE and self._client is not None

    async def get_last_message_time(self) -> Optional[datetime]:
        return self._last_message_time

    @property
    def last_message_time(self) -> Optional[datetime]:
        """Synchronous view of the same value, for the stats collector."""
        return self._last_message_time

    @property
    def connected_at(self) -> Optional[datetime]:
        return self._connected_at

    # -- lifecycle ----------------------------------------------------------

    def _build_client(self) -> Any:
        from pyrogram import Client  # imported here to keep startup cheap

        kwargs: dict[str, Any] = {
            "api_id": self.api_id,
            "api_hash": self.api_hash,
            "app_version": "verification-forwarder",
        }
        if self.session_string:
            # Stateless login: nothing is written to disk, which is what an
            # ephemeral Render instance needs.
            kwargs["session_string"] = self.session_string
            kwargs["in_memory"] = True
        else:
            Path(self.workdir).mkdir(parents=True, exist_ok=True)
            kwargs["workdir"] = self.workdir
            if self.phone:
                kwargs["phone_number"] = self.phone
            if self.password:
                kwargs["password"] = self.password

        return Client(self.session_name, **kwargs)

    async def connect(self) -> bool:
        """Start the underlying Pyrogram client. Returns True on success."""
        self._status = STATUS_CONNECTING
        try:
            self._client = self._build_client()
            self._register_handler()
            await self._client.start()
        except Exception as exc:  # noqa: BLE001 - surface any auth/network error
            self._status = STATUS_ERROR
            self._last_error = f"{type(exc).__name__}: {exc}"
            logger.error("Telegram: connection failed: %s", self._last_error)
            self._client = None
            return False

        self._status = STATUS_ONLINE
        self._connected_at = datetime.now(timezone.utc)
        self._last_error = ""
        try:
            me = await self._client.get_me()
            logger.info("Telegram: connected as %s (id=%s)", me.first_name, me.id)
        except Exception:  # noqa: BLE001 - identity lookup is informational only
            logger.info("Telegram: connected")
        return True

    async def disconnect(self) -> None:
        if self._client is not None:
            try:
                await self._client.stop()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Telegram: error while stopping client: %s", exc)
        self._client = None
        self._status = STATUS_OFFLINE
        logger.info("Telegram: disconnected")

    def _register_handler(self) -> None:
        from pyrogram import filters
        from pyrogram.handlers import MessageHandler

        self._client.add_handler(
            MessageHandler(self._on_message, filters.chat(self.source_chat_id))
        )

    # -- message flow -------------------------------------------------------

    async def _on_message(self, _client: Any, message: Any) -> None:
        await self.handle_message(message)

    async def handle_message(self, message: Any) -> None:
        """Hand the text of an incoming message to the registered callback."""
        self._last_message_time = datetime.now(timezone.utc)
        text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
        message_id = getattr(message, "id", None)

        if not text.strip():
            logger.debug("Telegram: ignored message %s with no text", message_id)
            return

        logger.info("Telegram: message %s received from %s", message_id, self.source_chat_id)
        if self._callback is None:
            return
        try:
            await self._callback(text, message_id)
        except Exception as exc:  # noqa: BLE001 - a bad message must not kill the bot
            logger.exception("Telegram: callback failed: %s", exc)

    async def start_listening(self, callback: MessageCallback) -> None:
        """Connect and stay connected, reconnecting with exponential backoff."""
        self._callback = callback
        self._stop_event = asyncio.Event()
        backoff = 1.0

        while not self._stop_event.is_set():
            if await self.connect():
                backoff = 1.0
                await self._stop_event.wait()
                break

            if self._is_auth_failure(self._last_error):
                logger.error(
                    "Telegram: authentication failed, pausing for %.0f minutes",
                    AUTH_FAILURE_PAUSE_SECONDS / 60,
                )
                await self._sleep_or_stop(AUTH_FAILURE_PAUSE_SECONDS)
                continue

            logger.warning("Telegram: reconnecting in %.0fs", backoff)
            await self._sleep_or_stop(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

        await self.disconnect()

    async def _sleep_or_stop(self, seconds: float) -> None:
        assert self._stop_event is not None
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    def request_stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()

    @staticmethod
    def _is_auth_failure(error: str) -> bool:
        needles = (
            "AuthKey",
            "PhoneNumber",
            "PhoneCode",
            "SessionExpired",
            "SessionRevoked",
            "PasswordHashInvalid",
            "Unauthorized",
        )
        return any(needle.lower() in error.lower() for needle in needles)
