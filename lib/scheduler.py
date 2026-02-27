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
        """Führt einen einzelnen Task aus und sendet das Ergebnis via Telegram."""
        prompt = task_config.get("prompt", "")
        timeout = task_config.get("timeout_seconds", 300)
        description = task_config.get("description", task_id)
        agent_name = agent.get("name", agent.get("id", "?"))
        agent_emoji = agent.get("emoji", "🤖")

        log.info(
            "⏰ Scheduler: Starte Task '%s' mit Agent '%s %s'",
            task_id, agent_emoji, agent_name,
        )

        start = datetime.now()

        try:
            cmd = self.build_claude_cmd(prompt, agent, "scheduler")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
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
                output += f"\n\n--- STDERR ---\n{stderr.decode().strip()}"

            # State aktualisieren
            self._state.setdefault(task_id, {"run_count": 0})
            self._state[task_id].update({
                "last_run": datetime.now().isoformat(),
                "last_status": "success",
                "last_duration_seconds": round(elapsed, 1),
                "last_error": None,
            })
            self._state[task_id]["run_count"] = (
                self._state[task_id].get("run_count", 0) + 1
            )

            # Ergebnis an Telegram senden
            header = (
                f"⏰ Scheduler: {description}\n"
                f"Agent: {agent_emoji} {agent_name}\n"
                f"Dauer: {elapsed:.1f}s\n"
                f"{'─' * 30}\n\n"
            )
            await self.send_message(header + output)

            log.info(
                "✅ Scheduler: Task '%s' erfolgreich in %.1fs (%d Zeichen)",
                task_id, elapsed, len(output),
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
            await self.send_message(
                f"⏰❌ Scheduler: Task '{description}' Timeout nach {timeout}s"
            )

        except Exception as e:
            elapsed = (datetime.now() - start).total_seconds()
            log.exception("❌ Scheduler: Fehler bei Task '%s': %s", task_id, e)
            self._state.setdefault(task_id, {}).update({
                "last_run": datetime.now().isoformat(),
                "last_status": "error",
                "last_duration_seconds": round(elapsed, 1),
                "last_error": str(e),
            })

        finally:
            self._save_state()

    # ------------------------------------------------------------------ #
    #  Scheduler-Zyklus                                                    #
    # ------------------------------------------------------------------ #

    async def _run_cycle(self):
        """Ein Scheduler-Zyklus: Alle Agenten durchgehen, fällige Tasks ausführen."""
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
