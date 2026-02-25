#!/usr/bin/env python3
"""Bidirektionaler Telegram-Bot als Kommunikationskanal für Claude Code."""

import json
import os
import sys
import asyncio
import logging
import subprocess
import tempfile
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

import browser as mcp_browser

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

# --- Agenten-System ---
AGENTS_FILE = WORKING_DIR / "agents.json"
ACTIVE_AGENT = {}  # Wird beim Start geladen


def load_agents() -> dict:
    """Lädt die Agenten-Konfiguration aus agents.json."""
    if not AGENTS_FILE.exists():
        return {"default": "assistant", "agents": {}}
    with open(AGENTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_active_agent() -> dict:
    """Gibt den aktiven Agenten zurück."""
    config = load_agents()
    agent_id = ACTIVE_AGENT.get("id", config.get("default", "assistant"))
    agents = config.get("agents", {})
    if agent_id in agents:
        agent = agents[agent_id]
        agent["id"] = agent_id
        return agent
    # Fallback: erster Agent oder leer
    if agents:
        first_id = next(iter(agents))
        agent = agents[first_id]
        agent["id"] = first_id
        return agent
    return {"id": "default", "name": "Standard", "emoji": "🤖", "system_prompt": "", "model": "opus"}


def build_claude_cmd(prompt: str, agent: dict = None) -> list:
    """Baut den Claude-CLI-Befehl mit Agent-System-Prompt."""
    if agent is None:
        agent = get_active_agent()
    cmd = ["claude", "--print", "--continue", "--dangerously-skip-permissions"]
    system_prompt = agent.get("system_prompt", "")
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]
    model = agent.get("model")
    if model:
        cmd += ["--model", model]
    cmd.append(prompt)
    return cmd


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
        "/browse <url> - Website öffnen (Screenshot + Inhalt)\n"
        "/snap - Aktuelle Seite als Text anzeigen\n"
        "/click <ref> - Element anklicken\n"
        "/type <ref> | <text> - Text eingeben\n"
        "/tabs - Offene Browser-Tabs\n"
        "/status - Bot-Status anzeigen\n"
        "/restart - Bot neu starten\n"
        "Foto senden - Bild analysieren\n\n"
        "Browser-Session bleibt persistent!\n"
        f"Autorisierte Chat-ID: {ALLOWED_CHAT_ID}"
    )


async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot neu starten über start.sh."""
    if not is_authorized(update):
        return

    log.info("CMD /restart von %s", update.effective_user.username)
    await update.message.reply_text("Bot wird neu gestartet...")

    start_script = WORKING_DIR / "start.sh"
    if not start_script.exists():
        await update.message.reply_text("Fehler: start.sh nicht gefunden!")
        return

    # start.sh als losgelösten Prozess starten — es killt den aktuellen Bot und startet neu
    subprocess.Popen(
        ["/bin/bash", str(start_script)],
        cwd=str(WORKING_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    log.info("start.sh gestartet, Bot wird gleich beendet...")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    log.info("CMD /status von %s", update.effective_user.username)
    log_size = LOG_FILE.stat().st_size if LOG_FILE.exists() else 0
    agent = get_active_agent()
    mcp_status = "läuft" if mcp_browser.is_mcp_running() else "gestoppt"
    await update.message.reply_text(
        f"Bot läuft.\n"
        f"Agent: {agent.get('emoji', '')} {agent.get('name', '?')} ({agent.get('id', '?')})\n"
        f"MCP Playwright: {mcp_status}\n"
        f"Chat-ID: {update.effective_chat.id}\n"
        f"Working Dir: {WORKING_DIR}\n"
        f"Log: {LOG_FILE} ({log_size / 1024:.1f} KB)"
    )


async def cmd_agents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verfügbare Agenten auflisten."""
    if not is_authorized(update):
        return
    log.info("CMD /agents von %s", update.effective_user.username)
    config = load_agents()
    agents = config.get("agents", {})
    active = get_active_agent()

    lines = ["Verfügbare Agenten:\n"]
    for aid, agent in agents.items():
        marker = " ← aktiv" if aid == active.get("id") else ""
        lines.append(f"{agent.get('emoji', '')} /{aid} - {agent.get('name', aid)}{marker}")
    lines.append(f"\nWechseln: /agent <name>")
    await update.message.reply_text("\n".join(lines))


