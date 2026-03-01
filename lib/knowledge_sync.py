#!/usr/bin/env python3
"""
Personal Knowledge Base – Sync-Modul.

Erfasst persönliche Daten (Gmail, Kalender, Kontakte, Google Drive)
und synchronisiert sie in die RAG-Wissensbasis (ChromaDB).

Delta-Sync: Hash-basierte Deduplizierung verhindert doppelte Einträge.
Drive-Sync: Direkter Dateisystem-Zugriff auf ~/gdrive (0 API-Tokens).
"""

import hashlib
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

log = logging.getLogger("telegram_bridge.knowledge_sync")

DATA_DIR = Path(__file__).parent.parent / "data"
SYNC_STATE_FILE = DATA_DIR / "sync_state.json"
GDRIVE_PATH = Path.home() / "gdrive"

# Maximale Textlänge pro ChromaDB-Eintrag (Embedding-Limit)
MAX_TEXT_LENGTH = 2000

# Dateiformate die als Text indexiert werden
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".xml", ".log", ".cfg", ".ini", ".conf"}

# Übersprungene Ordner/Dateien (Sicherheit + Performance)
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".cache", ".tmp",
    "Keepass", "security", "backup", ".Trash",
}
SKIP_FILES = {".kdbx", ".key", ".pem", ".p12", ".pfx", ".gpg"}


