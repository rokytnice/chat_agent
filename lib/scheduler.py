#!/usr/bin/env python3
"""
Zyklischer Task-Scheduler für wiederkehrende Agenten-Aufgaben.

Liest die `scheduled_tasks` aus agents.json und führt fällige Tasks
automatisch mit dem jeweiligen Agenten aus. Ergebnisse werden via
Telegram an den User gesendet.

Läuft als asyncio-Task im Bot-Event-Loop.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("telegram_bridge.scheduler")

WORKING_DIR = Path(__file__).parent.parent
AGENTS_FILE = WORKING_DIR / "config" / "agents.json"
STATE_FILE = WORKING_DIR / "data" / "scheduler_state.json"
CURRENT_JOBS_FILE = WORKING_DIR / "data" / "current_jobs.json"

# Prüf-Intervall in Sekunden (wie oft der Scheduler nach fälligen Tasks schaut)
CHECK_INTERVAL = 60


class TaskScheduler:
    """Zyklischer Scheduler der Agent-Tasks nach Cron-Zeitplan ausführt."""

    def __init__(
        self,
        build_claude_cmd_fn: Callable,
        send_message_fn: Callable,
    ):
        """
        Args:
            build_claude_cmd_fn: Referenz zu build_claude_cmd() aus bot.py
            send_message_fn:     Async callable(text) um Telegram-Nachricht zu senden
        """
        self.build_claude_cmd = build_claude_cmd_fn
        self.send_message = send_message_fn
        self._task: Optional[asyncio.Task] = None
        self._state: dict = {}
        self._running_tasks: dict = {}  # task_id -> {agent, task_config, started}

    # ------------------------------------------------------------------ #
    #  Config & State I/O                                                  #
    # ------------------------------------------------------------------ #

    def _load_agents(self) -> dict:
        """Lade agents.json (bei jedem Zyklus neu → Hot-Reload)."""
        if not AGENTS_FILE.exists():
            return {}
        with open(AGENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_state(self) -> dict:
        """Lade Ausführungs-State aus data/scheduler_state.json."""
        if not STATE_FILE.exists():
            return {}
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            log.warning("scheduler_state.json beschädigt, starte neu")
            return {}

    def _save_state(self):
        """Speichere State persistent."""
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, default=str)
        # Update dashboard (non-blocking, best-effort)
        try:
            from lib.dashboard_publisher import publish_dashboard
            publish_dashboard()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  Cron-Parser                                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _cron_field_matches(field: str, value: int) -> bool:
        """Prüft ob ein einzelnes Cron-Feld zum aktuellen Wert passt.

        Unterstützt: * (jeder), Zahl, */N (Step), Komma-Listen, Bereiche.
        Beispiele: "*", "5", "*/15", "1,15", "9-17"
        """
        if field == "*":
            return True

        # Step: */N
        if field.startswith("*/"):
            step = int(field[2:])
            return value % step == 0

        # Komma-Liste: 1,5,10
        if "," in field:
            return value in [int(v) for v in field.split(",")]

        # Bereich: 9-17
        if "-" in field:
            low, high = field.split("-", 1)
            return int(low) <= value <= int(high)

        # Einzelwert
        if field.isdigit():
            return int(field) == value

        return False

    def _is_cron_due(self, expression: str, last_run: Optional[datetime]) -> bool:
        """Prüft ob eine Cron-Expression jetzt fällig ist.

        Format: minute hour day month weekday
        Beispiele:
          "0 7 * * *"    → täglich um 7:00
          "*/30 * * * *" → alle 30 Minuten
          "0 9 * * 1"    → Montag 9:00
          "0 */6 * * *"  → alle 6 Stunden zur vollen Stunde
        """
        parts = expression.strip().split()
        if len(parts) != 5:
            log.warning("Ungültige Cron-Expression: '%s'", expression)
            return False

        now = datetime.now()
        c_min, c_hour, c_day, c_month, c_weekday = parts

        # Wochentag: Cron 0=Sonntag, Python 0=Montag → umrechnen
        py_weekday = now.weekday()  # 0=Mo, 6=So
        cron_weekday = (py_weekday + 1) % 7  # 0=So, 1=Mo, ..., 6=Sa

        time_matches = (
            self._cron_field_matches(c_min, now.minute)
            and self._cron_field_matches(c_hour, now.hour)
            and self._cron_field_matches(c_day, now.day)
            and self._cron_field_matches(c_month, now.month)
            and self._cron_field_matches(c_weekday, cron_weekday)
        )

        if not time_matches:
            return False

        # Schutz: Nicht erneut ausführen wenn bereits in dieser Minute gelaufen
        if last_run:
            elapsed = (now - last_run).total_seconds()
            if elapsed < 60:
                return False

        return True

    # ------------------------------------------------------------------ #
    #  Task-Ausführung                                                     #
    # ------------------------------------------------------------------ #

    async def _execute_task(self, task_id: str, task_config: dict, agent: dict):
        """Führt einen einzelnen Task aus und sendet das Ergebnis via Telegram.

        Unterstützt zwei Task-Typen:
          - "claude" (default): Führt Prompt via Claude aus
          - "bash": Führt Shell-Befehl direkt aus (kein Claude)

        Bei transienten Fehlern (DNS, Netzwerk) wird automatisch 1x wiederholt.
        """
        max_retries = task_config.get("retries", 1)
        await self._execute_task_attempt(task_id, task_config, agent, max_retries)

    async def _execute_task_attempt(
        self, task_id: str, task_config: dict, agent: dict,
        retries_left: int,
    ):
        """Einzelner Ausführungsversuch mit optionalem Retry."""
        task_type = task_config.get("type", "claude")
        prompt = task_config.get("prompt", "")
        timeout = task_config.get("timeout_seconds", 300)
        description = task_config.get("description", task_id)
        silent = task_config.get("silent", False)
        agent_name = agent.get("name", agent.get("id", "?"))
        agent_emoji = agent.get("emoji", "🤖")

        log.info(
            "⏰ Scheduler: Starte Task '%s' (type=%s) mit Agent '%s %s'",
            task_id, task_type, agent_emoji, agent_name,
        )

        start = datetime.now()
        self._running_tasks[task_id] = {
            "agent": agent, "task_config": task_config, "started": start
        }
        self._write_current_jobs()

        # Intervall für Zwischenstand-Meldungen (Sekunden)
        progress_interval = task_config.get("progress_interval", 120)

        try:
            if task_type == "bash":
                # ---- Bash-Task: Direkte Shell-Ausführung, KEIN Claude ----
                bash_cmd = task_config.get("command", prompt)
                proc = await asyncio.create_subprocess_shell(
                    bash_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(WORKING_DIR),
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                elapsed = (datetime.now() - start).total_seconds()
                output = stdout.decode().strip()
                if stderr.decode().strip():
                    output += f"\n--- STDERR ---\n{stderr.decode().strip()}"
            else:
                # ---- Claude-Task: Ausführung mit Streaming-Fortschritt ----
                cmd = self.build_claude_cmd(prompt, agent, "scheduler")
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(WORKING_DIR),
                )

                # Streaming: stdout zeilenweise lesen + Zwischenstände senden
                output_lines = []
                stream_done = asyncio.Event()

                async def _read_stream():
                    """Liest stdout zeilenweise und sammelt Output."""
                    while True:
                        line = await proc.stdout.readline()
                        if not line:
                            break
                        decoded = line.decode().rstrip()
                        output_lines.append(decoded)
                    stream_done.set()

                async def _progress_ticker():
                    """Sendet unabhängig vom Output alle progress_interval Sekunden ein Update."""
                    progress_count = 0
                    while not stream_done.is_set():
                        try:
                            await asyncio.wait_for(
                                stream_done.wait(),
                                timeout=progress_interval,
                            )
                            # Stream ist fertig → kein Update mehr nötig
                            break
                        except asyncio.TimeoutError:
                            # progress_interval ist abgelaufen, Stream läuft noch
                            if silent:
                                continue
                            progress_count += 1
                            elapsed_so_far = (datetime.now() - start).total_seconds()
                            # Letzte 5 Zeilen als Vorschau
                            preview = "\n".join(output_lines[-5:]) if output_lines else "(noch keine Ausgabe)"
                            if len(preview) > 500:
                                preview = preview[-500:]
                            await self.send_message(
                                f"⏳ {agent_emoji} {description}\n"
                                f"Läuft seit {elapsed_so_far:.0f}s...\n"
                                f"{'─' * 25}\n"
                                f"{preview}"
                            )

                try:
                    # Beide Tasks parallel: Lesen + Progress-Timer
                    reader_task = asyncio.create_task(_read_stream())
                    ticker_task = asyncio.create_task(_progress_ticker())
                    # Timeout gilt für den gesamten Prozess
                    await asyncio.wait_for(reader_task, timeout=timeout)
                    ticker_task.cancel()
                    await proc.wait()  # Warte auf Prozess-Ende
                except asyncio.TimeoutError:
                    ticker_task.cancel()
                    proc.kill()
                    raise

                stderr_data = await proc.stderr.read()
                elapsed = (datetime.now() - start).total_seconds()
                output = "\n".join(output_lines).strip()
                if stderr_data.decode().strip():
                    output += f"\n\n--- STDERR ---\n{stderr_data.decode().strip()}"

            # State aktualisieren
            self._state.setdefault(task_id, {"run_count": 0})
            self._state[task_id].update({
                "last_run": datetime.now().isoformat(),
                "last_status": "success",
                "last_duration_seconds": round(elapsed, 1),
                "last_error": None,
                "last_output": output[:2000] if output else "",
            })
            self._state[task_id]["run_count"] = (
                self._state[task_id].get("run_count", 0) + 1
            )

            # Ergebnis an Telegram senden
            if task_type == "bash":
                header = (
                    f"⚙️ Scheduler: {description}\n"
                    f"Typ: Bash-Befehl\n"
                    f"Dauer: {elapsed:.1f}s\n"
                    f"{'─' * 30}\n\n"
                )
            else:
                header = (
                    f"⏰ Scheduler: {description}\n"
                    f"Agent: {agent_emoji} {agent_name}\n"
                    f"Dauer: {elapsed:.1f}s\n"
                    f"{'─' * 30}\n\n"
                )
            if not silent:
                await self.send_message(header + output)

            log.info(
                "✅ Scheduler: Task '%s' erfolgreich in %.1fs (%d Zeichen)%s",
                task_id, elapsed, len(output),
                " (silent)" if silent else "",
            )

        except asyncio.TimeoutError:
            elapsed = (datetime.now() - start).total_seconds()
            log.error("⏱️ Scheduler: Task '%s' Timeout nach %ds", task_id, timeout)
            self._state.setdefault(task_id, {}).update({
                "last_run": datetime.now().isoformat(),
                "last_status": "timeout",
                "last_duration_seconds": round(elapsed, 1),
                "last_error": f"Timeout nach {timeout}s",
            })
            # Timeout nur loggen, NICHT im Chat melden (stört den User)
            log.warning(
                "⏰ Scheduler: Task '%s' Timeout nach %ds – keine Chat-Meldung",
                task_id, timeout,
            )

        except Exception as e:
            elapsed = (datetime.now() - start).total_seconds()
            error_str = str(e)

            # Transiente Fehler erkennen (DNS, Netzwerk) → automatisch Retry
            transient_errors = [
                "name resolution",
                "ConnectError",
                "ConnectionReset",
                "ConnectionRefused",
                "Temporary failure",
                "Network is unreachable",
            ]
            is_transient = any(t in error_str for t in transient_errors)

            if is_transient and retries_left > 0:
                log.warning(
                    "🔄 Scheduler: Transienter Fehler bei '%s': %s – Retry in 30s (%d verbleibend)",
                    task_id, error_str[:80], retries_left,
                )
                await asyncio.sleep(30)
                await self._execute_task_attempt(
                    task_id, task_config, agent, retries_left - 1
                )
                return

            log.exception("❌ Scheduler: Fehler bei Task '%s': %s", task_id, e)
            self._state.setdefault(task_id, {}).update({
                "last_run": datetime.now().isoformat(),
                "last_status": "error",
                "last_duration_seconds": round(elapsed, 1),
                "last_error": error_str,
            })

        finally:
            self._running_tasks.pop(task_id, None)
            self._write_current_jobs()
            self._save_state()
            self._persist_scheduler_request(task_id, task_config, agent, start)

    def _write_current_jobs(self):
        """Merge scheduler running tasks into data/current_jobs.json (additive with bot jobs)."""
        try:
            # Read existing data (from bot PipeQueue) - new format with running/queued
            data = {"running": [], "queued": []}
            if CURRENT_JOBS_FILE.exists():
                try:
                    raw = json.loads(CURRENT_JOBS_FILE.read_text())
                    if isinstance(raw, dict):
                        data = raw
                    elif isinstance(raw, list):
                        data = {"running": raw, "queued": []}
                except (json.JSONDecodeError, ValueError):
                    pass
            # Remove old scheduler entries from running, keep bot entries
            data["running"] = [j for j in data.get("running", []) if j.get("source") != "scheduler"]
            # Add current scheduler tasks to running
            for task_id, info in self._running_tasks.items():
                agent = info["agent"]
                started = info["started"]
                elapsed = round((datetime.now() - started).total_seconds(), 1)
                data["running"].append({
                    "agent_id": agent.get("id", "?"),
                    "agent_name": agent.get("name", "?"),
                    "agent_emoji": agent.get("emoji", "🤖"),
                    "title": info["task_config"].get("description", task_id)[:80],
                    "job_type": info["task_config"].get("type", "claude"),
                    "started": started.isoformat(),
                    "elapsed_seconds": elapsed,
                    "source": "scheduler",
                })
            CURRENT_JOBS_FILE.write_text(json.dumps(data, ensure_ascii=False, default=str))
        except Exception as e:
            log.warning("Write current_jobs failed: %s", e)

    def _persist_scheduler_request(self, task_id, task_config, agent, start):
        """Append scheduler task execution to data/request_log.json."""
        try:
            log_file = Path(__file__).parent.parent / "data" / "request_log.json"
            entries = []
            if log_file.exists():
                try:
                    entries = json.loads(log_file.read_text())
                except (json.JSONDecodeError, ValueError):
                    entries = []

            task_state = self._state.get(task_id, {})
            entry = {
                "id": None,
                "timestamp": task_state.get("last_run", datetime.now().isoformat()),
                "agent_id": agent.get("id", "?"),
                "agent_name": agent.get("name", "?"),
                "agent_emoji": agent.get("emoji", ""),
                "job_type": task_config.get("type", "claude"),
                "title": task_config.get("description", task_id)[:80],
                "prompt": task_config.get("prompt", "")[:500],
                "output": task_state.get("last_output", "")[:2000],
                "status": task_state.get("last_status", "error"),
                "duration_seconds": task_state.get("last_duration_seconds"),
                "source": "scheduler",
            }
            entries.append(entry)
            entries = entries[-200:]
            log_file.write_text(json.dumps(entries, indent=2, ensure_ascii=False, default=str))
        except Exception as e:
            log.warning("Scheduler request-log persist failed: %s", e)

    # ------------------------------------------------------------------ #
    #  Scheduler-Zyklus                                                    #
    # ------------------------------------------------------------------ #

    async def _check_reminders(self):
        """Prüfe fällige Erinnerungen und sende sie via Telegram."""
        try:
            from lib.reminders import ReminderManager
            mgr = ReminderManager()
            due = mgr.get_due_reminders()
            for r in due:
                created = r.get("created_at", "")[:10]
                text = (
                    f"🔔 Erinnerung!\n\n"
                    f"{r['text']}\n\n"
                    f"(Erstellt: {created})"
                )
                await self.send_message(text)
                mgr.mark_sent(r["id"])
                log.info("🔔 Reminder gesendet: %s", r["id"])
            # Alte Erinnerungen aufräumen
            mgr.cleanup_old(days=30)
        except Exception as e:
            log.warning("Reminder-Check fehlgeschlagen: %s", e)

    async def _watchdog(self):
        """Schnelle Systemprüfung bei jedem Zyklus (alle 60s).

        Erkennt und behebt:
        - Hängende Tasks (laufen >2x Timeout)
        - Chrome/CDP nicht erreichbar → Auto-Restart
        - Playwright MCP Server tot → Auto-Restart
        """
        issues = []

        # 1. Hängende Tasks prüfen
        now = datetime.now()
        for task_id, info in list(self._running_tasks.items()):
            started = info["started"]
            elapsed = (now - started).total_seconds()
            timeout = info["task_config"].get("timeout_seconds", 300)
            # Task läuft >2x Timeout → wahrscheinlich gehangen
            if elapsed > timeout * 2:
                issues.append(f"⚠️ Task '{task_id}' hängt seit {int(elapsed)}s (Timeout: {timeout}s)")
                log.error("🐕 Watchdog: Task '%s' hängt seit %ds – entferne aus Tracking",
                          task_id, int(elapsed))
                self._running_tasks.pop(task_id, None)
                self._state.setdefault(task_id, {}).update({
                    "last_run": now.isoformat(),
                    "last_status": "watchdog_killed",
                    "last_error": f"Watchdog: Task hing nach {int(elapsed)}s",
                })
                self._write_current_jobs()

        # 2. Chrome/CDP Health-Check (nur wenn chrome_manager vorhanden)
        try:
            from lib.chrome_manager import is_cdp_alive, restart as chrome_restart
            if not is_cdp_alive():
                log.warning("🐕 Watchdog: Chrome CDP nicht erreichbar – Neustart")
                chrome_restart()
                if is_cdp_alive():
                    issues.append("🔄 Chrome war tot → automatisch neugestartet ✅")
                    log.info("🐕 Watchdog: Chrome erfolgreich neugestartet")
                else:
                    issues.append("❌ Chrome Neustart fehlgeschlagen!")
                    log.error("🐕 Watchdog: Chrome Neustart fehlgeschlagen")
        except ImportError:
            pass
        except Exception as e:
            log.debug("Watchdog Chrome-Check: %s", e)

        # 3. Playwright MCP Server Check
        try:
            import subprocess
            result = subprocess.run(
                ["pgrep", "-f", "playwright.*mcp"],
                capture_output=True, timeout=5,
            )
            if result.returncode != 0:
                # Playwright MCP läuft nicht – versuche Neustart
                log.warning("🐕 Watchdog: Playwright MCP Server nicht gefunden – Neustart")
                mcp_cmd = "npx @anthropic-ai/mcp-playwright --port 3002"
                subprocess.Popen(
                    mcp_cmd, shell=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                await asyncio.sleep(3)
                result2 = subprocess.run(
                    ["pgrep", "-f", "playwright.*mcp"],
                    capture_output=True, timeout=5,
                )
                if result2.returncode == 0:
                    issues.append("🔄 Playwright MCP war tot → automatisch neugestartet ✅")
                    log.info("🐕 Watchdog: Playwright MCP erfolgreich neugestartet")
                else:
                    issues.append("❌ Playwright MCP Neustart fehlgeschlagen!")
                    log.error("🐕 Watchdog: Playwright MCP Neustart fehlgeschlagen")
        except Exception as e:
            log.debug("Watchdog Playwright-Check: %s", e)

        # Bei Problemen → User informieren
        if issues:
            msg = "🐕 **Watchdog-Report**\n\n" + "\n".join(issues)
            try:
                await self.send_message(msg)
            except Exception:
                pass

    async def _run_cycle(self):
        """Ein Scheduler-Zyklus: Watchdog, Erinnerungen, dann Agenten-Tasks."""
        # Watchdog: Schnelle Systemprüfung (< 2s)
        await self._watchdog()

        # Erinnerungen prüfen (kostet 0 Tokens)
        await self._check_reminders()

        config = self._load_agents()
        agents = config.get("agents", {})

        for agent_id, agent_cfg in agents.items():
            tasks = agent_cfg.get("scheduled_tasks", [])
            if not tasks:
                continue

            # Agent-Dict für build_claude_cmd vorbereiten
            agent = dict(agent_cfg)
            agent["id"] = agent_id

            for task in tasks:
                if not task.get("enabled", False):
                    continue

                task_id = task.get("id", f"{agent_id}_unnamed")
                cron_expr = task.get("cron", "")
                if not cron_expr:
                    continue

                # Letzten Lauf ermitteln
                state = self._state.get(task_id, {})
                last_run_str = state.get("last_run")
                last_run = (
                    datetime.fromisoformat(last_run_str) if last_run_str else None
                )

                if self._is_cron_due(cron_expr, last_run):
                    # Tasks sequentiell ausführen (Ressourcen schonen)
                    await self._execute_task(task_id, task, agent)

    async def run_forever(self):
        """Endlos-Schleife: Zyklisch prüfen und ausführen."""
        log.info("⏰ Scheduler gestartet (Prüf-Intervall: %ds)", CHECK_INTERVAL)
        self._state = self._load_state()

        while True:
            try:
                await self._run_cycle()
            except Exception as e:
                log.exception("Scheduler-Zyklus Fehler: %s", e)

            await asyncio.sleep(CHECK_INTERVAL)

    # ------------------------------------------------------------------ #
    #  Start / Stop / Status                                               #
    # ------------------------------------------------------------------ #

    def start(self):
        """Starte Scheduler als asyncio-Task."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run_forever())
            log.info("⏰ Scheduler-Task erstellt")

    def stop(self):
        """Stoppe Scheduler."""
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None
            log.info("⏰ Scheduler gestoppt")

    def get_status(self) -> str:
        """Formatierter Status für /scheduler Befehl."""
        config = self._load_agents()
        agents = config.get("agents", {})
        self._state = self._load_state()

        all_tasks = []
        for agent_id, agent_cfg in agents.items():
            emoji = agent_cfg.get("emoji", "🤖")
            for task in agent_cfg.get("scheduled_tasks", []):
                tid = task.get("id", "?")
                enabled = task.get("enabled", False)
                cron = task.get("cron", "?")
                desc = task.get("description", tid)

                state = self._state.get(tid, {})
                last_run = state.get("last_run", "nie")
                if last_run != "nie":
                    # Nur Zeit anzeigen wenn heute, sonst Datum+Zeit
                    try:
                        dt = datetime.fromisoformat(last_run)
                        if dt.date() == datetime.now().date():
                            last_run = dt.strftime("%H:%M")
                        else:
                            last_run = dt.strftime("%d.%m. %H:%M")
                    except ValueError:
                        pass

                last_status = state.get("last_status", "-")
                run_count = state.get("run_count", 0)

                status_icon = "🟢" if enabled else "⚪"
                result_icon = {"success": "✅", "timeout": "⏱️", "error": "❌"}.get(
                    last_status, "➖"
                )

                all_tasks.append(
                    f"{status_icon} {emoji} {desc}\n"
                    f"   Cron: {cron} | Runs: {run_count}\n"
                    f"   Letzter Lauf: {last_run} {result_icon}"
                )

        if not all_tasks:
            return "⏰ Scheduler: Keine Tasks konfiguriert.\nFüge scheduled_tasks in config/agents.json hinzu."

        running = "läuft" if (self._task and not self._task.done()) else "gestoppt"
        header = f"⏰ Scheduler ({running}) — {len(all_tasks)} Tasks:\n{'─' * 35}\n"
        return header + "\n\n".join(all_tasks)

    def run_now(self, task_id: str) -> bool:
        """Markiere einen Task als 'sofort fällig' (löscht last_run)."""
        if task_id in self._state:
            self._state[task_id].pop("last_run", None)
            self._save_state()
            return True
        # Auch wenn noch kein State existiert → wird beim nächsten Zyklus sofort ausgeführt
        return True
