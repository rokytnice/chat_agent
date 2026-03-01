"""
Proaktives Erinnerungssystem – erkennt Reminder in Nachrichten,
speichert sie und benachrichtigt wenn sie fällig sind.

Kein Claude nötig: Erkennung via Regex, Datum-Parsing via dateparser.
"""

import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict

log = logging.getLogger("telegram_bridge.reminders")

DATA_DIR = Path(__file__).parent.parent / "data"
REMINDERS_FILE = DATA_DIR / "reminders.json"

# Deutsche Reminder-Trigger-Patterns (einmalig kompiliert)
REMINDER_PATTERNS = [
    re.compile(r"erinner[e]?\s+(mich|uns)", re.IGNORECASE),
    re.compile(r"(ich\s+muss|wir\s+müssen|nicht\s+vergessen)", re.IGNORECASE),
    re.compile(r"(denk[e]?\s+dran|vergiss\s+nicht)", re.IGNORECASE),
    re.compile(r"(bis\s+(spätestens|zum)|deadline|frist)", re.IGNORECASE),
    re.compile(r"termin\s+(am|um|ist|für)", re.IGNORECASE),
    re.compile(r"(nächste[rn]?\s+woche|morgen|übermorgen)\s+.{0,30}(muss|soll|termin|anruf)", re.IGNORECASE),
    re.compile(r"(todo|aufgabe|zu\s+erledigen)\s*:", re.IGNORECASE),
]


class ReminderManager:
    """Verwaltet Erinnerungen: Erkennung, Speicherung, Fälligkeitsprüfung."""

    def __init__(self):
        self._reminders: List[Dict] = []
        self._load()

    # ------------------------------------------------------------------ #
    #  Persistenz                                                          #
    # ------------------------------------------------------------------ #

    def _load(self):
        """Lade Erinnerungen aus JSON-Datei."""
        if REMINDERS_FILE.exists():
            try:
                with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
                    self._reminders = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                log.warning("Reminders-Datei fehlerhaft, starte leer: %s", e)
                self._reminders = []

    def _save(self):
        """Speichere Erinnerungen in JSON-Datei."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._reminders, f, indent=2, ensure_ascii=False, default=str)

    # ------------------------------------------------------------------ #
    #  Erkennung                                                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    def detect_reminder(text: str) -> bool:
        """Prüfe ob der Text ein Reminder-Pattern enthält."""
        return any(p.search(text) for p in REMINDER_PATTERNS)

    # ------------------------------------------------------------------ #
    #  Speicherung                                                         #
    # ------------------------------------------------------------------ #

    def parse_and_store(self, text: str, chat_id: str) -> Optional[Dict]:
        """Parse eine Erinnerung aus dem Text und speichere sie.

        Returns:
            Dict mit Reminder-Daten oder None bei Fehler.
        """
        import dateparser  # Lazy Import – nur bei tatsächlichem Bedarf

        # Datum aus dem Text extrahieren
        parsed_date = dateparser.parse(
            text,
            languages=["de"],
            settings={
                "PREFER_DATES_FROM": "future",
                "RELATIVE_BASE": datetime.now(),
            },
        )

        if parsed_date is None or parsed_date < datetime.now():
            # Fallback: morgen 9:00 Uhr
            parsed_date = (datetime.now() + timedelta(days=1)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )

        reminder = {
            "id": str(uuid.uuid4())[:8],
            "text": text,
            "due_date": parsed_date.isoformat(),
            "created_at": datetime.now().isoformat(),
            "chat_id": chat_id,
            "sent": False,
        }

        self._reminders.append(reminder)
        self._save()

        log.info(
            "🔔 Reminder gespeichert: '%s' → fällig am %s",
            text[:60], parsed_date.strftime("%d.%m.%Y %H:%M"),
        )
        return reminder

    # ------------------------------------------------------------------ #
    #  Fälligkeitsprüfung                                                  #
    # ------------------------------------------------------------------ #

    def get_due_reminders(self) -> List[Dict]:
        """Gibt alle fälligen, noch nicht gesendeten Erinnerungen zurück."""
        now = datetime.now()
        due = []
        for r in self._reminders:
            if r.get("sent"):
                continue
            try:
                due_date = datetime.fromisoformat(r["due_date"])
                if due_date <= now:
                    due.append(r)
            except (ValueError, KeyError):
                continue
        return due

    def mark_sent(self, reminder_id: str):
        """Markiere eine Erinnerung als gesendet."""
        for r in self._reminders:
            if r["id"] == reminder_id:
                r["sent"] = True
                r["sent_at"] = datetime.now().isoformat()
        self._save()

    # ------------------------------------------------------------------ #
    #  Wartung                                                             #
    # ------------------------------------------------------------------ #

    def cleanup_old(self, days: int = 30):
        """Entferne gesendete Erinnerungen älter als N Tage."""
        cutoff = datetime.now() - timedelta(days=days)
        before = len(self._reminders)
        self._reminders = [
            r for r in self._reminders
            if not r.get("sent")
            or datetime.fromisoformat(r.get("sent_at", r["created_at"])) > cutoff
        ]
        removed = before - len(self._reminders)
        if removed > 0:
            log.info("🧹 %d alte Erinnerungen entfernt", removed)
            self._save()

    def get_active(self) -> List[Dict]:
        """Gibt alle aktiven (nicht gesendeten) Erinnerungen zurück."""
        return [r for r in self._reminders if not r.get("sent")]

    def get_stats(self) -> str:
        """Formatierter Status-String."""
        active = self.get_active()
        total = len(self._reminders)
        sent = total - len(active)
        lines = [f"🔔 Erinnerungen: {len(active)} aktiv, {sent} erledigt"]
        for r in sorted(active, key=lambda x: x.get("due_date", "")):
            try:
                due = datetime.fromisoformat(r["due_date"]).strftime("%d.%m. %H:%M")
            except (ValueError, KeyError):
                due = "?"
            lines.append(f"  → {due}: {r['text'][:60]}")
        return "\n".join(lines)
