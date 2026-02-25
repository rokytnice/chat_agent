# Changelog

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
