#!/bin/bash
# Startet Chrome (headed) + MCP Playwright Server (CDP) + Telegram-Bot.
# Beendet alle laufenden Instanzen und startet neu.
#
# Architektur:
#   1. Chrome (headed, GPU, persistentes Profil) → CDP auf Port 9222
#   2. MCP Playwright Server → verbindet sich per --cdp-endpoint zu Chrome
#   3. Telegram Bot → nutzt MCP für Browser-Steuerung
#
# Vorteile:
#   - Login-Sessions bleiben erhalten (Google, etc.)
#   - Kein Headless-Modus → WebGL/GPU funktioniert
#   - Chrome kann unabhängig vom MCP/Bot neugestartet werden
#   - Health-Checks und Auto-Recovery über chrome_manager.py

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOT_SCRIPT="$SCRIPT_DIR/bot.py"
VENV="$SCRIPT_DIR/venv/bin/activate"
LOG="$SCRIPT_DIR/logs/bot.log"
MCP_PORT=8931
CDP_PORT=9222

echo "=== Telegram Bot + Chrome + MCP Playwright Starter ==="

# Venv aktivieren
source "$VENV"

# Log-Verzeichnis sicherstellen
mkdir -p "$SCRIPT_DIR/logs"

# ─── Schritt 0: Alte Instanzen beenden ───────────────────────────

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

# ─── Schritt 1: Chrome starten (headed, CDP) ────────────────────

echo ""
echo "--- Schritt 1: Chrome Browser (headed, CDP Port $CDP_PORT) ---"
python -m lib.chrome_manager start
CHROME_STATUS=$?

if [ $CHROME_STATUS -ne 0 ]; then
    echo "FEHLER: Chrome konnte nicht gestartet werden!"
    echo "Versuche Health-Check mit Auto-Recovery..."
    python -m lib.chrome_manager health
fi

# Prüfe ob CDP erreichbar ist
CDP_CHECK=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$CDP_PORT/json/version" 2>/dev/null)
if [ "$CDP_CHECK" != "200" ]; then
    echo "WARNUNG: CDP Endpoint antwortet nicht (HTTP $CDP_CHECK)"
    echo "MCP wird trotzdem gestartet – Chrome muss eventuell manuell geprüft werden."
else
    echo "Chrome CDP bereit auf Port $CDP_PORT ✓"
fi

# ─── Schritt 2: MCP Playwright Server (CDP-Endpoint) ────────────

echo ""
echo "--- Schritt 2: MCP Playwright Server (Port $MCP_PORT, CDP $CDP_PORT) ---"

# MCP verbindet sich zum laufenden Chrome statt eigenen Browser zu starten
nohup npx @playwright/mcp@latest \
    --port $MCP_PORT \
    --cdp-endpoint "http://localhost:$CDP_PORT" \
    --caps vision \
    --shared-browser-context \
    >> "$SCRIPT_DIR/logs/mcp.log" 2>&1 &
MCP_PID=$!
echo "MCP Server gestartet mit PID $MCP_PID (CDP-Endpoint: localhost:$CDP_PORT)"

# Kurz warten bis MCP Server bereit ist
sleep 3

# ─── Schritt 3: Bot starten ─────────────────────────────────────

echo ""
echo "--- Schritt 3: Telegram Bot ---"
nohup python "$BOT_SCRIPT" >> "$LOG" 2>&1 &
NEW_PID=$!
echo "Bot gestartet mit PID $NEW_PID"

# ─── Zusammenfassung ────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════"
echo "  Chrome:     CDP Port $CDP_PORT (headed, GPU)"
echo "  MCP Server: PID $MCP_PID (Port $MCP_PORT)"
echo "  Bot:        PID $NEW_PID"
echo "  Profil:     ~/.config/chrome-bot-profile/"
echo "  Logs:       $LOG | $SCRIPT_DIR/logs/mcp.log"
echo "═══════════════════════════════════════════════"
echo ""
echo "=== Live Log (Ctrl+C zum Beenden) ==="
tail -f "$LOG"
