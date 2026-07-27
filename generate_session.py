#!/usr/bin/env python3
"""Generate a Pyrogram session string for headless deployment.

Render's filesystem is ephemeral, so a `.session` file would be lost on every
deploy and the bot would ask for a login code it cannot receive. Run this once
locally, then store the printed value as TELEGRAM_SESSION_STRING in Doppler.

    doppler run -- python generate_session.py

The string is equivalent to a logged-in session: treat it like a password.
"""

from __future__ import annotations

import asyncio
import sys

from app.config import Config


async def generate() -> int:
    config = Config.from_env()

    if not (config.telegram_api_id and config.telegram_api_hash):
        print("error: TELEGRAM_API_ID and TELEGRAM_API_HASH must be set", file=sys.stderr)
        return 2

    try:
        from pyrogram import Client
    except ImportError:
        print("error: pyrogram is not installed (pip install -r requirements.txt)", file=sys.stderr)
        return 2

    kwargs = {
        "api_id": config.telegram_api_id,
        "api_hash": config.telegram_api_hash,
        "in_memory": True,
        "app_version": "verification-forwarder",
    }
    if config.telegram_phone:
        kwargs["phone_number"] = config.telegram_phone
    if config.telegram_password:
        kwargs["password"] = config.telegram_password

    print("Signing in — Telegram will send a login code to your account.\n")
    async with Client("session_generator", **kwargs) as client:
        me = await client.get_me()
        session_string = await client.export_session_string()

    print(f"\nSigned in as {me.first_name} (id={me.id})\n")
    print("Store this as TELEGRAM_SESSION_STRING (it is a credential — do not commit it):\n")
    print(session_string)
    print("\n  doppler secrets set TELEGRAM_SESSION_STRING")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(generate()))
