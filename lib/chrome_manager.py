#!/usr/bin/env python3
"""
Chrome Manager – Verwaltet den echten Chrome-Browser für den Bot.

Funktionen:
- Start/Stop/Restart des Chrome-Browsers
- Persistentes Profil (überlebt Reboots)
- Health-Checks und Auto-Recovery
- CDP-Endpoint auf Port 9222
- Headed-Modus mit GPU-Support (WebGL etc.)

Usage:
    python -m lib.chrome_manager start    # Chrome starten
    python -m lib.chrome_manager stop     # Chrome stoppen
    python -m lib.chrome_manager restart  # Chrome neustarten
    python -m lib.chrome_manager status   # Status prüfen
    python -m lib.chrome_manager health   # Health-Check mit Auto-Recovery
"""

import json
import logging
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

log = logging.getLogger("chrome_manager")

# ─── Konfiguration ───────────────────────────────────────────────

# Chrome Binary
CHROME_BIN = "/opt/google/chrome/chrome"

# CDP Port für Remote Debugging
CDP_PORT = 9222

# Persistentes Browser-Profil (NICHT /tmp!)
PROFILE_DIR = Path.home() / ".config" / "chrome-bot-profile"

# Chrome Flags
CHROME_FLAGS = [
    f"--remote-debugging-port={CDP_PORT}",
    "--remote-allow-origins=*",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-hang-monitor",
    f"--user-data-dir={PROFILE_DIR}",
]

# Start-URL
START_URL = "about:blank"

# PID-Datei
PID_FILE = Path(__file__).parent.parent / "data" / "chrome.pid"

# Log-Datei
CHROME_LOG = Path(__file__).parent.parent / "logs" / "chrome.log"


# ─── Funktionen ──────────────────────────────────────────────────

def _get_display() -> str:
    """Finde das aktive X Display."""
    display = os.environ.get("DISPLAY", "")
    if display:
        return display

    # Versuche :0 (Standard für lokale Desktops)
    if os.path.exists("/tmp/.X11-unix/X0"):
        return ":0"

    # Suche nach Xvfb
    try:
        result = subprocess.run(
            ["pgrep", "-a", "Xvfb"],
            capture_output=True, text=True, timeout=5,
        )
        if result.stdout:
            # Parse Display aus Xvfb-Kommandozeile
            for part in result.stdout.split():
                if part.startswith(":"):
                    return part
    except Exception:
        pass

    return ":0"  # Fallback


def _find_chrome_pid() -> int | None:
    """Finde die PID des laufenden Chrome mit CDP."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"chrome.*remote-debugging-port={CDP_PORT}"],
            capture_output=True, text=True, timeout=5,
        )
        pids = result.stdout.strip().split("\n")
        pids = [int(p) for p in pids if p.strip()]
        return pids[0] if pids else None
    except Exception:
        return None


def _save_pid(pid: int):
    """Speichere PID in Datei."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid))


def _read_pid() -> int | None:
    """Lese PID aus Datei."""
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except (ValueError, IOError):
            pass
    return None


