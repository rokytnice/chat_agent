#!/usr/bin/env python3
"""Persistenter Claude-Session-Manager mit Datei-basiertem Response-Kanal.

Architektur:
- EINE fixe Session pro Agent (wird NIE automatisch rotiert)
- Jede Anfrage: `claude --print --resume <session_id>` mit Output in eine Datei
- Bot liest die Antwort aus der Datei
- Sequentielle Verarbeitung über asyncio.Lock pro Agent
- Session wird nur bei explizitem /newsession zurückgesetzt

Vorteile gegenüber dem alten System:
- Kontext geht nie verloren (keine automatische Session-Rotation)
- Saubere Datei-basierte Antwort-Übergabe
- Robuste Fehlerbehandlung und Recovery
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path

log = logging.getLogger("claude_pipe")

# Pfade
WORKING_DIR = Path(__file__).parent.parent
DATA_DIR = WORKING_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
SESSIONS_FILE = DATA_DIR / "sessions.json"
RESPONSE_DIR = DATA_DIR / "responses"
RESPONSE_DIR.mkdir(exist_ok=True)
MCP_CONFIG_FILE = WORKING_DIR / "config" / "mcp_config.json"

# Timeouts
CLAUDE_TIMEOUT = 600  # 10 Minuten max pro Aufruf


class ClaudePipe:
    """Persistenter Claude-Session-Manager.

    Verwaltet eine fixe Session pro Agent und stellt sicher, dass:
    - Kontext über alle Nachrichten erhalten bleibt
    - Antworten sauber über Dateien übergeben werden
    - Nie mehr als ein Claude-Prozess pro Agent gleichzeitig läuft
    """

    def __init__(self, rag=None):
        self._locks: dict[str, asyncio.Lock] = {}
        self._sessions: dict[str, str] = self._load_sessions()
        self._stats: dict[str, int] = {}
        self._current: dict[str, dict] = {}
        self._rag = rag
        log.info("ClaudePipe initialisiert mit %d Sessions", len(self._sessions))

    # --- Session-Verwaltung ---

    def _load_sessions(self) -> dict:
        """Lädt Session-IDs aus data/sessions.json."""
        if not SESSIONS_FILE.exists():
            return {}
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            log.error("Fehler beim Laden der Sessions: %s", e)
            return {}

    def _save_sessions(self):
        """Speichert Session-IDs in data/sessions.json."""
        try:
            with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._sessions, f, indent=2)
        except IOError as e:
            log.error("Fehler beim Speichern der Sessions: %s", e)

    def get_session_id(self, agent_id: str) -> tuple[str, bool]:
        """Gibt (session_id, is_new) zurück. Erstellt neue Session falls nötig."""
        if agent_id in self._sessions:
            return self._sessions[agent_id], False

        new_id = str(uuid.uuid4())
        self._sessions[agent_id] = new_id
        self._save_sessions()
        log.info("Neue Session für Agent '%s': %s", agent_id, new_id)
        return new_id, True

    def reset_session(self, agent_id: str) -> bool:
        """Setzt Session zurück. Gibt True zurück wenn eine Session existierte."""
        if agent_id in self._sessions:
            old_id = self._sessions.pop(agent_id)
            self._save_sessions()
            log.info("Session für Agent '%s' zurückgesetzt (war: %s)", agent_id, old_id)
            return True
        return False

    def get_session_info(self, agent_id: str) -> dict:
        """Gibt Info über die aktuelle Session zurück."""
        session_id = self._sessions.get(agent_id)
        if not session_id:
            return {"agent_id": agent_id, "status": "keine Session"}

        transcript = self._transcript_path(session_id)
        size_mb = 0
        if transcript.exists():
            size_mb = transcript.stat().st_size / (1024 * 1024)

        return {
            "agent_id": agent_id,
            "session_id": session_id[:8] + "...",
            "transcript_mb": round(size_mb, 1),
            "requests": self._stats.get(agent_id, 0),
            "active": agent_id in self._current,
        }

    def _transcript_path(self, session_id: str) -> Path:
        """Pfad zur Claude-Session-Transcript-Datei."""
        project_dir = Path.home() / ".claude" / "projects" / "-home-aroc-projects-chat-agent"
        return project_dir / f"{session_id}.jsonl"

    def _get_lock(self, agent_id: str) -> asyncio.Lock:
        """Gibt den Lock für einen Agent zurück (erstellt ihn falls nötig)."""
        if agent_id not in self._locks:
            self._locks[agent_id] = asyncio.Lock()
        return self._locks[agent_id]

    # --- Claude-Befehl bauen ---

    def build_cmd(self, prompt: str, agent: dict, chat_id: str = None) -> list:
        """Baut den Claude-CLI-Befehl."""
        agent_id = agent.get("id", "default")
        session_id, is_new = self.get_session_id(agent_id)

        if is_new:
            cmd = ["claude", "--print", "--session-id", session_id,
                   "--dangerously-skip-permissions"]
        else:
            cmd = ["claude", "--print", "--resume", session_id,
                   "--dangerously-skip-permissions"]

        # MCP-Konfiguration
        if MCP_CONFIG_FILE.exists():
            cmd += ["--mcp-config", str(MCP_CONFIG_FILE)]

        # System-Prompt mit RAG-Anreicherung
        system_prompt = agent.get("system_prompt", "")
        if system_prompt and self._rag:
            try:
                system_prompt = self._rag.enrich_user_message(
                    user_query=prompt,
                    system_prompt=system_prompt,
                    chat_id=chat_id or "default"
                )
            except Exception as e:
                log.warning("RAG-Anreicherung fehlgeschlagen: %s", e)

        if system_prompt:
            cmd += ["--system-prompt", system_prompt]

        model = agent.get("model")
        if model:
            cmd += ["--model", model]

        cmd.append(prompt)
        return cmd

    # --- Ausführung ---

    async def execute(self, prompt: str, agent: dict, chat_id: str = None) -> dict:
        """Führt eine Claude-Anfrage aus und gibt das Ergebnis zurück.

        Returns:
            dict mit keys: output, elapsed, error, session_id
        """
        agent_id = agent.get("id", "default")
        lock = self._get_lock(agent_id)

        async with lock:
            return await self._run_claude(prompt, agent, chat_id)

    async def _run_claude(self, prompt: str, agent: dict, chat_id: str = None) -> dict:
        """Interne Ausführung: spawnt Claude-Prozess, schreibt Output in Datei."""
        agent_id = agent.get("id", "default")
        session_id, _ = self.get_session_id(agent_id)

        # Response-Datei vorbereiten
        response_file = RESPONSE_DIR / f"{agent_id}_{session_id[:8]}.txt"
        result = {
            "output": "",
            "elapsed": 0,
            "error": None,
            "session_id": session_id,
        }

        self._current[agent_id] = {
            "prompt": prompt[:100],
            "started": datetime.now(),
        }

        start = datetime.now()
        try:
            cmd = self.build_cmd(prompt, agent, chat_id)

            # Umgebung ohne CLAUDECODE (verhindert "nested session" Fehler)
            env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(WORKING_DIR),
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=CLAUDE_TIMEOUT
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                elapsed = (datetime.now() - start).total_seconds()
                result["elapsed"] = elapsed
                result["error"] = f"Timeout nach {int(elapsed)}s"
                log.error("⏱️ Claude [%s] TIMEOUT nach %.0fs", agent_id, elapsed)
                return result

            elapsed = (datetime.now() - start).total_seconds()
            result["elapsed"] = elapsed

            output = stdout.decode().strip()
            stderr_text = stderr.decode().strip()

            if proc.returncode != 0 and not output:
                result["error"] = f"Exit Code {proc.returncode}: {stderr_text[:500]}"
                log.error("Claude [%s] Fehler (exit=%d): %s",
                          agent_id, proc.returncode, stderr_text[:200])
                return result

            if stderr_text:
                log.debug("Claude [%s] stderr: %s", agent_id, stderr_text[:200])

            result["output"] = output

            # Response in Datei schreiben (für Nachvollziehbarkeit)
            try:
                with open(response_file, "w", encoding="utf-8") as f:
                    f.write(f"# Agent: {agent_id} | Session: {session_id[:8]}\n")
                    f.write(f"# Prompt: {prompt[:200]}\n")
                    f.write(f"# Zeit: {datetime.now().isoformat()} | Dauer: {elapsed:.1f}s\n")
                    f.write(f"# ---\n")
                    f.write(output)
            except IOError as e:
                log.warning("Response-Datei schreiben fehlgeschlagen: %s", e)

            # RAG-Speicherung
            if self._rag:
                try:
                    self._rag.store_interaction(
                        user_message=prompt,
                        assistant_response=output,
                        chat_id=chat_id or "default",
                        model=agent.get("model", "unknown")
                    )
                except Exception as e:
                    log.warning("RAG-Speichern fehlgeschlagen: %s", e)

            self._stats[agent_id] = self._stats.get(agent_id, 0) + 1
            log.info("Claude [%s] fertig in %.1fs (%d Zeichen, Session %s)",
                     agent_id, elapsed, len(output), session_id[:8])

            if elapsed > 120:
                log.warning("⚠️ Claude [%s] langsam: %.1fs", agent_id, elapsed)

            return result

        except FileNotFoundError:
            result["error"] = "'claude' CLI nicht gefunden. Ist Claude Code installiert?"
            log.error("claude CLI nicht gefunden")
            return result
        except Exception as e:
            result["error"] = str(e)
            log.exception("Claude [%s] unerwarteter Fehler: %s", agent_id, e)
            return result
        finally:
            self._current.pop(agent_id, None)

    # --- Status ---

    def get_status(self) -> str:
        """Formatierter Status für /status."""
        lines = ["🔗 Claude Pipe Status:"]

        if not self._sessions:
            lines.append("  Keine aktiven Sessions")
            return "\n".join(lines)

        for agent_id, session_id in self._sessions.items():
            info = self.get_session_info(agent_id)
            active = "🔄 aktiv" if info["active"] else "💤 idle"
            lines.append(
                f"  {agent_id}: {active} | "
                f"{info['transcript_mb']}MB | "
                f"{info['requests']} Requests"
            )

        total = sum(self._stats.values())
        active = len(self._current)
        lines.append(f"\n🔄 {active} laufend | ✅ {total} gesamt")
        return "\n".join(lines)

    def is_busy(self, agent_id: str = None) -> bool:
        """Prüft ob ein Agent gerade beschäftigt ist."""
        if agent_id:
            return agent_id in self._current
        return bool(self._current)
