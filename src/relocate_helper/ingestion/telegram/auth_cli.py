"""Interactive Telethon authorization CLI."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from relocate_helper.common.config import get_settings
from relocate_helper.common.logging import configure_logging, get_logger

logger = get_logger(__name__)


async def _authorize(*, phone: str | None, session_path: Path) -> None:
    from telethon import TelegramClient

    settings = get_settings()
    api_id = settings.telegram_api_id
    api_hash = settings.telegram_api_hash.get_secret_value()

    session_path.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(session_path), api_id, api_hash)
    await client.connect()

    if await client.is_user_authorized():
        logger.info("telegram_auth_already_authorized", session_path=str(session_path))
        await client.disconnect()
        return

    if not phone:
        phone = input("Telegram phone number (international format): ").strip()

    await client.send_code_request(phone)
    code = input("Login code from Telegram (never paste into chat logs): ").strip()
    try:
        await client.sign_in(phone=phone, code=code)
    except Exception:
        password = input("Two-step password (input hidden in terminal): ").strip()
        await client.sign_in(password=password)

    await client.disconnect()
    logger.info("telegram_auth_success", session_path=str(session_path))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Authorize Telethon and save session outside the repository.",
    )
    parser.add_argument(
        "--phone",
        help="Phone number in international format. Prompted if omitted.",
    )
    parser.add_argument(
        "--session-path",
        type=Path,
        default=None,
        help="Override TELETHON_SESSION_PATH from settings.",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(log_level=settings.log_level, json_logs=settings.log_json)
    session_path = args.session_path or settings.telethon_session_path
    if session_path is None:
        print(
            "TELETHON_SESSION_PATH is not configured. Set it in the environment.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    asyncio.run(_authorize(phone=args.phone, session_path=session_path))


if __name__ == "__main__":
    main()
