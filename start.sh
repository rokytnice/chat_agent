#!/bin/bash
# Startet MCP Playwright Server + Telegram-Bot.
# Beendet alle laufenden Instanzen und startet neu.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOT_SCRIPT="$SCRIPT_DIR/bot.py"
VENV="$SCRIPT_DIR/venv/bin/activate"
LOG="$SCRIPT_DIR/logs/bot.log"
MCP_PORT=8931

echo "=== Telegram Bot + MCP Playwright Starter ==="

# Alle laufenden bot.py Instanzen beenden
PIDS=$(pgrep -f "python.*bot\.py" 2>/dev/null)
if [ -n "$PIDS" ]; then
    echo "Beende Bot-Instanzen: $PIDS"
    kill $PIDS 2>/dev/null
    sleep 1
    PIDS=$(pgrep -f "python.*bot\.py" 2>/dev/null)
    [ -n "$PIDS" ] && kill -9 $PIDS 2>/dev/null
else
    echo "Keine laufenden Bot-Instanzen."
fi

# MCP Playwright Server beenden falls laufend
MCP_PIDS=$(pgrep -f "playwright/mcp" 2>/dev/null)
if [ -n "$MCP_PIDS" ]; then
    echo "Beende MCP Server: $MCP_PIDS"
    kill $MCP_PIDS 2>/dev/null
    sleep 1
    MCP_PIDS=$(pgrep -f "playwright/mcp" 2>/dev/null)
    [ -n "$MCP_PIDS" ] && kill -9 $MCP_PIDS 2>/dev/null
else
    echo "Kein laufender MCP Server."
fi

# Venv aktivieren
source "$VENV"

# Log-Verzeichnis sicherstellen
mkdir -p "$SCRIPT_DIR/logs"

# MCP Playwright Server starten (persistent, headless, shared context)
echo "Starte MCP Playwright Server auf Port $MCP_PORT..."
nohup npx @playwright/mcp@latest \
    --port $MCP_PORT \
    --headless \
    --caps vision \
    --shared-browser-context \
    >> "$SCRIPT_DIR/logs/mcp.log" 2>&1 &
MCP_PID=$!
echo "MCP Server gestartet mit PID $MCP_PID"

# Kurz warten bis MCP Server bereit ist
sleep 3

# Bot starten
echo "Starte Bot..."
nohup python "$BOT_SCRIPT" >> "$LOG" 2>&1 &
NEW_PID=$!
echo "Bot gestartet mit PID $NEW_PID"
echo ""
echo "MCP Server: PID $MCP_PID (Port $MCP_PORT)"
echo "Bot:        PID $NEW_PID"
echo "Logs:       $LOG | $SCRIPT_DIR/logs/mcp.log"
echo ""
echo "=== Live Log (Ctrl+C zum Beenden) ==="
tail -f "$LOG"
