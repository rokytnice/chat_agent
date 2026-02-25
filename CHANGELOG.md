# Changelog

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
