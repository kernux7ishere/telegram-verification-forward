"""Configuration loading and logging setup.

Secrets come from environment variables. A local `.env` file is read as a fallback.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

_LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def load_dotenv(path: str | os.PathLike[str] | None = None) -> None:
    """Populate os.environ from a .env file, without overriding real env vars."""
    env_path = Path(path) if path else ROOT_DIR / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


@dataclass
class Config:
    """Runtime configuration, resolved once at startup."""

    # Telegram
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_phone: str = ""
    telegram_password: str = ""
    telegram_session_string: str = ""
    session_name: str = "verification_forwarder"

    # Source filtering
    source_chat_id: int = 777000
    min_confidence: float = 0.5

    # Discord
    discord_webhook_url: str = ""
    discord_max_retries: int = 3

    # Storage
    log_dir: str = "./logs"
    log_level: str = "INFO"
    log_retention_days: int = 30

    # Web
    flask_secret_key: str = "change-me"
    port: int = 5000
    environment: str = "production"
    run_bot: bool = True
    run_webui: bool = True

    version: str = field(default="", repr=False)

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        from app import __version__

        return cls(
            telegram_api_id=_env_int("TELEGRAM_API_ID", 0),
            telegram_api_hash=os.environ.get("TELEGRAM_API_HASH", "").strip(),
            telegram_phone=os.environ.get("TELEGRAM_PHONE", "").strip(),
            telegram_password=os.environ.get("TELEGRAM_PASSWORD", "").strip(),
            telegram_session_string=os.environ.get("TELEGRAM_SESSION_STRING", "").strip(),
            source_chat_id=_env_int("SOURCE_CHAT_ID", 777000),
            min_confidence=_env_float("MIN_CONFIDENCE", 0.5),
            discord_webhook_url=os.environ.get("DISCORD_WEBHOOK_URL", "").strip(),
            discord_max_retries=_env_int("DISCORD_MAX_RETRIES", 3),
            log_dir=os.environ.get("LOG_DIR", "./logs").strip(),
            log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper(),
            log_retention_days=_env_int("LOG_RETENTION_DAYS", 30),
            flask_secret_key=os.environ.get("FLASK_SECRET_KEY", "change-me").strip(),
            port=_env_int("PORT", 5000),
            environment=os.environ.get("ENVIRONMENT", "production").strip(),
            run_bot=_env_bool("RUN_BOT", True),
            run_webui=_env_bool("RUN_WEBUI", True),
            version=__version__,
        )

    @property
    def telegram_configured(self) -> bool:
        """True when there are enough credentials to attempt a login."""
        if not (self.telegram_api_id and self.telegram_api_hash):
            return False
        return bool(self.telegram_session_string or self.telegram_phone)

    @property
    def discord_configured(self) -> bool:
        return self.discord_webhook_url.startswith("https://")

    def missing_settings(self) -> list[str]:
        missing = []
        if not self.telegram_api_id:
            missing.append("TELEGRAM_API_ID")
        if not self.telegram_api_hash:
            missing.append("TELEGRAM_API_HASH")
        if not (self.telegram_session_string or self.telegram_phone):
            missing.append("TELEGRAM_SESSION_STRING or TELEGRAM_PHONE")
        if not self.discord_configured:
            missing.append("DISCORD_WEBHOOK_URL")
        return missing


_logging_ready = False


def setup_logging(config: Config | None = None) -> None:
    """Configure stdout + rotating-file logging. Safe to call more than once."""
    global _logging_ready
    if _logging_ready:
        return

    config = config or Config.from_env()
    level = getattr(logging, config.log_level, logging.INFO)
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT)

    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)

    try:
        log_dir = Path(config.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as exc:  # read-only filesystem: stdout logging is enough
        root.warning("File logging disabled (%s)", exc)

    # Pyrogram is extremely chatty at INFO.
    logging.getLogger("pyrogram").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _logging_ready = True
