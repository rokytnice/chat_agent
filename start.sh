#!/bin/bash
# Startet den Telegram-Bot: Beendet alle laufenden Instanzen und startet eine neue.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOT_SCRIPT="$SCRIPT_DIR/bot.py"
VENV="$SCRIPT_DIR/venv/bin/activate"
LOG="$SCRIPT_DIR/logs/bot.log"

echo "=== Telegram Bot Starter ==="

# Alle laufenden bot.py Instanzen beenden
PIDS=$(pgrep -f "python.*bot\.py" 2>/dev/null)
if [ -n "$PIDS" ]; then
    echo "Beende laufende Instanzen: $PIDS"
    kill $PIDS 2>/dev/null
    sleep 1
    # Falls noch am Leben, forcieren
    PIDS=$(pgrep -f "python.*bot\.py" 2>/dev/null)
    if [ -n "$PIDS" ]; then
        echo "Force-Kill: $PIDS"
        kill -9 $PIDS 2>/dev/null
    fi
else
    echo "Keine laufenden Instanzen gefunden."
fi

# Venv aktivieren
source "$VENV"

# Log-Verzeichnis sicherstellen
mkdir -p "$SCRIPT_DIR/logs"

# Bot im Hintergrund starten
echo "Starte Bot..."
nohup python "$BOT_SCRIPT" >> "$LOG" 2>&1 &
NEW_PID=$!
echo "Bot gestartet mit PID $NEW_PID"
echo "Log: $LOG"
echo "Stoppen: kill $NEW_PID"
echo ""
echo "=== Live Log (Ctrl+C zum Beenden) ==="
tail -f "$LOG"
