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
    ApplicationHandlerStop,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction

from lib.auth import TwoFactorAuth
# worker/metrics entfernt (Telemetrie-Fehler + nicht benötigt)
from lib.rag_integration import RAGIntegration
from lib.claude_pipe import ClaudePipe
from lib.scheduler import TaskScheduler
from lib.reminders import ReminderManager
from lib.knowledge_sync import KnowledgeSync

load_dotenv(Path(__file__).parent / ".env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
WORKING_DIR = Path(__file__).parent
LOG_DIR = WORKING_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
DATA_DIR = WORKING_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# --- Logging Setup ---
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
LOG_FILE = LOG_DIR / "bot.log"

log = logging.getLogger("telegram_bridge")
log.setLevel(logging.INFO)

# Nur Handler hinzufügen wenn noch keine vorhanden (verhindert Dopplungen)
if not log.handlers:
    _formatter = logging.Formatter(LOG_FORMAT)
    _fh = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    _fh.setFormatter(_formatter)
    log.addHandler(_fh)

# Root-Logger ruhigstellen (keine doppelten Einträge)
logging.basicConfig(level=logging.WARNING)

# --- 2FA ---
tfa = TwoFactorAuth()

# --- RAG (Retrieval-Augmented Generation) ---
rag = RAGIntegration()
reminder_mgr = ReminderManager()

# --- Knowledge Sync ---
knowledge_sync = KnowledgeSync()

# --- Scheduler ---
scheduler: TaskScheduler = None  # Wird in post_init gestartet

# --- Agenten-System ---
AGENTS_FILE = WORKING_DIR / "config" / "agents.json"
ACTIVE_AGENT = {}  # Wird beim Start geladen

# --- Claude Pipe (persistente Session + Queue) ---
CURRENT_JOBS_FILE = Path("data/current_jobs.json")


def _write_current_jobs(current_jobs: dict):
    """Write currently running jobs to data/current_jobs.json for dashboard."""
    try:
        jobs = []
        for agent_id, job in current_jobs.items():
            agent = job.get("agent", {})
            started = job.get("started")
            elapsed = round((datetime.now() - started).total_seconds(), 1) if started else 0
            jobs.append({
                "agent_id": agent.get("id", agent_id),
                "agent_name": agent.get("name", agent_id),
                "agent_emoji": agent.get("emoji", "🤖"),
                "title": job.get("title", "")[:80],
                "job_type": job.get("job_type", "text"),
                "started": started.isoformat() if started else None,
                "elapsed_seconds": elapsed,
                "source": "user",
            })
        CURRENT_JOBS_FILE.write_text(json.dumps(jobs, ensure_ascii=False, default=str))
    except Exception:
        pass


class PipeQueue:
    """Warteschlange die ClaudePipe für die Ausführung nutzt.

    Kombiniert die Queue-Logik (sequentielle Verarbeitung, Status-Tracking)
    mit dem persistenten Session-Management von ClaudePipe.
    """

    def __init__(self, pipe: ClaudePipe):
        self._pipe = pipe
        self._queues: dict[str, asyncio.Queue] = {}
        self._workers: dict[str, asyncio.Task] = {}
        self._current: dict[str, dict] = {}
        self._job_counter: int = 0
        self._history: list[dict] = []

    def _ensure_queue(self, agent_id: str):
        if agent_id not in self._queues:
            self._queues[agent_id] = asyncio.Queue()

    async def enqueue(self, agent_id: str, prompt: str, agent: dict,
                      chat_id: str, message, job_type: str = "text",
                      tmp_path: Path = None, title: str = None) -> int:
        """Fügt Job in Queue ein. Gibt Queue-Position zurück."""
        self._ensure_queue(agent_id)
        self._job_counter += 1
        job = {
            "id": self._job_counter,
            "prompt": prompt,
            "agent": agent,
            "chat_id": chat_id,
            "message": message,
            "job_type": job_type,
            "tmp_path": tmp_path,
            "title": title or prompt[:50],
            "enqueued": datetime.now(),
            "status": "⏳",
        }
        position = self._queues[agent_id].qsize()
        if agent_id in self._current:
            position += 1
        await self._queues[agent_id].put(job)
        log.info("📋 Queue [%s]: Job eingereiht (Position %d, Typ=%s, Prompt='%s...')",
                 agent_id, position, job_type, prompt[:50])

        if agent_id not in self._workers or self._workers[agent_id].done():
            self._workers[agent_id] = asyncio.create_task(self._worker(agent_id))
            log.info("🔧 Queue [%s]: Worker gestartet", agent_id)

        return position

    async def _worker(self, agent_id: str):
        """Sequentielle Job-Verarbeitung über ClaudePipe."""
        log.info("🔧 Worker [%s] gestartet", agent_id)
        try:
            while True:
                try:
                    job = await asyncio.wait_for(
                        self._queues[agent_id].get(), timeout=1800
                    )
                except asyncio.TimeoutError:
                    log.info("🔧 Worker [%s] beendet (30 Min ohne Jobs)", agent_id)
                    break

                self._current[agent_id] = job
                job["status"] = "🔄"
                job["started"] = datetime.now()
                self._add_history(job)
                _write_current_jobs(self._current)

                try:
                    await self._execute_job(agent_id, job)
                    job["status"] = "✅"
                    job["completed"] = datetime.now()
                except Exception as e:
                    log.exception("Worker [%s] Fehler bei Job: %s", agent_id, e)
                    job["status"] = "❌"
                    job["completed"] = datetime.now()
                    try:
                        await job["message"].reply_text(f"❌ Fehler: {e}")
                    except Exception:
                        pass
                finally:
                    self._persist_request(job)
                    self._current.pop(agent_id, None)
                    _write_current_jobs(self._current)
                    self._queues[agent_id].task_done()
        finally:
            self._workers.pop(agent_id, None)
            log.info("🔧 Worker [%s] beendet", agent_id)

    async def _execute_job(self, agent_id: str, job: dict):
        """Führt einen Job über ClaudePipe aus."""
        message = job["message"]
        typing = TypingLoop(message.chat)
        typing.start()

        # Progress-Ticker: sendet Zwischenstand alle 60s bei langen Aufgaben
        progress_event = asyncio.Event()

        async def _progress_ticker():
            """Sendet Chat-Updates alle 60s, damit User weiß dass Bot noch arbeitet."""
            wait_seconds = 60
            count = 0
            while not progress_event.is_set():
                try:
                    await asyncio.wait_for(progress_event.wait(), timeout=wait_seconds)
                    break  # Event gesetzt → fertig
                except asyncio.TimeoutError:
                    count += 1
                    mins = count
                    try:
                        await message.reply_text(
                            f"⏳ Arbeite noch... ({mins} Min)\n"
                            f"Aufgabe läuft weiter im Hintergrund."
                        )
                    except Exception:
                        pass  # Telegram-Fehler nicht blockierend

        ticker_task = asyncio.create_task(_progress_ticker())

        try:
            result = await self._pipe.execute(
                prompt=job["prompt"],
                agent=job["agent"],
                chat_id=job["chat_id"],
            )

            if result["error"]:
                await message.reply_text(f"❌ {result['error']}")
                return

            output = result["output"]
            if not output.strip():
                await message.reply_text("(keine Ausgabe)")
            else:
                for i in range(0, len(output), 4000):
                    await message.reply_text(output[i:i + 4000])
        finally:
            progress_event.set()
            ticker_task.cancel()
            # Temp-Dateien aufräumen (z.B. Fotos)
            if job.get("tmp_path"):
                job["tmp_path"].unlink(missing_ok=True)
            typing.stop()

    def _add_history(self, job: dict):
        self._history.append(job)
        if len(self._history) > 50:
            self._history = self._history[-50:]

    def _persist_request(self, job: dict):
        """Persist completed request to data/request_log.json for dashboard."""
        try:
            log_file = Path("data/request_log.json")
            entries = []
            if log_file.exists():
                try:
                    entries = json.loads(log_file.read_text())
                except (json.JSONDecodeError, ValueError):
                    entries = []

            agent = job.get("agent", {})
            entry = {
                "id": job.get("id", 0),
                "timestamp": (job.get("completed") or job.get("started") or job.get("enqueued", datetime.now())).isoformat(),
                "agent_id": agent.get("id", "?"),
                "agent_name": agent.get("name", "?"),
                "agent_emoji": agent.get("emoji", ""),
                "job_type": job.get("job_type", "text"),
                "title": job.get("title", "")[:80],
                "status": "success" if job.get("status") == "✅" else "error",
                "duration_seconds": round(
                    (job.get("completed", datetime.now()) - job.get("started", datetime.now())).total_seconds(), 1
                ) if job.get("started") and job.get("completed") else None,
                "source": "user",
            }
            entries.append(entry)
            # Keep last 200 entries
            entries = entries[-200:]
            log_file.write_text(json.dumps(entries, indent=2, ensure_ascii=False, default=str))
        except Exception as e:
            log.warning("Request-Log persist failed: %s", e)

    def queue_size(self, agent_id: str = None) -> int:
        if agent_id:
            pending = self._queues[agent_id].qsize() if agent_id in self._queues else 0
            running = 1 if agent_id in self._current else 0
            return pending + running
        return sum(
            (q.qsize() + (1 if aid in self._current else 0))
            for aid, q in self._queues.items()
        )

    def get_status(self) -> str:
        """Formatierter Queue-Status als Tabelle."""
        rows = []

        for job in self._history:
            ts = job.get("completed") or job.get("started") or job["enqueued"]
            rows.append({
                "id": job.get("id", "?"),
                "status": job.get("status", "?"),
                "title": job.get("title", job["prompt"][:40]),
                "time": ts.strftime("%H:%M:%S"),
            })

        for agent_id, q in self._queues.items():
            for queued_job in q._queue:
                if queued_job.get("id") not in [r["id"] for r in rows]:
                    rows.append({
                        "id": queued_job.get("id", "?"),
                        "status": "⏳",
                        "title": queued_job.get("title", queued_job["prompt"][:40]),
                        "time": queued_job["enqueued"].strftime("%H:%M:%S"),
                    })

        if not rows:
            return "📋 Warteschlange: leer"

        rows.sort(key=lambda r: r["id"] if isinstance(r["id"], int) else 0)

        lines = ["📋 Queue-Status:"]
        lines.append("ID  | Status | Zeit     | Titel")
        lines.append("----|--------|----------|------")
        for r in rows[-20:]:
            rid = str(r["id"]).rjust(3)
            lines.append(f"{rid} | {r['status']}     | {r['time']} | {r['title'][:45]}")

        pipe_status = self._pipe.get_status()
        lines.append(f"\n{pipe_status}")
        return "\n".join(lines)


# Globale Instanzen
claude_pipe = ClaudePipe(rag=rag)
claude_queue = PipeQueue(pipe=claude_pipe)


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


# --- Session-Verwaltung (delegiert an ClaudePipe) ---
# Die alten Funktionen load_sessions, save_sessions, get_session_info,
# reset_session, build_claude_cmd sind jetzt in lib/claude_pipe.py


def build_claude_cmd(prompt: str, agent: dict = None, chat_id: str = None) -> list:
    """Wrapper für Abwärtskompatibilität (Scheduler etc.)."""
    if agent is None:
        agent = get_active_agent()
    return claude_pipe.build_cmd(prompt, agent, chat_id)


class TypingLoop:
    """Sendet periodisch ChatAction.TYPING, solange Claude arbeitet."""

    def __init__(self, chat, interval: float = 4.0):
        self.chat = chat
        self.interval = interval
        self._task: asyncio.Task | None = None

    async def _loop(self):
        try:
            while True:
                try:
                    await self.chat.send_action(ChatAction.TYPING)
                except Exception:
                    pass  # Netzwerk-Fehler nicht blockierend – einfach weiter
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            pass

    def start(self):
        self._task = asyncio.create_task(self._loop())

    def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None


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
    log.info("[/2fa] Eingang von @%s (chat_id=%s)", update.effective_user.username, update.effective_chat.id)
    if not is_authorized(update):
        log.info("[/2fa] Abgelehnt: nicht autorisiert")
        return
    log.info("[/2fa] Generiere und sende neuen 2FA-Code...")
    if tfa.generate_and_send():
        log.info("[/2fa] Code gesendet, warte auf Eingabe")
        await update.message.reply_text("Neuer 2FA-Code wurde per E-Mail gesendet. Bitte eingeben:")
    else:
        log.error("[/2fa] Fehler beim Senden des Codes")
        await update.message.reply_text("Fehler beim Senden des 2FA-Codes. Prüfe SMTP-Einstellungen in .env.")


async def handle_2fa_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prüft 2FA-Code-Eingabe (höchste Priorität, Gruppe -1)."""
    log.info("[2FA-Check] Eingang von @%s", update.effective_user.username)
    if not is_authorized(update):
        log.info("[2FA-Check] Abgelehnt: nicht autorisiert")
        return
    if tfa.verified:
        log.info("[2FA-Check] Bereits verifiziert, weiter an Handler")
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    log.info("[2FA-Check] Code-Eingabe erhalten, prüfe...")
    if tfa.check_code(text):
        log.info("[2FA-Check] Code korrekt! Bot freigeschaltet")
        await update.message.reply_text("2FA erfolgreich! Bot ist jetzt freigeschaltet.")
        raise ApplicationHandlerStop
    elif tfa.is_expired:
        log.warning("[2FA-Check] Code abgelaufen")
        await update.message.reply_text("2FA-Code abgelaufen. Nutze /2fa für einen neuen Code.")
        raise ApplicationHandlerStop
    else:
        log.warning("[2FA-Check] Falscher Code eingegeben")
        await update.message.reply_text("Falscher Code. Bitte 2FA-Code eingeben:")
        raise ApplicationHandlerStop


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log.info("[/start] Eingang von @%s (chat_id=%s)", update.effective_user.username, update.effective_chat.id)
    if not is_authorized(update):
        log.info("[/start] Abgelehnt: nicht autorisiert")
        return
    if not tfa.verified:
        log.info("[/start] Abgelehnt: 2FA nicht verifiziert")
        await update.message.reply_text("Bot ist gesperrt. Bitte 2FA-Code eingeben:")
        return
    agent = get_active_agent()
    log.info("[/start] Agent=%s, sende Hilfe-Nachricht", agent.get("name", "?"))
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
        "/newsession - Frische Konversation\n"
        "/2fa - Neuen 2FA-Code anfordern\n"
        "/status - Bot-Status\n"
        "/restart - Bot neustarten"
    )


async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot neu starten über start.sh."""
    log.info("[/restart] Eingang von @%s", update.effective_user.username)
    if not is_authorized(update):
        log.info("[/restart] Abgelehnt: nicht autorisiert")
        return
    if not tfa.verified:
        log.info("[/restart] Abgelehnt: 2FA nicht verifiziert")
        await update.message.reply_text("Bot ist gesperrt. Bitte 2FA-Code eingeben:")
        return

    log.info("[/restart] Starte Bot neu...")
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
    log.info("[/status] Eingang von @%s", update.effective_user.username)
    if not is_authorized(update):
        log.info("[/status] Abgelehnt: nicht autorisiert")
        return
    if not tfa.verified:
        log.info("[/status] Abgelehnt: 2FA nicht verifiziert")
        await update.message.reply_text("Bot ist gesperrt. Bitte 2FA-Code eingeben:")
        return
    log_size = LOG_FILE.stat().st_size if LOG_FILE.exists() else 0
    agent = get_active_agent()
    log.info("[/status] Agent=%s, Log=%.1fKB", agent.get("name", "?"), log_size / 1024)
    log.info("[/status] Antwort gesendet")
    scheduler_info = scheduler.get_status() if scheduler else "Scheduler: nicht initialisiert"
    reminder_info = reminder_mgr.get_stats()
    queue_info = claude_queue.get_status()
    pipe_info = claude_pipe.get_status()
    await update.message.reply_text(
        f"Bot läuft.\n"
        f"Agent: {agent.get('emoji', '')} {agent.get('name', '?')} ({agent.get('id', '?')})\n"
        f"Chat-ID: {update.effective_chat.id}\n"
        f"Working Dir: {WORKING_DIR}\n"
        f"Log: {LOG_FILE} ({log_size / 1024:.1f} KB)\n"
        f"2FA: verifiziert\n\n"
        f"{pipe_info}\n\n"
        f"{queue_info}\n\n"
        f"{reminder_info}\n\n"
        f"{scheduler_info}"
    )


async def cmd_agents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verfügbare Agenten auflisten."""
    log.info("[/agents] Eingang von @%s", update.effective_user.username)
    if not is_authorized(update):
        log.info("[/agents] Abgelehnt: nicht autorisiert")
        return
    if not tfa.verified:
        log.info("[/agents] Abgelehnt: 2FA nicht verifiziert")
        await update.message.reply_text("Bot ist gesperrt. Bitte 2FA-Code eingeben:")
        return
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
    log.info("[/agent] Eingang von @%s", update.effective_user.username)
    if not is_authorized(update):
        log.info("[/agent] Abgelehnt: nicht autorisiert")
        return
    if not tfa.verified:
        log.info("[/agent] Abgelehnt: 2FA nicht verifiziert")
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
    await update.message.reply_text(
        f"{agent.get('emoji', '')} Agent gewechselt: {agent.get('name', agent_id)}\n"
        f"Rolle: {agent.get('system_prompt', '')[:200]}"
    )


CLAUDE_MAX_RUNTIME = 600  # Safety-Timeout: 10 Minuten max pro Aufruf


## _run_claude_background und _kill_old_claude entfernt – ersetzt durch ClaudeQueue


async def cmd_claude(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nachricht an Claude Code senden (asynchron im Hintergrund)."""
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
    # Job in Warteschlange einreihen
    chat_id = str(update.message.chat_id)
    agent_id = agent.get("id", "default")
    title = f"/claude: {prompt[:60]}"
    position = await claude_queue.enqueue(agent_id, prompt, agent, chat_id, update.message, title=title)
    if position == 0:
        await update.message.reply_text("⏳ Claude läuft...")
    else:
        await update.message.reply_text(f"📋 In Warteschlange (Position {position}): \"{title}\"\nDeine Anfrage wird bearbeitet sobald die vorherige fertig ist.")


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
    typing = TypingLoop(update.message.chat)
    typing.start()

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
    finally:
        typing.stop()


## _run_photo_analysis_background entfernt – ersetzt durch ClaudeQueue._execute_photo


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foto empfangen, speichern und von Claude analysieren lassen (asynchron)."""
    if not is_authorized(update):
        return
    if not tfa.verified:
        await update.message.reply_text("Bot ist gesperrt. Bitte 2FA-Code eingeben:")
        return

    caption = update.message.caption or "Analysiere dieses Bild detailliert. Beschreibe was du siehst."
    log.info("Foto von %s (caption: %s)", update.effective_user.username, caption[:100])
    agent = get_active_agent()
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

        # Job in Warteschlange einreihen
        chat_id = str(update.message.chat_id)
        agent_id = agent.get("id", "default")
        title = f"📷 Bild: {caption[:50]}"
        position = await claude_queue.enqueue(
            agent_id, prompt, agent, chat_id, update.message,
            job_type="photo", tmp_path=tmp_path, title=title
        )
        if position == 0:
            await update.message.reply_text("⏳ Bildanalyse läuft...")
        else:
            await update.message.reply_text(f"📋 Bildanalyse in Warteschlange (Position {position}): \"{title}\"")
    except Exception as e:
        log.exception("Fehler beim Foto-Download: %s", e)
        await update.message.reply_text(f"Fehler beim Foto-Download: {e}")
        tmp_path.unlink(missing_ok=True)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Freitext-Nachrichten direkt an Claude Code weiterleiten (asynchron im Hintergrund)."""
    if not is_authorized(update):
        return
    if not tfa.verified:
        # 2FA-Check wird in handle_2fa_check (Gruppe -1) behandelt
        return

    prompt = update.message.text
    if not prompt:
        return

    # Reminder-Erkennung (vor Claude-Call, als Side-Effect)
    if reminder_mgr.detect_reminder(prompt):
        try:
            r = reminder_mgr.parse_and_store(prompt, str(update.message.chat_id))
            if r:
                from datetime import datetime as dt_cls
                due = dt_cls.fromisoformat(r["due_date"]).strftime("%d.%m.%Y %H:%M")
                await update.message.reply_text(
                    f"🔔 Erinnerung gespeichert für {due}\n({r['text'][:80]})"
                )
        except Exception as e:
            log.warning("Reminder-Erkennung fehlgeschlagen: %s", e)

    agent = get_active_agent()
    log.info("Freitext [%s] von %s: %s", agent["id"], update.effective_user.username, prompt[:100])
    # Job in Warteschlange einreihen
    chat_id = str(update.message.chat_id)
    agent_id = agent.get("id", "default")
    title = prompt[:60]
    position = await claude_queue.enqueue(agent_id, prompt, agent, chat_id, update.message, title=title)
    if position == 0:
        await update.message.reply_text("⏳ Claude läuft...")
    else:
        await update.message.reply_text(f"📋 In Warteschlange (Position {position}): \"{title}\"\nDeine Anfrage wird bearbeitet sobald die vorherige fertig ist.")


async def cmd_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/queue – Warteschlangen-Status anzeigen."""
    if not is_authorized(update):
        return
    if not tfa.verified:
        await update.message.reply_text("Bot ist gesperrt. Bitte 2FA-Code eingeben:")
        return

    log.info("[/queue] von %s", update.effective_user.username)
    await update.message.reply_text(claude_queue.get_status())


async def cmd_newsession(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Session für aktiven Agenten zurücksetzen (frische Konversation)."""
    log.info("[/newsession] Eingang von @%s", update.effective_user.username)
    if not is_authorized(update):
        return
    if not tfa.verified:
        await update.message.reply_text("Bot ist gesperrt. Bitte 2FA-Code eingeben:")
        return

    agent = get_active_agent()
    agent_id = agent.get("id", "default")
    if claude_pipe.reset_session(agent_id):
        await update.message.reply_text(
            f"{agent.get('emoji', '')} Session für {agent.get('name', agent_id)} zurückgesetzt.\n"
            "Nächste Nachricht startet eine frische Konversation."
        )
    else:
        await update.message.reply_text(
            f"Keine aktive Session für {agent.get('name', agent_id)} vorhanden."
        )


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


async def cmd_cpu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/cpu – Claude CPU & Memory Auslastung anzeigen (kein Claude-Aufruf)."""
    if not is_authorized(update):
        return
    if not tfa.verified:
        return

    log.info("[/cpu] von %s", update.effective_user.username)

    try:
        cmd = (
            "echo '📊 Claude Prozesse:' && "
            "(ps aux --sort=-%cpu | grep '[c]laude' | head -5 | "
            "awk '{printf \"  PID=%-7s CPU=%5s%%  MEM=%5s%%  %s\\n\", $2, $3, $4, $11}' "
            "|| echo '  Keine Claude-Prozesse') && "
            "echo '' && echo '💻 System Load:' && "
            "cat /proc/loadavg | awk '{printf \"  Load: %s %s %s\\n\", $1, $2, $3}' && "
            "echo '' && echo '🧠 Memory:' && "
            "LC_ALL=C free -h | awk '/Mem/{printf \"  Total: %s  Used: %s  Free: %s\\n\", $2, $3, $4}'"
        )
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(WORKING_DIR),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        output = stdout.decode().strip()
        if not output:
            output = "Keine Claude-Prozesse gefunden."
        await update.message.reply_text(output)
    except Exception as e:
        log.exception("/cpu Fehler: %s", e)
        await update.message.reply_text(f"❌ Fehler: {e}")


async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/sync – Knowledge Base synchronisieren.

    Verwendung:
      /sync status  – Sync-Status aller Quellen anzeigen
      /sync drive   – Google Drive indexieren (lokal, 0 Tokens)
      /sync gmail   – Gmail-Cache in ChromaDB laden
      /sync calendar – Kalender-Cache in ChromaDB laden
      /sync contacts – Kontakte-Cache in ChromaDB laden
      /sync all     – Alle Quellen synchronisieren
    """
    if not is_authorized(update):
        return
    if not tfa.verified:
        await update.message.reply_text("Bot ist gesperrt. Bitte 2FA-Code eingeben:")
        return

    arg = context.args[0].lower() if context.args else "status"
    log.info("[/sync] %s von %s", arg, update.effective_user.username)

    if arg == "status":
        await update.message.reply_text(knowledge_sync.get_sync_status())
        return

    if arg == "drive":
        await update.message.reply_text("🔄 Drive-Sync gestartet...")
        typing = TypingLoop(update.message.chat)
        typing.start()
        try:
            start = datetime.now()
            result = knowledge_sync.sync_drive_all()
            elapsed = (datetime.now() - start).total_seconds()
            msg = (
                f"✅ Drive-Sync abgeschlossen in {elapsed:.1f}s:\n"
                f"  📁 Ordnerstruktur: {result.get('structure_lines', 0)} Zeilen\n"
                f"  📄 Textdateien: {result.get('documents', 0)} neu indexiert\n"
                f"  📑 PDF-Katalog: {result.get('pdfs', 0)} PDFs"
            )
            await update.message.reply_text(msg)
        except Exception as e:
            log.exception("/sync drive Fehler: %s", e)
            await update.message.reply_text(f"❌ Drive-Sync Fehler: {e}")
        finally:
            typing.stop()
        return

    if arg in ("gmail", "calendar", "contacts"):
        # Lade gespeicherte JSON-Daten aus data/sync_*.json → ChromaDB
        await update.message.reply_text(f"🔄 Lade {arg}-Daten in ChromaDB...")
        try:
            count = knowledge_sync.load_and_store(arg)
            await update.message.reply_text(f"✅ {arg.title()}: {count} Einträge in ChromaDB gespeichert.")
        except FileNotFoundError:
            await update.message.reply_text(
                f"⚠️ Keine {arg}-Daten vorhanden.\n"
                f"Starte zuerst den datasync-Agent: /scheduler run sync_{arg}"
            )
        except Exception as e:
            log.exception("/sync %s Fehler: %s", arg, e)
            await update.message.reply_text(f"❌ {arg}-Sync Fehler: {e}")
        return

    if arg == "all":
        await update.message.reply_text("🔄 Vollständiger Sync gestartet...")
        typing = TypingLoop(update.message.chat)
        typing.start()
        try:
            results = []
            # Drive (direkt, 0 Tokens)
            drive_result = knowledge_sync.sync_drive_all()
            results.append(f"📁 Drive: {drive_result.get('documents', 0)} Docs, {drive_result.get('pdfs', 0)} PDFs")

            # Gmail, Calendar, Contacts (aus Cache-Dateien)
            for source in ("gmail", "calendar", "contacts"):
                try:
                    count = knowledge_sync.load_and_store(source)
                    results.append(f"{'📧' if source == 'gmail' else '📅' if source == 'calendar' else '👥'} {source.title()}: {count} Einträge")
                except FileNotFoundError:
                    results.append(f"⚠️ {source.title()}: keine Daten (noch nicht synchronisiert)")
                except Exception as e:
                    results.append(f"❌ {source.title()}: {e}")

            await update.message.reply_text("✅ Sync abgeschlossen:\n" + "\n".join(results))
        except Exception as e:
            log.exception("/sync all Fehler: %s", e)
            await update.message.reply_text(f"❌ Sync Fehler: {e}")
        finally:
            typing.stop()
        return

    # Unbekanntes Argument
    await update.message.reply_text(
        "🔄 Knowledge-Sync Befehle:\n"
        "/sync status – Sync-Status anzeigen\n"
        "/sync drive – Google Drive indexieren\n"
        "/sync gmail – Gmail-Cache laden\n"
        "/sync calendar – Kalender laden\n"
        "/sync contacts – Kontakte laden\n"
        "/sync all – Alles synchronisieren"
    )


async def cmd_scheduler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scheduler-Status und Steuerung: /scheduler [status|pause|resume|run <task_id>]"""
    if not is_authorized(update):
        return
    if not tfa.verified:
        await update.message.reply_text("Bot ist gesperrt. Bitte 2FA-Code eingeben:")
        return

    arg = context.args[0] if context.args else "status"

    if arg == "status":
        await update.message.reply_text(scheduler.get_status())

    elif arg == "pause":
        scheduler.stop()
        log.info("[/scheduler] Scheduler pausiert von %s", update.effective_user.username)
        await update.message.reply_text("⏸️ Scheduler pausiert.")

    elif arg == "resume":
        scheduler.start()
        log.info("[/scheduler] Scheduler fortgesetzt von %s", update.effective_user.username)
        await update.message.reply_text("▶️ Scheduler fortgesetzt.")

    elif arg == "run":
        # /scheduler run <task_id> → Task sofort ausführen
        task_id = context.args[1] if len(context.args) > 1 else None
        if not task_id:
            await update.message.reply_text("Verwendung: /scheduler run <task_id>")
            return
        scheduler.run_now(task_id)
        log.info("[/scheduler] Task '%s' manuell getriggert von %s", task_id, update.effective_user.username)
        await update.message.reply_text(f"🔄 Task '{task_id}' wird beim nächsten Zyklus ausgeführt (~60s).")

    else:
        await update.message.reply_text(
            "⏰ Scheduler-Befehle:\n"
            "/scheduler status - Alle Tasks anzeigen\n"
            "/scheduler pause - Scheduler pausieren\n"
            "/scheduler resume - Scheduler fortsetzen\n"
            "/scheduler run <task_id> - Task sofort ausführen"
        )


async def error_handler(update, context):
    """Fehlerbehandlung für Telegram-Fehler (besonders Netzwerkfehler)."""
    from telegram.error import NetworkError, TimedOut
    if isinstance(context.error, (NetworkError, TimedOut)):
        # Netzwerk-Timeouts sind normal bei Long-Polling – nur als WARNING loggen
        log.warning("Telegram Netzwerk: %s", context.error)
    else:
        log.error("Telegram Fehler: %s", context.error, exc_info=context.error)


async def post_init(application: Application):
    """Bot-Kommandos registrieren, 2FA starten und Scheduler initialisieren."""
    await application.bot.set_my_commands([
        BotCommand("start", "Bot starten / Hilfe"),
        BotCommand("agent", "Agent wechseln"),
        BotCommand("agents", "Agenten auflisten"),
        BotCommand("claude", "Nachricht an Claude Code"),
        BotCommand("bash", "Shell-Befehl ausführen"),
        BotCommand("vorlesen", "Text als Audio vorlesen"),
        BotCommand("newsession", "Frische Konversation starten"),
        BotCommand("queue", "Warteschlange anzeigen"),
        BotCommand("cpu", "Claude CPU & Memory Auslastung"),
        BotCommand("sync", "Knowledge Base synchronisieren"),
        BotCommand("scheduler", "Scheduler-Status & Steuerung"),
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

    # --- Scheduler starten ---
    global scheduler

    async def scheduler_send(text: str):
        """Sendet Scheduler-Ergebnisse an den Telegram-Chat."""
        for i in range(0, len(text), 4000):
            chunk = text[i: i + 4000]
            await application.bot.send_message(
                chat_id=ALLOWED_CHAT_ID, text=chunk
            )

    scheduler = TaskScheduler(
        build_claude_cmd_fn=build_claude_cmd,
        send_message_fn=scheduler_send,
    )
    scheduler.start()
    log.info("⏰ Scheduler initialisiert und gestartet")


def main():
    if not BOT_TOKEN:
        print("FEHLER: TELEGRAM_BOT_TOKEN nicht in .env gesetzt!")
        return

    from telegram.ext import Defaults
    from telegram.request import HTTPXRequest
    # Robustere HTTP-Verbindung: höhere Timeouts, Connection-Pooling
    request = HTTPXRequest(
        connect_timeout=20.0,
        read_timeout=45.0,
        write_timeout=30.0,
        pool_timeout=10.0,
        connection_pool_size=8,
    )
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)
        .post_init(post_init)
        .build()
    )

    # Error-Handler für Netzwerk- und andere Fehler
    app.add_error_handler(error_handler)

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
    app.add_handler(CommandHandler("newsession", cmd_newsession))
    app.add_handler(CommandHandler("queue", cmd_queue))
    app.add_handler(CommandHandler("cpu", cmd_cpu))
    app.add_handler(CommandHandler("scheduler", cmd_scheduler))
    app.add_handler(CommandHandler("sync", cmd_sync))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    agent = get_active_agent()
    log.info("=== Bot gestartet === PID=%d, Agent=%s, Chat-ID=%d, Working Dir=%s", os.getpid(), agent["id"], ALLOWED_CHAT_ID, WORKING_DIR)
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        read_timeout=30,
        connect_timeout=15,
        pool_timeout=10,
    )


if __name__ == "__main__":
    main()
