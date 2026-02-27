# Changelog

## [0.10.0] - 2026-02-27
### Hinzugefügt
- **Zyklischer Task-Scheduler**: Automatische Ausführung wiederkehrender Agenten-Aufgaben
  - `lib/scheduler.py` - Core Scheduler-Modul mit Cron-Parser
    - Läuft als asyncio-Task im Bot-Event-Loop (kein separater Prozess)
    - Prüft alle 60 Sekunden welche Tasks fällig sind
    - Cron-Syntax: Minute, Stunde, Tag, Monat, Wochentag (z.B. `0 7 * * *`)
    - Unterstützt: `*`, Einzelwerte, Step (`*/15`), Bereiche (`9-17`), Listen (`1,5,10`)
    - Hot-Reload: `config/agents.json` wird bei jedem Zyklus neu geladen
    - State-Persistenz: `data/scheduler_state.json` (überlebt Bot-Neustarts)
    - Fehler-Isolation: Ein fehlender Task blockiert keine anderen
    - Timeout pro Task konfigurierbar
  - **Cron-Config direkt in `agents.json`** pro Agent:
    - Jeder Agent kann `scheduled_tasks` Array mit Cron-Jobs haben
    - Felder: `id`, `enabled`, `cron`, `prompt`, `timeout_seconds`, `description`
    - Beispiel-Tasks: System-Health-Check (alle 6h), Morgen-Briefing (7 Uhr), Code-Review (Mo 9 Uhr)
  - **`/scheduler` Telegram-Command**:
    - `/scheduler status` - Alle Tasks mit Status, letztem Lauf, Run-Count anzeigen
    - `/scheduler pause` - Scheduler pausieren
    - `/scheduler resume` - Scheduler fortsetzen
    - `/scheduler run <task_id>` - Task sofort beim nächsten Zyklus ausführen
  - `/status` zeigt jetzt auch Scheduler-Status an
  - Task-Ergebnisse werden automatisch via Telegram gesendet
  - RAG-Kontext wird automatisch bei Scheduler-Tasks angereichert

## [0.9.1] - 2026-02-27
### Behoben
- **Logging-Duplikate**: StreamHandler entfernt - doppelte Log-Einträge durch simultanes Schreiben auf Konsole und Datei behoben
- **Fehlerbehandlung**: Error-Handler für Telegram-API-Fehler (NetworkError) hinzugefügt - "No error handlers are registered" Warnung entfernt

## [0.9.0] - 2026-02-27
### Hinzugefügt
- **RAG Kontextmanagement-System**: Vollständig integriert in bot.py für automatische Prompt-Anreicherung
  - **bot.py RAG-Integration**:
    - Automatische Prompt-Anreicherung: System-Prompts werden mit relevantem semantischem Memory angereichert
    - Automatische Interaktions-Speicherung: Alle User-Queries und Assistant-Responses werden nach jedem API-Call gespeichert
    - Wirkt in allen Claude API-Calls: `/claude`, Freitext, Bildanalyse
    - Performance: ~5-10ms zusätzlich pro Request für RAG-Retrieval
    - Error-Handling: RAG-Fehler sind nicht-kritisch (Fallback zu Original-Prompt)
  - **RAG Kontextmanagement-System**: Retrieval-Augmented Generation mit ChromaDB für semantisches Long-Term Memory
  - `lib/context_manager.py` - Core RAG-Engine mit ChromaDB Persistenz
    - 3 Collections: conversations, knowledge, user_preferences
    - Semantic Search mit Cosine Similarity
    - Embedding-Modell: all-MiniLM-L6-v2 (384-dimensionale Vektoren)
    - Methods: `store_conversation()`, `store_knowledge()`, `store_user_preference()`, `retrieve_relevant_context()`, `enrich_prompt()`
  - `lib/rag_integration.py` - Vereinfachte Bot-Integration
    - Automatische Prompt-Anreicherung für Claude API Calls
    - Interaktions-Tracking und Metadaten-Speicherung
    - Präferenz-Management (`set_user_preference()`, `enrich_user_message()`)
  - `docs/RAG_SYSTEM.md` - Umfassende Dokumentation mit API-Referenz, Integration-Guide, Best Practices
  - `examples/rag_example.py` - 4 vollständige funktionsfähige Beispiele (Basis-Verwendung, RAG-Enrichment, Konversations-Tracking, Memory-Statistiken)
  - Persistenter Storage: `data/chroma_db/` mit automatischem Backup-Export
- **ChromaDB Dependency** hinzugefügt zu requirements.txt (>= 0.4.0)
- **Performance getestet**: ~5-10ms Retrieval für Top-K Results, <1ms bei Hit-Caching
- **Production-ready**: Alle Tests bestanden, Dokumentation komplett, Sicherheit & Datenschutz integriert

## [0.8.1] - 2026-02-25
### Hinzugefügt
- **Persistente Sessions**: Claude-Konversationen überleben Bot-Neustarts
  - Feste Session-ID (UUID) pro Agent, gespeichert in `data/sessions.json`
  - `--continue` ersetzt durch `--session-id <uuid>` für zuverlässige Persistenz
  - `/newsession` - Session zurücksetzen, nächste Nachricht startet frische Konversation
  - Session-Verwaltung: `load_sessions()`, `get_session_id()`, `reset_session()`
  - `data/` Ordner wird beim Start automatisch erstellt