async def cmd_agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Agent wechseln."""
    if not is_authorized(update):
        return

    agent_id = context.args[0] if context.args else ""
    if not agent_id:
        await cmd_agents(update, context)
        return

    config = load_agents()
    agents = config.get("agents", {})

    if agent_id not in agents:
        await update.message.reply_text(
            f"Agent '{agent_id}' nicht gefunden.\n"
            f"Verfügbar: {', '.join(agents.keys())}"
        )
        return

    ACTIVE_AGENT["id"] = agent_id
    agent = agents[agent_id]
    log.info("Agent gewechselt zu: %s (%s)", agent_id, agent.get("name"))
    await update.message.reply_text(
        f"{agent.get('emoji', '')} Agent gewechselt: {agent.get('name', agent_id)}\n"
        f"Rolle: {agent.get('system_prompt', '')[:200]}"
    )


async def cmd_claude(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nachricht an Claude Code senden und Antwort zurückgeben."""
    if not is_authorized(update):
        return

    prompt = " ".join(context.args) if context.args else ""
    if not prompt:
        await update.message.reply_text("Verwendung: /claude <deine Nachricht>")
        return

    agent = get_active_agent()
    log.info("CMD /claude [%s] von %s: %s", agent["id"], update.effective_user.username, prompt[:100])
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        start = datetime.now()
        cmd = build_claude_cmd(prompt, agent)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(WORKING_DIR),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        elapsed = (datetime.now() - start).total_seconds()
        output = stdout.decode().strip()
        if stderr.decode().strip():
            output += f"\n\n--- STDERR ---\n{stderr.decode().strip()}"
        log.info("Claude [%s] antwortete in %.1fs (%d Zeichen)", agent["id"], elapsed, len(output))
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


async def cmd_browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Website über MCP Playwright öffnen und Screenshot + Snapshot senden."""
    if not is_authorized(update):
        return

    url = " ".join(context.args) if context.args else ""
    if not url:
        await update.message.reply_text("Verwendung: /browse <url>")
        return

    log.info("CMD /browse von %s: %s", update.effective_user.username, url)
    await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)

    try:
        start = datetime.now()
        img_bytes, snap_text = await mcp_browser.screenshot(url)
        elapsed = (datetime.now() - start).total_seconds()
        log.info("MCP Browse %s in %.1fs", url, elapsed)

        if img_bytes:
            from io import BytesIO
            await update.message.reply_photo(
                photo=BytesIO(img_bytes),
                caption=f"Screenshot: {url}",
            )

        if snap_text:
            await split_send(update, snap_text[:4000])
    except Exception as e:
        log.exception("MCP Browse-Fehler für %s: %s", url, e)
        await update.message.reply_text(f"Browse-Fehler: {e}")


async def cmd_snap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Aktuellen Seiteninhalt als Accessibility-Snapshot anzeigen."""
    if not is_authorized(update):
        return

    log.info("CMD /snap von %s", update.effective_user.username)
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        snap = await mcp_browser.get_snapshot()
        await split_send(update, snap)
    except Exception as e:
        log.exception("Snap-Fehler: %s", e)
        await update.message.reply_text(f"Snap-Fehler: {e}")


async def cmd_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Element auf der Seite anklicken (Accessibility-Ref)."""
    if not is_authorized(update):
        return

    element = " ".join(context.args) if context.args else ""
    if not element:
        await update.message.reply_text("Verwendung: /click <element-ref>\nZ.B. /click link 'Anmelden'")
        return

    log.info("CMD /click von %s: %s", update.effective_user.username, element)
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        start = datetime.now()
        result = await mcp_browser.click(element)
        elapsed = (datetime.now() - start).total_seconds()
        log.info("MCP Click '%s' in %.1fs", element, elapsed)
        await split_send(update, result[:4000])
    except Exception as e:
        log.exception("Click-Fehler: %s", e)
        await update.message.reply_text(f"Click-Fehler: {e}")


async def cmd_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Text in ein Eingabefeld tippen."""
    if not is_authorized(update):
        return

    args_text = " ".join(context.args) if context.args else ""
    if "|" not in args_text:
        await update.message.reply_text("Verwendung: /type <element-ref> | <text>\nZ.B. /type textbox 'Suche' | Hello World")
        return

    parts = args_text.split("|", 1)
    element = parts[0].strip()
    text = parts[1].strip()

    log.info("CMD /type von %s: '%s' -> '%s'", update.effective_user.username, element, text[:50])
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        start = datetime.now()
        result = await mcp_browser.type_text(element, text)
        elapsed = (datetime.now() - start).total_seconds()
        log.info("MCP Type in %.1fs", elapsed)
        await split_send(update, result[:4000])
    except Exception as e:
        log.exception("Type-Fehler: %s", e)
        await update.message.reply_text(f"Type-Fehler: {e}")


