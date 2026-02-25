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

from lib.auth import TwoFactorAuth
from lib.worker import log_request

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

# --- 2FA ---
tfa = TwoFactorAuth()

# --- Agenten-System ---
AGENTS_FILE = WORKING_DIR / "config" / "agents.json"
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
    return {"id": "default", "name": "Standard", "emoji": "\U0001f916", "system_prompt": "", "model": "opus"}


MCP_CONFIG_FILE = WORKING_DIR / "config" / "mcp_config.json"


def build_claude_cmd(prompt: str, agent: dict = None) -> list:
    """Baut den Claude-CLI-Befehl mit Agent-System-Prompt und MCP Playwright."""
    if agent is None:
        agent = get_active_agent()
    cmd = ["claude", "--print", "--continue", "--dangerously-skip-permissions"]
    # MCP Playwright SSE-Server einbinden (persistente Session auf Port 8931)
    if MCP_CONFIG_FILE.exists():
        cmd += ["--mcp-config", str(MCP_CONFIG_FILE)]
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


async def cmd_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Neuen 2FA-Code anfordern."""
    if not is_authorized(update):
        return
    log.info("CMD /2fa von %s", update.effective_user.username)
    if tfa.generate_and_send():
        await update.message.reply_text("Neuer 2FA-Code wurde per E-Mail gesendet. Bitte eingeben:")
    else:
        await update.message.reply_text("Fehler beim Senden des 2FA-Codes. Prüfe SMTP-Einstellungen in .env.")


async def handle_2fa_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prüft 2FA-Code-Eingabe (höchste Priorität, Gruppe -1)."""
    if not is_authorized(update):
        return
    if tfa.verified:
        return  # Bereits verifiziert, normalen Flow weiterlaufen lassen

    text = (update.message.text or "").strip()
    if not text:
        return

    if tfa.check_code(text):
        await update.message.reply_text("2FA erfolgreich! Bot ist jetzt freigeschaltet.")
    elif tfa.is_expired:
        await update.message.reply_text("2FA-Code abgelaufen. Nutze /2fa für einen neuen Code.")
    else:
        await update.message.reply_text("Falscher Code. Bitte 2FA-Code eingeben:")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not tfa.verified:
        await update.message.reply_text("Bot ist gesperrt. Bitte 2FA-Code eingeben:")
        return
    log.info("CMD /start von %s", update.effective_user.username)
    agent = get_active_agent()
    await log_request(update.effective_user.username, "/start", "", agent.get("name", "?"))
    await update.message.reply_text(
        f"Claude Code Telegram Bridge aktiv.\n"
        f"Aktiver Agent: {agent.get('emoji', '')} {agent.get('name', '?')}\n\n"
        "--- Agenten ---\n"
        "/agent <name> - Agent wechseln\n"
        "/agents - Alle Agenten anzeigen\n\n"
        "--- Claude ---\n"
        "/claude <nachricht> - Nachricht senden\n"
        "Freitext / Foto - Direkt an Agent\n\n"
        "--- Tools ---\n"
        "/vorlesen <text> - Text als Audio vorlesen\n"
        "(auch als Reply auf eine Nachricht)\n\n"
        "--- System ---\n"
        "/bash <befehl> - Shell ausführen\n"
        "/2fa - Neuen 2FA-Code anfordern\n"
        "/status - Bot-Status\n"
        "/restart - Bot neustarten"
    )


async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot neu starten über start.sh."""
    if not is_authorized(update):
        return
    if not tfa.verified:
        await update.message.reply_text("Bot ist gesperrt. Bitte 2FA-Code eingeben:")
        return

    log.info("CMD /restart von %s", update.effective_user.username)
    await log_request(update.effective_user.username, "/restart", "", "System")
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
    if not tfa.verified:
        await update.message.reply_text("Bot ist gesperrt. Bitte 2FA-Code eingeben:")
        return
    log.info("CMD /status von %s", update.effective_user.username)
    log_size = LOG_FILE.stat().st_size if LOG_FILE.exists() else 0
    agent = get_active_agent()
    await log_request(update.effective_user.username, "/status", "", agent.get("name", "?"))
    await update.message.reply_text(
        f"Bot läuft.\n"
        f"Agent: {agent.get('emoji', '')} {agent.get('name', '?')} ({agent.get('id', '?')})\n"
        f"Chat-ID: {update.effective_chat.id}\n"
        f"Working Dir: {WORKING_DIR}\n"
        f"Log: {LOG_FILE} ({log_size / 1024:.1f} KB)\n"
        f"2FA: verifiziert"
    )


async def cmd_agents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verfügbare Agenten auflisten."""
    if not is_authorized(update):
        return
    if not tfa.verified:
        await update.message.reply_text("Bot ist gesperrt. Bitte 2FA-Code eingeben:")
        return
    log.info("CMD /agents von %s", update.effective_user.username)
    config = load_agents()
    agents = config.get("agents", {})
    active = get_active_agent()

    lines = ["Verfügbare Agenten:\n"]
    for aid, agent in agents.items():
        marker = " \u2190 aktiv" if aid == active.get("id") else ""
        lines.append(f"{agent.get('emoji', '')} /{aid} - {agent.get('name', aid)}{marker}")
    lines.append(f"\nWechseln: /agent <name>")
    await update.message.reply_text("\n".join(lines))