def is_cdp_alive() -> bool:
    """Prüfe ob der CDP-Endpoint antwortet."""
    try:
        req = urllib.request.Request(
            f"http://localhost:{CDP_PORT}/json/version",
            headers={"User-Agent": "ChromeManager/1.0"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            return "Browser" in data or "webSocketDebuggerUrl" in data
    except Exception:
        return False


def is_running() -> bool:
    """Prüfe ob Chrome läuft UND der CDP-Endpoint antwortet."""
    pid = _find_chrome_pid()
    if not pid:
        return False
    return is_cdp_alive()


def get_status() -> dict:
    """Detaillierter Status-Report."""
    pid = _find_chrome_pid()
    cdp_alive = is_cdp_alive()

    status = {
        "running": pid is not None and cdp_alive,
        "pid": pid,
        "cdp_alive": cdp_alive,
        "cdp_port": CDP_PORT,
        "profile_dir": str(PROFILE_DIR),
        "profile_exists": PROFILE_DIR.exists(),
    }

    if cdp_alive:
        try:
            req = urllib.request.Request(
                f"http://localhost:{CDP_PORT}/json",
                headers={"User-Agent": "ChromeManager/1.0"},
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                targets = json.loads(resp.read())
                status["open_tabs"] = len(targets)
                status["tab_urls"] = [t.get("url", "?")[:80] for t in targets[:10]]
        except Exception:
            status["open_tabs"] = 0

    return status


def start(url: str = None) -> dict:
    """Starte Chrome mit CDP-Support.

    Returns:
        dict mit pid, cdp_port, status
    """
    # Schon laufend?
    if is_running():
        pid = _find_chrome_pid()
        return {
            "status": "already_running",
            "pid": pid,
            "cdp_port": CDP_PORT,
        }

    # Zombie-Prozesse aufräumen
    stop(quiet=True)

    # Display setzen
    display = _get_display()
    env = os.environ.copy()
    env["DISPLAY"] = display

    # Profil-Verzeichnis erstellen
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    # Log-Datei vorbereiten
    CHROME_LOG.parent.mkdir(parents=True, exist_ok=True)

    # Chrome starten
    start_url = url or START_URL
    cmd = [CHROME_BIN] + CHROME_FLAGS + [start_url]

    log.info("Starte Chrome: DISPLAY=%s, CDP=%d", display, CDP_PORT)
    log.info("Profil: %s", PROFILE_DIR)

    with open(CHROME_LOG, "a") as logfile:
        process = subprocess.Popen(
            cmd,
            stdout=logfile,
            stderr=logfile,
            env=env,
            start_new_session=True,
        )

    _save_pid(process.pid)

    # Warte bis CDP bereit ist
    for i in range(15):
        time.sleep(1)
        if is_cdp_alive():
            log.info("Chrome gestartet! PID=%d, CDP bereit auf Port %d", process.pid, CDP_PORT)
            return {
                "status": "started",
                "pid": process.pid,
                "cdp_port": CDP_PORT,
                "display": display,
            }

    log.warning("Chrome gestartet (PID=%d), aber CDP antwortet nicht!", process.pid)
    return {
        "status": "started_no_cdp",
        "pid": process.pid,
        "cdp_port": CDP_PORT,
        "warning": "CDP endpoint not responding after 15s",
    }


def stop(quiet: bool = False) -> dict:
    """Stoppe Chrome."""
    pid = _find_chrome_pid()
    if not pid:
        saved_pid = _read_pid()
        if saved_pid:
            try:
                os.kill(saved_pid, 0)
                pid = saved_pid
            except ProcessLookupError:
                pass

    if not pid:
        if not quiet:
            log.info("Chrome läuft nicht.")
        if PID_FILE.exists():
            PID_FILE.unlink()
        return {"status": "not_running"}

    log.info("Stoppe Chrome PID=%d...", pid)
    try:
        os.kill(pid, signal.SIGTERM)
        # Warte kurz
        for _ in range(5):
            time.sleep(1)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
        else:
            # Immer noch da → SIGKILL
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    except ProcessLookupError:
        pass

    if PID_FILE.exists():
        PID_FILE.unlink()

    # Auch Child-Prozesse beenden
    try:
        subprocess.run(
            ["pkill", "-f", f"chrome.*user-data-dir={PROFILE_DIR}"],
            timeout=5, capture_output=True,
        )
    except Exception:
        pass

    log.info("Chrome gestoppt.")
    return {"status": "stopped", "pid": pid}


def restart(url: str = None) -> dict:
    """Chrome neustarten."""
    log.info("Chrome Neustart...")
    stop()
    time.sleep(2)
    return start(url)


def health_check(auto_recover: bool = True) -> dict:
    """Health-Check mit optionalem Auto-Recovery.

    Prüft:
    1. Läuft der Chrome-Prozess?
    2. Antwortet der CDP-Endpoint?
    3. Sind die Tabs responsiv?

    Bei Problemen: Automatischer Neustart (wenn auto_recover=True).
    """
    result = {
        "healthy": False,
        "checks": {},
        "action": None,
    }

    # Check 1: Chrome-Prozess
    pid = _find_chrome_pid()
    result["checks"]["process"] = pid is not None
    result["checks"]["pid"] = pid

    # Check 2: CDP-Endpoint
    cdp_alive = is_cdp_alive()
    result["checks"]["cdp_alive"] = cdp_alive

    # Check 3: Tabs erreichbar
    if cdp_alive:
        try:
            req = urllib.request.Request(
                f"http://localhost:{CDP_PORT}/json",
                headers={"User-Agent": "ChromeManager/1.0"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                targets = json.loads(resp.read())
                result["checks"]["tabs"] = len(targets)
                result["checks"]["tabs_responsive"] = True
        except Exception:
            result["checks"]["tabs_responsive"] = False

    # Gesamtbewertung
    result["healthy"] = (
        result["checks"].get("process") is not None
        and result["checks"].get("cdp_alive", False)
        and result["checks"].get("tabs_responsive", False)
    )

    # Auto-Recovery
    if not result["healthy"] and auto_recover:
        log.warning("Chrome unhealthy! Auto-Recovery wird gestartet...")
        restart_result = restart()
        result["action"] = "restarted"
        result["restart_result"] = restart_result
        # Re-check
        result["healthy"] = is_running()

    return result


def ensure_running() -> bool:
    """Stelle sicher, dass Chrome läuft. Starte bei Bedarf.

    Returns:
        True wenn Chrome läuft (oder erfolgreich gestartet wurde)
    """
    if is_running():
        return True

    log.info("Chrome läuft nicht – starte automatisch...")
    result = start()
    return result.get("status") in ("started", "already_running")


# ─── CLI ─────────────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
    )

    if len(sys.argv) < 2:
        print("Usage: python -m lib.chrome_manager [start|stop|restart|status|health]")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    url = sys.argv[2] if len(sys.argv) > 2 else None

    if cmd == "start":
        result = start(url)
        print(json.dumps(result, indent=2))

    elif cmd == "stop":
        result = stop()
        print(json.dumps(result, indent=2))

    elif cmd == "restart":
        result = restart(url)
        print(json.dumps(result, indent=2))

    elif cmd == "status":
        status = get_status()
        print(json.dumps(status, indent=2))

    elif cmd == "health":
        result = health_check(auto_recover=True)
        print(json.dumps(result, indent=2, default=str))

    else:
        print(f"Unbekannter Befehl: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
