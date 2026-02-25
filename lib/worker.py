#!/usr/bin/env python3
"""Worker-Bot: Spiegelt eingehende Requests über einen separaten Bot."""

import logging
import os
from datetime import datetime
from pathlib import Path

import requests as http_requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

log = logging.getLogger("telegram_bridge.worker")

WORKER_BOT_TOKEN = os.getenv("TELEGRAM_WORKER_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


async def log_request(user: str, request_type: str, content: str, agent: str = "Assistant"):
    """Sendet eine formatierte Request-Info über den Worker-Bot."""
    if not WORKER_BOT_TOKEN:
        log.warning("TELEGRAM_WORKER_BOT_TOKEN nicht gesetzt, Worker-Log übersprungen")
        return

    now = datetime.now().strftime("%H:%M:%S")
    preview = content[:200] if content else "(leer)"

    text = (
        f"📋 Request\n"
        f"👤 @{user}\n"
        f"📌 {request_type}\n"
        f"💬 {preview}\n"
        f"🤖 Agent: {agent}\n"
        f"🕐 {now}"
    )

    url = f"https://api.telegram.org/bot{WORKER_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}

    try:
        resp = http_requests.post(url, json=payload, timeout=5)
        if not resp.ok:
            log.warning("Worker-Bot Fehler: %s", resp.text)
    except Exception as e:
        log.warning("Worker-Bot nicht erreichbar: %s", e)
