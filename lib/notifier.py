#!/usr/bin/env python3
"""Einfaches Modul zum Senden von Nachrichten an Telegram (für Claude Code Hooks etc.)."""

import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_message(text: str, parse_mode: str = None) -> bool:
    """Sendet eine Nachricht an den konfigurierten Telegram-Chat."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for i in range(0, len(text), 4000):
        chunk = text[i : i + 4000]
        payload = {"chat_id": CHAT_ID, "text": chunk}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        resp = requests.post(url, json=payload, timeout=10)
        if not resp.ok:
            print(f"Telegram-Fehler: {resp.text}", file=sys.stderr)
            return False
    return True


def send_photo(photo_path: str, caption: str = "") -> bool:
    """Sendet ein Foto an den konfigurierten Telegram-Chat."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(photo_path, "rb") as f:
        resp = requests.post(
            url,
            data={"chat_id": CHAT_ID, "caption": caption},
            files={"photo": f},
            timeout=30,
        )
    return resp.ok


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Test-Nachricht vom Claude Code Bot"
    if send_message(msg):
        print("Nachricht gesendet.")
    else:
        print("Fehler beim Senden.", file=sys.stderr)