class KnowledgeSync:
    """Synchronisiert persönliche Daten in die RAG-Wissensbasis."""

    def __init__(self):
        self._state: Dict[str, Any] = {}
        self._load_state()

    # ------------------------------------------------------------------ #
    #  State Management                                                    #
    # ------------------------------------------------------------------ #

    def _load_state(self):
        """Lade Sync-State aus JSON."""
        if SYNC_STATE_FILE.exists():
            try:
                with open(SYNC_STATE_FILE, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                log.warning("sync_state.json fehlerhaft: %s", e)
                self._state = {}

    def _save_state(self):
        """Speichere Sync-State persistent."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(SYNC_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, ensure_ascii=False, default=str)

    def get_last_sync(self, source: str) -> Optional[str]:
        """Letzter Sync-Zeitpunkt für eine Quelle."""
        return self._state.get(source, {}).get("last_sync")

    def _update_sync_state(self, source: str, count: int, hashes: Optional[Dict] = None):
        """Aktualisiere Sync-State nach erfolgreichem Sync."""
        self._state.setdefault(source, {})
        self._state[source].update({
            "last_sync": datetime.now().isoformat(),
            "entry_count": count,
            "sync_count": self._state[source].get("sync_count", 0) + 1,
        })
        if hashes is not None:
            self._state[source]["known_hashes"] = hashes
        self._save_state()

    @staticmethod
    def _hash(text: str) -> str:
        """SHA256-Hash eines Texts (erste 12 Zeichen)."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]

    # ------------------------------------------------------------------ #
    #  Gmail Sync                                                          #
    # ------------------------------------------------------------------ #

    def store_email_summaries(self, summaries: List[Dict]) -> int:
        """Speichere E-Mail-Zusammenfassungen in ChromaDB.

        Args:
            summaries: Liste von {sender, subject, date, summary, importance}

        Returns:
            Anzahl neu gespeicherter Einträge.
        """
        from lib.context_manager import ContextManager
        cm = ContextManager()

        known = set(self._state.get("gmail", {}).get("known_hashes", {}).values())
        new_hashes = dict(self._state.get("gmail", {}).get("known_hashes", {}))
        stored = 0

        for email in summaries:
            sender = email.get("sender", "")
            subject = email.get("subject", "")
            date = email.get("date", "")
            summary = email.get("summary", "")
            importance = email.get("importance", "normal")

            # Hash: Absender + Betreff + Datum
            h = self._hash(f"{sender}|{subject}|{date}")
            if h in known:
                continue

            text = (
                f"E-Mail von {sender} ({date})\n"
                f"Betreff: {subject}\n"
                f"Wichtigkeit: {importance}\n"
                f"Zusammenfassung: {summary}"
            )

            doc_id = f"gmail_{h}"
            cm.store_knowledge(text, source="gmail", doc_type="email", doc_id=doc_id)
            new_hashes[f"{sender}|{subject}"] = h
            stored += 1

        self._update_sync_state("gmail", len(new_hashes), new_hashes)
        log.info("📧 Gmail-Sync: %d neue E-Mails gespeichert (%d gesamt)", stored, len(new_hashes))
        return stored

    # ------------------------------------------------------------------ #
    #  Kalender Sync (Replace-All Strategie)                               #
    # ------------------------------------------------------------------ #

    def store_calendar_events(self, events: List[Dict]) -> int:
        """Speichere Kalender-Termine in ChromaDB (Replace-All).

        Löscht alle alten Kalender-Einträge und schreibt aktuelle Termine neu.

        Args:
            events: Liste von {title, date, time, location, description}

        Returns:
            Anzahl gespeicherter Termine.
        """
        from lib.context_manager import ContextManager
        cm = ContextManager()

        # Alte Kalender-Einträge löschen
        old_ids = self._state.get("calendar", {}).get("chromadb_ids", [])
        if old_ids:
            try:
                cm.knowledge.delete(ids=old_ids)
                log.info("📅 %d alte Kalender-Einträge gelöscht", len(old_ids))
            except Exception as e:
                log.warning("Kalender-Löschung fehlgeschlagen: %s", e)

        # Neue Termine schreiben
        new_ids = []
        for i, event in enumerate(events):
            title = event.get("title", "")
            date = event.get("date", "")
            time_ = event.get("time", "")
            location = event.get("location", "")
            description = event.get("description", "")

            text = f"Termin: {title}\nDatum: {date} {time_}"
            if location:
                text += f"\nOrt: {location}"
            if description:
                text += f"\nDetails: {description}"

            doc_id = f"cal_{self._hash(f'{title}|{date}|{time_}')}"
            cm.store_knowledge(text, source="calendar", doc_type="event", doc_id=doc_id)
            new_ids.append(doc_id)

        self._state.setdefault("calendar", {})
        self._state["calendar"]["chromadb_ids"] = new_ids
        self._update_sync_state("calendar", len(new_ids))
        log.info("📅 Kalender-Sync: %d Termine gespeichert", len(new_ids))
        return len(new_ids)

    # ------------------------------------------------------------------ #
    #  Kontakte Sync (Diff-Strategie)                                      #
    # ------------------------------------------------------------------ #

    def store_contacts(self, contacts: List[Dict]) -> int:
        """Speichere Kontakte in ChromaDB (Diff: neue/geänderte/gelöschte).

        Args:
            contacts: Liste von {name, email, phone, organization, notes}

        Returns:
            Anzahl verarbeiteter Kontakte.
        """
        from lib.context_manager import ContextManager
        cm = ContextManager()

        old_hashes = dict(self._state.get("contacts", {}).get("known_hashes", {}))
        new_hashes = {}
        stored = 0

        for contact in contacts:
            name = contact.get("name", "")
            email = contact.get("email", "")
            phone = contact.get("phone", "")
            org = contact.get("organization", "")
            notes = contact.get("notes", "")

            # Hash aus allen Feldern (ändert sich bei Updates)
            content_hash = self._hash(f"{name}|{email}|{phone}|{org}|{notes}")
            key = f"{name}|{email}"

            # Nur speichern wenn neu oder geändert
            if old_hashes.get(key) == content_hash:
                new_hashes[key] = content_hash
                continue

            text = f"Kontakt: {name}"
            if email:
                text += f"\nE-Mail: {email}"
            if phone:
                text += f"\nTelefon: {phone}"
            if org:
                text += f"\nOrganisation: {org}"
            if notes:
                text += f"\nNotizen: {notes}"

            doc_id = f"contact_{self._hash(key)}"
            cm.store_knowledge(text, source="contacts", doc_type="contact", doc_id=doc_id)
            new_hashes[key] = content_hash
            stored += 1

        # Gelöschte Kontakte entfernen
        deleted_keys = set(old_hashes.keys()) - set(new_hashes.keys())
        for key in deleted_keys:
            doc_id = f"contact_{self._hash(key)}"
            try:
                cm.knowledge.delete(ids=[doc_id])
            except Exception:
                pass

        self._update_sync_state("contacts", len(new_hashes), new_hashes)
        log.info("📇 Kontakte-Sync: %d neu/geändert, %d gelöscht", stored, len(deleted_keys))
        return stored

    # ------------------------------------------------------------------ #
    #  Google Drive Sync (Dateisystem, 0 API-Tokens)                       #
    # ------------------------------------------------------------------ #

    def sync_drive_structure(self) -> str:
        """Indexiere die Ordnerstruktur von ~/gdrive als Knowledge-Dokument.

        Returns:
            Die generierte Struktur als String.
        """
        from lib.context_manager import ContextManager
        cm = ContextManager()

        if not GDRIVE_PATH.exists():
            log.warning("Google Drive Pfad nicht gefunden: %s", GDRIVE_PATH)
            return ""

        lines = ["Google Drive Ordnerstruktur (~/gdrive):\n"]

        # Nur Top-Level + 2 Ebenen tief (sonst zu lang)
        for root, dirs, files in os.walk(GDRIVE_PATH):
            # Skip-Verzeichnisse
            dirs[:] = [d for d in sorted(dirs) if d not in SKIP_DIRS]

            depth = str(root).replace(str(GDRIVE_PATH), "").count(os.sep)
            if depth > 2:
                dirs.clear()
                continue

            indent = "  " * depth
            folder_name = Path(root).name if depth > 0 else "gdrive/"

            # Dateien zählen nach Typ
            file_count = len(files)
            pdf_count = sum(1 for f in files if f.lower().endswith(".pdf"))
            img_count = sum(1 for f in files if f.lower().endswith((".jpg", ".jpeg", ".png")))

            info = f"{indent}📁 {folder_name}/ ({file_count} Dateien"
            if pdf_count:
                info += f", {pdf_count} PDFs"
            if img_count:
                info += f", {img_count} Bilder"
            info += ")"
            lines.append(info)

        structure = "\n".join(lines)

        # Als ein Knowledge-Dokument speichern (wird bei jedem Sync überschrieben)
        cm.store_knowledge(
            structure[:MAX_TEXT_LENGTH * 5],  # Struktur darf länger sein
            source="gdrive_structure",
            doc_type="directory_tree",
            doc_id="gdrive_structure_main",
        )

        self._state.setdefault("drive_structure", {})
        self._state["drive_structure"]["last_sync"] = datetime.now().isoformat()
        self._save_state()

        log.info("📁 Drive-Struktur indexiert: %d Zeilen", len(lines))
        return structure

    def sync_drive_documents(self, max_files: int = 200) -> int:
        """Indexiere Text-basierte Dateien aus ~/gdrive (Delta-Sync).

        Args:
            max_files: Maximale Anzahl Dateien pro Sync.

        Returns:
            Anzahl neu indexierter Dateien.
        """
        from lib.context_manager import ContextManager
        cm = ContextManager()

        if not GDRIVE_PATH.exists():
            return 0

        known = dict(self._state.get("drive_docs", {}).get("known_hashes", {}))
        new_hashes = dict(known)
        stored = 0

        # Textdateien finden, sortiert nach Änderungsdatum (neueste zuerst)
        text_files = []
        for root, dirs, files in os.walk(GDRIVE_PATH):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                ext = Path(fname).suffix.lower()
                if ext in TEXT_EXTENSIONS and ext not in SKIP_FILES:
                    fpath = Path(root) / fname
                    try:
                        mtime = fpath.stat().st_mtime
                        text_files.append((mtime, fpath))
                    except OSError:
                        continue

        # Neueste zuerst
        text_files.sort(reverse=True)

        for mtime, fpath in text_files[:max_files]:
            rel_path = str(fpath.relative_to(GDRIVE_PATH))

            # Delta-Check: mtime als Hash
            mtime_hash = f"mtime:{int(mtime)}"
            if known.get(rel_path) == mtime_hash:
                new_hashes[rel_path] = mtime_hash
                continue

            # Datei lesen
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")[:MAX_TEXT_LENGTH]
            except (OSError, UnicodeDecodeError) as e:
                log.debug("Datei nicht lesbar: %s (%s)", rel_path, e)
                continue

            if not content.strip():
                continue

            text = f"Google Drive Datei: {rel_path}\n\n{content}"
            doc_id = f"gdrive_doc_{self._hash(rel_path)}"

            try:
                cm.store_knowledge(text, source="gdrive_docs", doc_type="file", doc_id=doc_id)
                new_hashes[rel_path] = mtime_hash
                stored += 1
            except Exception as e:
                log.warning("Drive-Dokument nicht speicherbar: %s (%s)", rel_path, e)

        self._update_sync_state("drive_docs", len(new_hashes), new_hashes)
        log.info("📄 Drive-Dokumente: %d neu/geändert indexiert (%d gesamt)", stored, len(new_hashes))
        return stored

    def sync_drive_pdf_catalog(self) -> int:
        """Erstelle einen PDF-Katalog (nur Dateiname + Pfad + Größe + Datum).

        Returns:
            Anzahl katalogisierter PDFs.
        """
        from lib.context_manager import ContextManager
        cm = ContextManager()

        if not GDRIVE_PATH.exists():
            return 0

        pdfs = []
        for root, dirs, files in os.walk(GDRIVE_PATH):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                if fname.lower().endswith(".pdf"):
                    fpath = Path(root) / fname
                    try:
                        stat = fpath.stat()
                        rel_path = str(fpath.relative_to(GDRIVE_PATH))
                        size_kb = stat.st_size / 1024
                        mdate = datetime.fromtimestamp(stat.st_mtime).strftime("%d.%m.%Y")
                        pdfs.append(f"  {rel_path} ({size_kb:.0f} KB, {mdate})")
                    except OSError:
                        continue

        if not pdfs:
            return 0

        # In Chunks aufteilen (ChromaDB hat Textlängen-Limits)
        chunk_size = 50
        total_chunks = 0
        for i in range(0, len(pdfs), chunk_size):
            chunk = pdfs[i:i + chunk_size]
            chunk_num = i // chunk_size
            text = f"Google Drive PDF-Katalog (Teil {chunk_num + 1}):\n\n" + "\n".join(chunk)

            doc_id = f"gdrive_pdf_catalog_{chunk_num}"
            cm.store_knowledge(
                text[:MAX_TEXT_LENGTH * 3],
                source="gdrive_pdfs",
                doc_type="pdf_catalog",
                doc_id=doc_id,
            )
            total_chunks += 1

        self._update_sync_state("drive_pdfs", len(pdfs))
        log.info("📑 PDF-Katalog: %d PDFs in %d Chunks indexiert", len(pdfs), total_chunks)
        return len(pdfs)

    def sync_drive_all(self) -> Dict[str, int]:
        """Führe kompletten Drive-Sync durch (Struktur + Dokumente + PDFs).

        Returns:
            Dict mit Anzahl pro Kategorie.
        """
        results = {
            "structure_lines": len(self.sync_drive_structure().split("\n")),
            "documents": self.sync_drive_documents(),
            "pdfs": self.sync_drive_pdf_catalog(),
        }
        log.info("🔄 Drive-Komplett-Sync: %s", results)
        return results

    # ------------------------------------------------------------------ #
    #  Hilfsmethoden für Claude-basierte Syncs                             #
    # ------------------------------------------------------------------ #

    def save_sync_data(self, source: str, data: List[Dict]):
        """Speichere Sync-Daten als JSON-Cache (z.B. aus Claude-Antwort).

        Args:
            source: "gmail", "calendar", "contacts"
            data: Die geparsten Daten als Liste von Dicts
        """
        cache_file = DATA_DIR / f"sync_{source}.json"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "synced_at": datetime.now().isoformat(),
                "count": len(data),
                "data": data,
            }, f, indent=2, ensure_ascii=False, default=str)
        log.info("💾 Sync-Cache gespeichert: %s (%d Einträge)", cache_file.name, len(data))

    def load_and_store(self, source: str) -> int:
        """Lade Sync-Cache und speichere in ChromaDB.

        Wird nach einem Claude-Sync aufgerufen um die Daten
        aus data/sync_*.json in die Wissensbasis zu übernehmen.

        Returns:
            Anzahl gespeicherter Einträge.
        """
        cache_file = DATA_DIR / f"sync_{source}.json"
        if not cache_file.exists():
            log.warning("Kein Sync-Cache für %s gefunden", source)
            return 0

        with open(cache_file, "r", encoding="utf-8") as f:
            cache = json.load(f)

        data = cache.get("data", [])
        if not data:
            return 0

        if source == "gmail":
            return self.store_email_summaries(data)
        elif source == "calendar":
            return self.store_calendar_events(data)
        elif source == "contacts":
            return self.store_contacts(data)
        else:
            log.warning("Unbekannte Sync-Quelle: %s", source)
            return 0

    # ------------------------------------------------------------------ #
    #  Status                                                              #
    # ------------------------------------------------------------------ #

    def get_sync_status(self) -> str:
        """Formatierter Sync-Status für /status und /sync Befehle."""
        sources = {
            "gmail": "📧 Gmail",
            "calendar": "📅 Kalender",
            "contacts": "📇 Kontakte",
            "drive_structure": "📁 Drive-Struktur",
            "drive_docs": "📄 Drive-Dokumente",
            "drive_pdfs": "📑 Drive-PDFs",
        }

        lines = ["🧠 Knowledge Base Sync:"]
        for key, label in sources.items():
            info = self._state.get(key, {})
            last = info.get("last_sync")
            count = info.get("entry_count", 0)
            syncs = info.get("sync_count", 0)

            if last:
                try:
                    dt = datetime.fromisoformat(last)
                    if dt.date() == datetime.now().date():
                        last_str = dt.strftime("%H:%M")
                    else:
                        last_str = dt.strftime("%d.%m. %H:%M")
                except ValueError:
                    last_str = last[:16]
                lines.append(f"  {label}: {count} Einträge (letzter Sync: {last_str}, #{syncs})")
            else:
                lines.append(f"  {label}: noch nie synchronisiert")

        return "\n".join(lines)


# ------------------------------------------------------------------ #
#  CLI-Interface für Bash-Tasks im Scheduler                           #
# ------------------------------------------------------------------ #

def main():
    """CLI-Entrypoint für Scheduler Bash-Tasks."""
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) < 2:
        print("Usage: python -m lib.knowledge_sync [drive|drive_structure|drive_docs|drive_pdfs|status]")
        sys.exit(1)

    cmd = sys.argv[1]
    ks = KnowledgeSync()

    if cmd == "drive":
        results = ks.sync_drive_all()
        print(f"✅ Drive-Sync abgeschlossen: {results}")
    elif cmd == "drive_structure":
        structure = ks.sync_drive_structure()
        print(f"✅ Struktur: {len(structure)} Zeichen")
    elif cmd == "drive_docs":
        count = ks.sync_drive_documents()
        print(f"✅ Dokumente: {count} neu indexiert")
    elif cmd == "drive_pdfs":
        count = ks.sync_drive_pdf_catalog()
        print(f"✅ PDF-Katalog: {count} PDFs")
    elif cmd == "status":
        print(ks.get_sync_status())
    else:
        print(f"Unbekannter Befehl: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
