#!/usr/bin/env python3
"""Aktienmarkt Crash-Monitor – prüft auf Kurseinbrüche >= 20%.

Überwacht wichtige Indizes und Einzelaktien. Sendet Telegram-Alert
wenn eine Aktie/Index >= 20% vom letzten Schlusskurs einbricht.

Verwendung:
    python -m lib.stock_monitor          # Einmal prüfen
    python -m lib.stock_monitor --test   # Test-Nachricht senden
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import yfinance as yf

# Schwelle: ab wieviel % Verlust wird alarmiert
CRASH_THRESHOLD = -20.0  # in Prozent

# Überwachte Ticker (Symbol → Anzeigename)
WATCHLIST = {
    # --- Indizes ---
    "^GSPC": "S&P 500",
    "^DJI": "Dow Jones",
    "^IXIC": "NASDAQ Composite",
    "^GDAXI": "DAX 40",
    "^STOXX50E": "Euro Stoxx 50",
    "^FTSE": "FTSE 100",
    "^N225": "Nikkei 225",
    "^HSI": "Hang Seng",
    # --- Top US-Aktien ---
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "AMZN": "Amazon",
    "NVDA": "NVIDIA",
    "META": "Meta",
    "TSLA": "Tesla",
    "BRK-B": "Berkshire Hathaway",
    "JPM": "JPMorgan Chase",
    "V": "Visa",
    # --- Top EU-Aktien ---
    "SAP.DE": "SAP",
    "SIE.DE": "Siemens",
    "ALV.DE": "Allianz",
    "DTE.DE": "Deutsche Telekom",
    "BAS.DE": "BASF",
    "BMW.DE": "BMW",
    "MBG.DE": "Mercedes-Benz",
    "VOW3.DE": "Volkswagen",
    "DHL.DE": "DHL Group",
    "MUV2.DE": "Munich Re",
}

# State-Datei: speichert letzte bekannte Kurse für Vergleich
STATE_FILE = Path(__file__).parent.parent / "data" / "stock_state.json"


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def check_markets() -> list[dict]:
    """Prüft alle Ticker auf Kurseinbrüche. Gibt Liste der Alerts zurück."""
    state = _load_state()
    alerts = []
    new_state = {}
    errors = []

    # Alle Ticker auf einmal abrufen (effizienter)
    tickers_str = " ".join(WATCHLIST.keys())
    try:
        data = yf.download(
            tickers_str,
            period="5d",
            interval="1d",
            group_by="ticker",
            progress=False,
            threads=True,
        )
    except Exception as e:
        errors.append(f"yfinance Download-Fehler: {e}")
        return alerts

    for symbol, name in WATCHLIST.items():
        try:
            # Kursdaten extrahieren
            if len(WATCHLIST) == 1:
                ticker_data = data
            else:
                ticker_data = data[symbol] if symbol in data.columns.get_level_values(0) else None

            if ticker_data is None or ticker_data.empty:
                continue

            # Letzten verfügbaren Schlusskurs und vorherigen holen
            closes = ticker_data["Close"].dropna()
            if len(closes) < 2:
                continue

            current_price = float(closes.iloc[-1])
            prev_close = float(closes.iloc[-2])

            if prev_close == 0:
                continue

            change_pct = ((current_price - prev_close) / prev_close) * 100

            # State aktualisieren
            new_state[symbol] = {
                "name": name,
                "price": round(current_price, 2),
                "prev_close": round(prev_close, 2),
                "change_pct": round(change_pct, 2),
                "checked": datetime.now().isoformat(),
            }

            # Crash erkannt?
            if change_pct <= CRASH_THRESHOLD:
                alerts.append({
                    "symbol": symbol,
                    "name": name,
                    "price": round(current_price, 2),
                    "prev_close": round(prev_close, 2),
                    "change_pct": round(change_pct, 2),
                })

        except Exception as e:
            errors.append(f"{symbol} ({name}): {e}")

    # State speichern
    new_state["_meta"] = {
        "last_check": datetime.now().isoformat(),
        "tickers_checked": len(new_state) - (1 if "_meta" in new_state else 0),
        "alerts_count": len(alerts),
        "errors": errors[:5] if errors else [],
    }
    _save_state(new_state)

    return alerts


def format_alert(alerts: list[dict]) -> str:
    """Formatiert Alerts als Telegram-Nachricht."""
    if not alerts:
        return ""

    lines = ["🚨 AKTIEN-CRASH ALERT 🚨\n"]
    for a in alerts:
        arrow = "📉"
        lines.append(
            f"{arrow} {a['name']} ({a['symbol']})\n"
            f"   Kurs: {a['price']} (Vortag: {a['prev_close']})\n"
            f"   Veränderung: {a['change_pct']:+.1f}%\n"
        )

    lines.append(f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    return "\n".join(lines)


def run():
    """Hauptfunktion: Prüft Märkte und sendet ggf. Alert."""
    from lib.notifier import send_message

    alerts = check_markets()

    if alerts:
        msg = format_alert(alerts)
        send_message(msg)
        print(f"ALERT: {len(alerts)} Crash(es) erkannt, Telegram gesendet.")
        return True
    else:
        # State laden für Status-Ausgabe
        state = _load_state()
        meta = state.get("_meta", {})
        checked = meta.get("tickers_checked", 0)
        print(f"OK: {checked} Ticker geprüft, keine Crashes (Schwelle: {CRASH_THRESHOLD}%)")
        return False


if __name__ == "__main__":
    if "--test" in sys.argv:
        from lib.notifier import send_message
        test_alert = [{
            "symbol": "TEST",
            "name": "Test-Aktie",
            "price": 80.00,
            "prev_close": 100.00,
            "change_pct": -20.0,
        }]
        msg = format_alert(test_alert)
        send_message(msg)
        print("Test-Alert gesendet.")
    else:
        run()
