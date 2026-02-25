#!/usr/bin/env python3
"""Zwei-Faktor-Authentifizierung per E-Mail für den Telegram-Bot."""

import logging
import os
import secrets
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

log = logging.getLogger("telegram_bridge.auth")

SMTP_EMAIL = os.getenv("SMTP_EMAIL", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")


def generate_code() -> str:
    """Generiert einen 6-stelligen Zufallscode."""
    return f"{secrets.randbelow(1_000_000):06d}"


def send_2fa_email(code: str, recipient: str = None) -> bool:
    """Sendet den 2FA-Code per Gmail SMTP."""
    recipient = recipient or SMTP_EMAIL
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        log.error("SMTP_EMAIL oder SMTP_PASSWORD nicht in .env gesetzt")
        return False

    msg = MIMEText(
        f"Dein 2FA-Code für den Telegram-Bot:\n\n"
        f"    {code}\n\n"
        f"Gültig für 10 Minuten.\n"
        f"Gib den Code im Telegram-Chat ein.",
        "plain",
        "utf-8",
    )
    msg["Subject"] = f"Telegram Bot 2FA: {code}"
    msg["From"] = SMTP_EMAIL
    msg["To"] = recipient

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)
        log.info("2FA-Code per E-Mail gesendet an %s", recipient)
        return True
    except Exception as e:
        log.exception("Fehler beim Senden der 2FA-E-Mail: %s", e)
        return False


class TwoFactorAuth:
    """Verwaltet den 2FA-Status des Bots."""

    def __init__(self):
        self.code: str = ""
        self.expires: datetime = datetime.min
        self.verified: bool = False

    def generate_and_send(self) -> bool:
        """Generiert neuen Code und sendet ihn per E-Mail."""
        self.code = generate_code()
        self.expires = datetime.now() + timedelta(minutes=10)
        self.verified = False
        log.info("Neuer 2FA-Code generiert, gültig bis %s", self.expires.strftime("%H:%M:%S"))
        return send_2fa_email(self.code)

    def check_code(self, user_code: str) -> bool:
        """Prüft den eingegebenen Code."""
        if datetime.now() > self.expires:
            log.warning("2FA-Code abgelaufen")
            return False
        if user_code.strip() == self.code:
            self.verified = True
            log.info("2FA erfolgreich verifiziert")
            return True
        log.warning("Falscher 2FA-Code eingegeben: %s", user_code)
        return False

    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.expires and not self.verified
