import asyncio
import atexit
import logging
import threading
from typing import Optional

from app.config import Config, setup_logging
from app.discord_sender import DiscordSender
from app.message_processor import MessageProcessor
from app.stats_collector import StatsCollector
from app.telegram_client import TelegramClient

logger = logging.getLogger(__name__)

class Service:
    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config.from_env()
        setup_logging(self.config)

        self.processor = MessageProcessor(min_confidence=self.config.min_confidence)
        self.discord = DiscordSender(
            webhook_url=self.config.discord_webhook_url,
            max_retries=self.config.discord_max_retries,
        )
        self.telegram = TelegramClient(
            api_id=self.config.telegram_api_id,
            api_hash=self.config.telegram_api_hash,
            phone=self.config.telegram_phone,
            password=self.config.telegram_password,
            session_string=self.config.telegram_session_string,
            session_name=self.config.session_name,
            source_chat_id=self.config.source_chat_id,
        )
        self.stats = StatsCollector(telegram_client=self.telegram, discord_sender=self.discord)

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._started = False

    async def on_message(self, text: str, telegram_message_id: Optional[int]) -> None:
        codes = self.processor.extract_codes(text, telegram_message_id=telegram_message_id)
        if not codes:
            return

        for code in codes:
            logger.info(f"Code received: {code.code}")
            self.stats.record_code(code)
            await self.discord.send_code(code)

    def start(self) -> bool:
        if self._started: return True
        if not self.config.run_bot: return False
        if not self.config.telegram_configured: return False

        self._started = True
        self._thread = threading.Thread(target=self._run_loop, name="telegram-bot", daemon=True)
        self._thread.start()
        atexit.register(self.stop)
        return True

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main())
        finally:
            loop.close()

    async def _main(self) -> None:
        await self.telegram.start_listening(self.on_message)

    def stop(self) -> None:
        if not self._started: return
        self._started = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self.telegram.request_stop)
        if self._thread:
            self._thread.join(timeout=10)

_service = None
_service_lock = threading.Lock()

def get_service(config: Optional[Config] = None) -> Service:
    global _service
    with _service_lock:
        if _service is None:
            _service = Service(config)
        return _service
