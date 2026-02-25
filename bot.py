#!/usr/bin/env python3
"""Bidirektionaler Telegram-Bot als Kommunikationskanal für Claude Code."""

import os
import asyncio
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction

load_dotenv(Path(__file__).parent / ".env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
WORKING_DIR = Path(__file__).parent
LOG_DIR = WORKING_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# --- Logging Setup ---
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
LOG_FILE = LOG_DIR / "bot.log"

logging.basicConfig(
    format=LOG_FORMAT,
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8"),
    ],
)
log = logging.getLogger("telegram_bridge")


def is_authorized(update: Update) -> bool:
    """Nur autorisierte Chat-ID zulassen."""
    chat_id = update.effective_chat.id
    if chat_id != ALLOWED_CHAT_ID:
        user = update.effective_user
        log.warning("Unautorisierter Zugriff von chat_id=%s user=%s (@%s)", chat_id, user.full_name if user else "?", user.username if user else "?")
        return False
    return True


async def split_send(update: Update, text: str):
    """Sendet lange Nachrichten in Teilen (Telegram-Limit: 4096 Zeichen)."""
    if not text.strip():
        await update.message.reply_text("(keine Ausgabe)")
        return
    for i in range(0, len(text), 4000):
        chunk = text[i : i + 4000]
        await update.message.reply_text(chunk)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    log.info("CMD /start von %s", update.effective_user.username)
    await update.message.reply_text(
        "Claude Code Telegram Bridge aktiv.\n\n"
        "/claude <nachricht> - Nachricht an Claude Code senden\n"
        "/bash <befehl> - Shell-Befehl ausführen\n"
        "/status - Bot-Status anzeigen\n"
        "/playwright <url> - Screenshot einer Webseite\n\n"
        f"Autorisierte Chat-ID: {ALLOWED_CHAT_ID}"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    log.info("CMD /status von %s", update.effective_user.username)
    log_size = LOG_FILE.stat().st_size if LOG_FILE.exists() else 0
    await update.message.reply_text(
        f"Bot läuft.\n"
        f"Chat-ID: {update.effective_chat.id}\n"
        f"Working Dir: {WORKING_DIR}\n"
        f"Log: {LOG_FILE} ({log_size / 1024:.1f} KB)"
    )


async def cmd_claude(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nachricht an Claude Code senden und Antwort zurückgeben."""
    if not is_authorized(update):
        return

    prompt = " ".join(context.args) if context.args else ""
    if not prompt:
        await update.message.reply_text("Verwendung: /claude <deine Nachricht>")
        return

    log.info("CMD /claude von %s: %s", update.effective_user.username, prompt[:100])
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        start = datetime.now()
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "--print",
            "--dangerously-skip-permissions",
            prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(WORKING_DIR),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        elapsed = (datetime.now() - start).total_seconds()
        output = stdout.decode().strip()
        if stderr.decode().strip():
            output += f"\n\n--- STDERR ---\n{stderr.decode().strip()}"
        log.info("Claude antwortete in %.1fs (%d Zeichen)", elapsed, len(output))
        await split_send(update, output)
    except asyncio.TimeoutError:
        log.error("Claude Timeout nach 300s für: %s", prompt[:100])
        await update.message.reply_text("Timeout: Claude Code hat nach 5 Minuten nicht geantwortet.")
    except FileNotFoundError:
        log.error("claude CLI nicht gefunden")
        await update.message.reply_text("Fehler: 'claude' CLI nicht gefunden. Ist Claude Code installiert?")
    except Exception as e:
        log.exception("Fehler bei /claude: %s", e)
        await update.message.reply_text(f"Fehler: {e}")


async def cmd_bash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shell-Befehl ausführen."""
    if not is_authorized(update):
        return

    command = " ".join(context.args) if context.args else ""
    if not command:
        await update.message.reply_text("Verwendung: /bash <befehl>")
        return

    log.info("CMD /bash von %s: %s", update.effective_user.username, command[:100])
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        start = datetime.now()
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(WORKING_DIR),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        elapsed = (datetime.now() - start).total_seconds()
        output = stdout.decode().strip()
        if stderr.decode().strip():
            output += f"\n\n--- STDERR ---\n{stderr.decode().strip()}"
        log.info("Bash fertig in %.1fs (exit=%d, %d Zeichen)", elapsed, proc.returncode, len(output))
        await split_send(update, output)
    except asyncio.TimeoutError:
        log.error("Bash Timeout nach 120s für: %s", command[:100])
        await update.message.reply_text("Timeout: Befehl hat nach 2 Minuten nicht geantwortet.")
    except Exception as e:
        log.exception("Fehler bei /bash: %s", e)
        await update.message.reply_text(f"Fehler: {e}")


async def cmd_playwright(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Screenshot einer Webseite mit Playwright erstellen und senden."""
    if not is_authorized(update):
        return

    url = " ".join(context.args) if context.args else ""
    if not url:
        await update.message.reply_text("Verwendung: /playwright <url>")
        return

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    log.info("CMD /playwright von %s: %s", update.effective_user.username, url)
    await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)

    try:
        from playwright.async_api import async_playwright

        start = datetime.now()
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 900})
            await page.goto(url, wait_until="networkidle", timeout=30000)
            screenshot_path = WORKING_DIR / "screenshot.png"
            await page.screenshot(path=str(screenshot_path), full_page=False)
            await browser.close()
        elapsed = (datetime.now() - start).total_seconds()
        log.info("Playwright Screenshot von %s in %.1fs", url, elapsed)

        await update.message.reply_photo(
            photo=open(screenshot_path, "rb"),
            caption=f"Screenshot: {url}",
        )
        screenshot_path.unlink(missing_ok=True)
    except Exception as e:
        log.exception("Playwright-Fehler für %s: %s", url, e)
        await update.message.reply_text(f"Playwright-Fehler: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Freitext-Nachrichten direkt an Claude Code weiterleiten."""
    if not is_authorized(update):
        return

    prompt = update.message.text
    if not prompt:
        return

    log.info("Freitext von %s: %s", update.effective_user.username, prompt[:100])
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        start = datetime.now()
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "--print",
            "--dangerously-skip-permissions",
            prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(WORKING_DIR),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        elapsed = (datetime.now() - start).total_seconds()
        output = stdout.decode().strip()
        if stderr.decode().strip():
            output += f"\n\n--- STDERR ---\n{stderr.decode().strip()}"
        log.info("Claude antwortete in %.1fs (%d Zeichen)", elapsed, len(output))
        await split_send(update, output)
    except asyncio.TimeoutError:
        log.error("Claude Timeout für Freitext: %s", prompt[:100])
        await update.message.reply_text("Timeout: Claude Code hat nach 5 Minuten nicht geantwortet.")
    except FileNotFoundError:
        log.error("claude CLI nicht gefunden")
        await update.message.reply_text("Fehler: 'claude' CLI nicht gefunden.")
    except Exception as e:
        log.exception("Fehler bei Freitext: %s", e)
        await update.message.reply_text(f"Fehler: {e}")


async def post_init(application: Application):
    """Bot-Kommandos registrieren."""
    await application.bot.set_my_commands([
        BotCommand("start", "Bot starten / Hilfe"),
        BotCommand("claude", "Nachricht an Claude Code"),
        BotCommand("bash", "Shell-Befehl ausführen"),
        BotCommand("playwright", "Screenshot einer URL"),
        BotCommand("status", "Bot-Status"),
    ])


def main():
    if not BOT_TOKEN:
        print("FEHLER: TELEGRAM_BOT_TOKEN nicht in .env gesetzt!")
        return

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("claude", cmd_claude))
    app.add_handler(CommandHandler("bash", cmd_bash))
    app.add_handler(CommandHandler("playwright", cmd_playwright))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("=== Bot gestartet === PID=%d, Chat-ID=%d, Working Dir=%s", os.getpid(), ALLOWED_CHAT_ID, WORKING_DIR)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