async def cmd_tabs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Offene Browser-Tabs anzeigen."""
    if not is_authorized(update):
        return

    log.info("CMD /tabs von %s", update.effective_user.username)
    try:
        result = await mcp_browser.list_tabs()
        await split_send(update, result)
    except Exception as e:
        log.exception("Tabs-Fehler: %s", e)
        await update.message.reply_text(f"Tabs-Fehler: {e}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foto empfangen, speichern und von Claude analysieren lassen."""
    if not is_authorized(update):
        return

    caption = update.message.caption or "Analysiere dieses Bild detailliert. Beschreibe was du siehst."
    log.info("Foto von %s (caption: %s)", update.effective_user.username, caption[:100])
    await update.message.chat.send_action(ChatAction.TYPING)

    # Höchste Auflösung nehmen (letztes Element in der Liste)
    photo = update.message.photo[-1]
    file = await photo.get_file()

    # Bild in temporäre Datei speichern
    tmp_path = WORKING_DIR / f"_tmp_photo_{update.message.message_id}.jpg"
    try:
        await file.download_to_drive(str(tmp_path))
        log.info("Foto gespeichert: %s (%d bytes)", tmp_path, tmp_path.stat().st_size)

        prompt = (
            f"Lies die Bilddatei '{tmp_path}' mit dem Read-Tool und analysiere sie. "
            f"Anweisung des Users: {caption}"
        )

        agent = get_active_agent()
        start = datetime.now()
        cmd = build_claude_cmd(prompt, agent)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(WORKING_DIR),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        elapsed = (datetime.now() - start).total_seconds()
        output = stdout.decode().strip()
        if stderr.decode().strip():
            output += f"\n\n--- STDERR ---\n{stderr.decode().strip()}"
        log.info("Bildanalyse [%s] in %.1fs (%d Zeichen)", agent["id"], elapsed, len(output))
        await split_send(update, output)
    except asyncio.TimeoutError:
        log.error("Timeout bei Bildanalyse")
        await update.message.reply_text("Timeout: Bildanalyse hat nach 5 Minuten nicht geantwortet.")
    except Exception as e:
        log.exception("Fehler bei Bildanalyse: %s", e)
        await update.message.reply_text(f"Fehler bei Bildanalyse: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Freitext-Nachrichten direkt an Claude Code weiterleiten."""
    if not is_authorized(update):
        return

    prompt = update.message.text
    if not prompt:
        return

    agent = get_active_agent()
    log.info("Freitext [%s] von %s: %s", agent["id"], update.effective_user.username, prompt[:100])
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        start = datetime.now()
        cmd = build_claude_cmd(prompt, agent)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(WORKING_DIR),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        elapsed = (datetime.now() - start).total_seconds()
        output = stdout.decode().strip()
        if stderr.decode().strip():
            output += f"\n\n--- STDERR ---\n{stderr.decode().strip()}"
        log.info("Claude [%s] antwortete in %.1fs (%d Zeichen)", agent["id"], elapsed, len(output))
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
        BotCommand("agent", "Agent wechseln"),
        BotCommand("agents", "Agenten auflisten"),
        BotCommand("claude", "Nachricht an Claude Code"),
        BotCommand("bash", "Shell-Befehl ausführen"),
        BotCommand("browse", "Website öffnen (MCP Playwright)"),
        BotCommand("snap", "Aktuelle Seite als Text"),
        BotCommand("click", "Element anklicken"),
        BotCommand("type", "Text in Feld eingeben"),
        BotCommand("tabs", "Offene Browser-Tabs"),
        BotCommand("status", "Bot-Status"),
        BotCommand("restart", "Bot neu starten"),
    ])


def main():
    if not BOT_TOKEN:
        print("FEHLER: TELEGRAM_BOT_TOKEN nicht in .env gesetzt!")
        return

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("restart", cmd_restart))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("claude", cmd_claude))
    app.add_handler(CommandHandler("bash", cmd_bash))
    app.add_handler(CommandHandler("browse", cmd_browse))
    app.add_handler(CommandHandler("snap", cmd_snap))
    app.add_handler(CommandHandler("click", cmd_click))
    app.add_handler(CommandHandler("type", cmd_type))
    app.add_handler(CommandHandler("tabs", cmd_tabs))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("=== Bot gestartet === PID=%d, Chat-ID=%d, Working Dir=%s", os.getpid(), ALLOWED_CHAT_ID, WORKING_DIR)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
