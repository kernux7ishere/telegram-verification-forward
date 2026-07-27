#!/usr/bin/env bash
# Production start command.
set -euo pipefail

PORT="${PORT:-5000}"

# One worker only: the Telegram user bot must not be duplicated across
# processes. Threads handle the (tiny) dashboard traffic instead.

RUN_WEBUI="${RUN_WEBUI:-true}"

if [[ "${RUN_WEBUI,,}" == "false" || "${RUN_WEBUI}" == "0" ]]; then
  echo "Starting in Bot-Only mode (Web UI disabled)"
  exec python -m app.main
else
  SERVER=(
    gunicorn
    --workers 1
    --threads 4
    --bind "0.0.0.0:${PORT}"
    --timeout 120
    --graceful-timeout 30
    --access-logfile -
    --error-logfile -
    app.web_server:app
  )
  echo "Starting server with Web UI enabled"
  exec "${SERVER[@]}"
fi