async def cmd_agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Agent wechseln."""
    if not is_authorized(update):
        return
    if not tfa.verified:
        await update.message.reply_text("Bot ist gesperrt. Bitte 2FA-Code eingeben:")
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
    await log_request(update.effective_user.username, "/agent", agent_id, agent.get("name", "?"))
    await update.message.reply_text(
        f"{agent.get('emoji', '')} Agent gewechselt: {agent.get('name', agent_id)}\n"
        f"Rolle: {agent.get('system_prompt', '')[:200]}"
    )


async def cmd_claude(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nachricht an Claude Code senden und Antwort zurückgeben."""
    if not is_authorized(update):
        return
    if not tfa.verified:
        await update.message.reply_text("Bot ist gesperrt. Bitte 2FA-Code eingeben:")
        return

    prompt = " ".join(context.args) if context.args else ""
    if not prompt:
        await update.message.reply_text("Verwendung: /claude <deine Nachricht>")
        return

    agent = get_active_agent()
    log.info("CMD /claude [%s] von %s: %s", agent["id"], update.effective_user.username, prompt[:100])
    await log_request(update.effective_user.username, "/claude", prompt, agent.get("name", "?"))
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
    if not tfa.verified:
        await update.message.reply_text("Bot ist gesperrt. Bitte 2FA-Code eingeben:")
        return

    command = " ".join(context.args) if context.args else ""
    if not command:
        await update.message.reply_text("Verwendung: /bash <befehl>")
        return

    log.info("CMD /bash von %s: %s", update.effective_user.username, command[:100])
    await log_request(update.effective_user.username, "/bash", command, "System")
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


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foto empfangen, speichern und von Claude analysieren lassen."""
    if not is_authorized(update):
        return
    if not tfa.verified:
        await update.message.reply_text("Bot ist gesperrt. Bitte 2FA-Code eingeben:")
        return

    caption = update.message.caption or "Analysiere dieses Bild detailliert. Beschreibe was du siehst."
    log.info("Foto von %s (caption: %s)", update.effective_user.username, caption[:100])
    agent = get_active_agent()
    await log_request(update.effective_user.username, "Foto", caption, agent.get("name", "?"))
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
    if not tfa.verified:
        # 2FA-Check wird in handle_2fa_check (Gruppe -1) behandelt
        return

    prompt = update.message.text
    if not prompt:
        return

    agent = get_active_agent()
    log.info("Freitext [%s] von %s: %s", agent["id"], update.effective_user.username, prompt[:100])
    await log_request(update.effective_user.username, "Freitext", prompt, agent.get("name", "?"))
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


async def cmd_vorlesen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Text als Audio-Nachricht vorlesen (Text-to-Speech)."""
    if not is_authorized(update):
        return
    if not tfa.verified:
        await update.message.reply_text("Bot ist gesperrt. Bitte 2FA-Code eingeben:")
        return

    text = " ".join(context.args) if context.args else ""

    # Wenn als Reply auf eine Nachricht → deren Text vorlesen
    if not text and update.message.reply_to_message:
        text = update.message.reply_to_message.text or ""

    if not text:
        await update.message.reply_text(
            "Verwendung:\n"
            "/vorlesen <text> - Text vorlesen\n"
            "Oder: Auf eine Nachricht antworten mit /vorlesen"
        )
        return

    log.info("CMD /vorlesen von %s: %s", update.effective_user.username, text[:100])
    await log_request(update.effective_user.username, "/vorlesen", text, "TTS")
    await update.message.chat.send_action(ChatAction.RECORD_VOICE)

    try:
        from gtts import gTTS
        from io import BytesIO

        start = datetime.now()
        tts = gTTS(text=text, lang="de")
        audio_buffer = BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        elapsed = (datetime.now() - start).total_seconds()

        log.info("TTS generiert in %.1fs (%d Zeichen, %d bytes)", elapsed, len(text), audio_buffer.getbuffer().nbytes)

        await update.message.reply_voice(
            voice=audio_buffer,
            caption=text[:200] if len(text) > 200 else None,
        )
    except Exception as e:
        log.exception("Vorlesen-Fehler: %s", e)
        await update.message.reply_text(f"Vorlesen-Fehler: {e}")


async def post_init(application: Application):
    """Bot-Kommandos registrieren und 2FA starten."""
    await application.bot.set_my_commands([
        BotCommand("start", "Bot starten / Hilfe"),
        BotCommand("agent", "Agent wechseln"),
        BotCommand("agents", "Agenten auflisten"),
        BotCommand("claude", "Nachricht an Claude Code"),
        BotCommand("bash", "Shell-Befehl ausführen"),
        BotCommand("vorlesen", "Text als Audio vorlesen"),
        BotCommand("2fa", "Neuen 2FA-Code anfordern"),
        BotCommand("status", "Bot-Status"),
        BotCommand("restart", "Bot neu starten"),
    ])
    # 2FA-Code generieren und senden
    log.info("Sende 2FA-Code per E-Mail...")
    if tfa.generate_and_send():
        log.info("2FA-Code gesendet. Bot wartet auf Verifizierung.")
    else:
        log.error("2FA-Code konnte nicht gesendet werden! Prüfe SMTP-Einstellungen.")


def main():
    if not BOT_TOKEN:
        print("FEHLER: TELEGRAM_BOT_TOKEN nicht in .env gesetzt!")
        return

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # 2FA-Handler mit höchster Priorität (Gruppe -1)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_2fa_check), group=-1)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("2fa", cmd_2fa))
    app.add_handler(CommandHandler("agent", cmd_agent))
    app.add_handler(CommandHandler("agents", cmd_agents))
    app.add_handler(CommandHandler("restart", cmd_restart))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("claude", cmd_claude))
    app.add_handler(CommandHandler("bash", cmd_bash))
    app.add_handler(CommandHandler("vorlesen", cmd_vorlesen))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    agent = get_active_agent()
    log.info("=== Bot gestartet === PID=%d, Agent=%s, Chat-ID=%d, Working Dir=%s", os.getpid(), agent["id"], ALLOWED_CHAT_ID, WORKING_DIR)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
