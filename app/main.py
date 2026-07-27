"""Local entry point: `python -m app.main`.

Starts the Telegram worker and serves the dashboard with Flask's built-in server.
In production Render runs `gunicorn app.web_server:app` via app.service.
"""

from __future__ import annotations

import logging
import signal
import sys
from types import FrameType
from typing import Optional

from app import __version__
from app.config import Config, setup_logging
from app.service import get_service
from app.web_server import create_app

logger = logging.getLogger(__name__)


def main() -> int:
    config = Config.from_env()
    setup_logging(config)
    logger.info("Starting telegram-verification-forwarder v%s (%s)", __version__, config.environment)

    missing = config.missing_settings()
    if missing:
        logger.warning("Missing configuration: %s", ", ".join(missing))

    service = get_service(config)

    def handle_signal(signum: int, _frame: Optional[FrameType]) -> None:
        logger.info("Received signal %s, shutting down", signum)
        service.stop()
        try:
            service.telegram._client.stop()
        except Exception:
            pass
        sys.exit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, handle_signal)
        except (ValueError, OSError):  # not the main thread / unsupported platform
            pass

    if config.run_webui:
        flask_app = create_app(service=service, start_bot=True)
        logger.info("Dashboard listening on http://0.0.0.0:%d", config.port)
        flask_app.run(host="0.0.0.0", port=config.port, debug=False, use_reloader=False)
    else:
        logger.info("Web UI is disabled. Running bot only.")
        service.start()
        import time
        while True:
            time.sleep(3600)
    service.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