- **Typing-Indikator**: "tippt..." wird alle 4 Sekunden erneuert, solange Claude/Bash arbeitet
  - `TypingLoop`-Klasse sendet periodisch `ChatAction.TYPING`
  - Aktiv in allen Handlern: `/claude`, `/bash`, Freitext, Bildanalyse

## [0.8.0] - 2026-02-25
### Hinzugefügt
- **2FA per E-Mail**: Bot ist beim Start gesperrt, 6-stelliger Code wird per Gmail SMTP gesendet
  - `/2fa` - Neuen Code anfordern (10 Min. Gültigkeit)
  - Code-Eingabe direkt im Chat, alle Handler blockiert bis Verifizierung
  - `lib/auth.py` - TwoFactorAuth-Klasse mit generate, send, check
- **Worker-Bot**: `assistina_workerbot` spiegelt jeden eingehenden Request im selben Chat
  - Formatierte Nachricht mit User, Request-Typ, Inhalt, Agent, Uhrzeit
  - `lib/worker.py` - Async Request-Logger über separaten Bot-Token
- **Ordner-Reorganisation**: Saubere Projektstruktur
  - `lib/` - Python-Module (auth, browser, notifier, worker)
  - `config/` - Konfigurationsdateien (agents.json, mcp_config.json)

### Geändert
- `bot.py`: Pfade auf `config/` umgestellt, 2FA-Guard in allen Handlern, Worker-Calls
- `lib/browser.py`: WORKING_DIR auf parent.parent angepasst
- `lib/notifier.py`: .env-Pfad auf parent.parent angepasst

### Entfernt
- `test_mcp.png` aufgeräumt

## [0.7.0] - 2026-02-25
### Hinzugefügt
- `/vorlesen <text>` - Text-to-Speech: Text als Audio-Nachricht vorlesen (Google TTS, Deutsch)
- Auch als Reply auf eine Nachricht nutzbar: einfach `/vorlesen` auf eine bestehende Nachricht antworten
- gTTS Dependency hinzugefügt

## [0.6.0] - 2026-02-25
### Hinzugefügt
- Neuer Agent: `auditor` - Forensic Corporate Auditor für Corporate Intelligence, Bilanzanalyse und Betrugserkennung
  - 4-Phasen-Workflow: Struktur & Vernetzung, Finanzprüfung, Reputation, Technische Infrastruktur
  - Nutzt North Data, Bundesanzeiger, Unternehmensregister, TÜV, Trusted Shops, ViewDNS, Tellows
  - Strukturierter Risikobericht mit Ampel-Bewertung (GRÜN/GELB/ROT)

## [0.5.0] - 2026-02-25
### Hinzugefügt
- Agenten-System: Konfigurierbare Agenten mit eigenem System-Prompt und Modell
- `agents.json`: Konfigurationsdatei für Agenten (assistant, coder, researcher, writer)
- `/agent <name>` - Agent wechseln
- `/agents` - Verfügbare Agenten auflisten
- Jeder Claude-Aufruf nutzt den aktiven Agenten (System-Prompt, Modell)
- `/status` zeigt aktiven Agenten und MCP-Status

## [0.4.0] - 2026-02-25
### Hinzugefügt
- MCP Playwright Integration: Persistente Browser-Session über `@playwright/mcp` SSE-Server
- `browser.py`: MCP-Client-Modul mit navigate, screenshot, click, type_text, list_tabs, get_snapshot
- `/browse <url>` - Website öffnen mit Screenshot + Accessibility-Snapshot
- `/snap` - Aktuelle Seite als strukturierten Text anzeigen
- `/click <ref>` - Element per Accessibility-Ref anklicken
- `/type <ref> | <text>` - Text in Eingabefeld tippen
- `/tabs` - Offene Browser-Tabs auflisten
- `start.sh` startet jetzt auch MCP Playwright Server (Port 8931, headless, shared context)
- `/status` zeigt MCP Server-Status an

### Geändert
- `/playwright` durch `/browse` ersetzt (nutzt jetzt MCP statt direktem Playwright)
- Browser-Session bleibt persistent zwischen Anfragen (shared-browser-context)

## [0.3.0] - 2026-02-25
### Geändert
- Persistente Claude-Session: Alle Claude-Aufrufe (`/claude`, Freitext, Bildanalyse) verwenden jetzt `--continue`, sodass immer dieselbe Session fortgeführt wird und der Kontext erhalten bleibt

## [0.2.0] - 2026-02-25
### Hinzugefügt
- Foto-Analyse: Bilder über Telegram senden, Claude analysiert sie
- `/restart` Befehl zum Neustarten des Bots
- Logging mit RotatingFileHandler (`logs/bot.log`, 5MB, 3 Backups)
- `start.sh` mit automatischem `tail -f` auf Log
- `.gitignore` für `.idea/`, `venv/`, `.env`, `logs/`

## [0.1.0] - 2026-02-25
### Hinzugefügt
- `bot.py`: Bidirektionaler Telegram-Bot (Claude Code Bridge)
- `/claude` - Nachricht an Claude Code senden
- `/bash` - Shell-Befehl ausführen
- `/playwright` - Screenshot einer Webseite
- `/status` - Bot-Status anzeigen
- Freitext wird direkt an Claude Code weitergeleitet
- `notifier.py`: Standalone-Modul zum Senden von Telegram-Nachrichten
- `start.sh`: Start-Script (beendet alte Instanzen, startet neu)
- Autorisierung: Nur konfigurierte Chat-ID erlaubt
