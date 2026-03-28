#!/usr/bin/env python3
"""Aktienmarkt Crash-Monitor – überwacht ALLE Aktien der großen Indizes.

Lädt die Bestandteile von 8 großen Indizes (S&P 500, NASDAQ-100, DAX 40,
MDAX 50, FTSE 100, Euro Stoxx 50, Nikkei 225, Hang Seng) und prüft
alle ~1.000 Einzelaktien + Indizes auf Kurseinbrüche >= 20%.

Verwendung:
    python -m lib.stock_monitor              # Alle Ticker prüfen
    python -m lib.stock_monitor --update     # Ticker-Liste aktualisieren
    python -m lib.stock_monitor --test       # Test-Alert senden
    python -m lib.stock_monitor --stats      # Statistiken anzeigen
"""

import json
import sys
import time
import logging
from datetime import datetime
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

log = logging.getLogger("stock_monitor")

# Schwelle: ab wieviel % Verlust wird alarmiert
CRASH_THRESHOLD = -20.0  # in Prozent

# Batch-Größe für yfinance Downloads
BATCH_SIZE = 50

# Dateipfade
DATA_DIR = Path(__file__).parent.parent / "data"
STATE_FILE = DATA_DIR / "stock_state.json"
TICKERS_FILE = DATA_DIR / "stock_tickers.json"

# HTTP-Header für Wikipedia-Scraping
HEADERS = {"User-Agent": "Mozilla/5.0 (StockMonitor/1.0; Python)"}

# Indizes die immer überwacht werden
INDEX_TICKERS = {
    "^GSPC": "S&P 500",
    "^DJI": "Dow Jones",
    "^IXIC": "NASDAQ Composite",
    "^GDAXI": "DAX 40",
    "^STOXX50E": "Euro Stoxx 50",
    "^FTSE": "FTSE 100",
    "^N225": "Nikkei 225",
    "^HSI": "Hang Seng",
}

# ------------------------------------------------------------------ #
#  Ticker-Listen von Wikipedia laden                                   #
# ------------------------------------------------------------------ #

def _fetch_table(url: str, **kwargs) -> pd.DataFrame | None:
    """Fetch HTML table from Wikipedia with proper User-Agent."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        tables = pd.read_html(StringIO(r.text), **kwargs)
        return tables
    except Exception as e:
        log.warning("Fehler beim Laden von %s: %s", url, e)
        return None


def fetch_sp500() -> dict[str, str]:
    """S&P 500 Bestandteile von Wikipedia."""
    tables = _fetch_table("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    if not tables:
        return {}
    df = tables[0]
    result = {}
    for _, row in df.iterrows():
        symbol = str(row.get("Symbol", "")).strip().replace(".", "-")
        name = str(row.get("Security", "")).strip()
        if symbol and name:
            result[symbol] = name
    log.info("S&P 500: %d Ticker geladen", len(result))
    return result


def fetch_nasdaq100() -> dict[str, str]:
    """NASDAQ-100 Bestandteile von Wikipedia."""
    tables = _fetch_table("https://en.wikipedia.org/wiki/NASDAQ-100")
    if not tables:
        return {}
    # Finde Tabelle mit 'Ticker' Spalte
    for df in tables:
        cols = [str(c).lower() for c in df.columns]
        if "ticker" in cols:
            result = {}
            ticker_col = df.columns[cols.index("ticker")]
            name_col = None
            for c in ["company", "security", "name"]:
                if c in cols:
                    name_col = df.columns[cols.index(c)]
                    break
            if name_col is None:
                name_col = df.columns[1] if len(df.columns) > 1 else ticker_col
            for _, row in df.iterrows():
                symbol = str(row[ticker_col]).strip()
                name = str(row[name_col]).strip()
                if symbol and len(symbol) < 10:
                    result[symbol] = name
            if result:
                log.info("NASDAQ-100: %d Ticker geladen", len(result))
                return result
    return {}


def fetch_dax() -> dict[str, str]:
    """DAX 40 Bestandteile von Wikipedia."""
    tables = _fetch_table("https://en.wikipedia.org/wiki/DAX")
    if not tables:
        return {}
    for df in tables:
        cols = [str(c).lower() for c in df.columns]
        if "ticker" in cols or "ticker symbol" in cols:
            result = {}
            ticker_idx = None
            for c in ["ticker", "ticker symbol"]:
                if c in cols:
                    ticker_idx = cols.index(c)
                    break
            if ticker_idx is None:
                continue
            ticker_col = df.columns[ticker_idx]
            name_col = None
            for c in ["company", "name"]:
                if c in cols:
                    name_col = df.columns[cols.index(c)]
                    break
            if name_col is None:
                name_col = df.columns[0]
            for _, row in df.iterrows():
                symbol = str(row[ticker_col]).strip()
                name = str(row[name_col]).strip()
                if not symbol.endswith(".DE") and not symbol.startswith("^"):
                    symbol = symbol + ".DE"
                if symbol and len(symbol) < 15:
                    result[symbol] = name
            if len(result) >= 30:
                log.info("DAX 40: %d Ticker geladen", len(result))
                return result
    return {}


def fetch_mdax() -> dict[str, str]:
    """MDAX 50 Bestandteile von Wikipedia."""
    tables = _fetch_table("https://en.wikipedia.org/wiki/MDAX")
    if not tables:
        return {}
    for df in tables:
        cols = [str(c).lower() for c in df.columns]
        if "symbol" in cols or "ticker" in cols:
            result = {}
            sym_col = None
            for c in ["symbol", "ticker"]:
                if c in cols:
                    sym_col = df.columns[cols.index(c)]
                    break
            if sym_col is None:
                continue
            name_col = df.columns[0] if cols[0] not in ["symbol", "ticker"] else df.columns[1]
            for _, row in df.iterrows():
                symbol = str(row[sym_col]).strip()
                name = str(row[name_col]).strip()
                if not symbol.endswith(".DE") and not symbol.startswith("^"):
                    symbol = symbol + ".DE"
                if symbol and len(symbol) < 15:
                    result[symbol] = name
            if len(result) >= 30:
                log.info("MDAX: %d Ticker geladen", len(result))
                return result
    return {}


def fetch_ftse100() -> dict[str, str]:
    """FTSE 100 Bestandteile von Wikipedia."""
    tables = _fetch_table("https://en.wikipedia.org/wiki/FTSE_100_Index")
    if not tables:
        return {}
    for df in tables:
        cols = [str(c).lower() for c in df.columns]
        if "ticker" in cols or "epic" in cols:
            result = {}
            ticker_idx = None
            for c in ["ticker", "epic"]:
                if c in cols:
                    ticker_idx = cols.index(c)
                    break
            if ticker_idx is None:
                continue
            ticker_col = df.columns[ticker_idx]
            name_col = None
            for c in ["company", "name"]:
                if c in cols:
                    name_col = df.columns[cols.index(c)]
                    break
            if name_col is None:
                name_col = df.columns[0]
            for _, row in df.iterrows():
                symbol = str(row[ticker_col]).strip()
                name = str(row[name_col]).strip()
                # FTSE Ticker brauchen .L Suffix für yfinance
                if not symbol.endswith(".L") and not symbol.startswith("^"):
                    symbol = symbol + ".L"
                if symbol and len(symbol) < 15:
                    result[symbol] = name
            if len(result) >= 50:
                log.info("FTSE 100: %d Ticker geladen", len(result))
                return result
    return {}


def fetch_eurostoxx50() -> dict[str, str]:
    """Euro Stoxx 50 Bestandteile von Wikipedia."""
    tables = _fetch_table("https://en.wikipedia.org/wiki/EURO_STOXX_50")
    if not tables:
        return {}
    for df in tables:
        cols = [str(c).lower() for c in df.columns]
        if "ticker" in cols:
            result = {}
            ticker_col = df.columns[cols.index("ticker")]
            name_col = None
            for c in ["name", "company"]:
                if c in cols:
                    name_col = df.columns[cols.index(c)]
                    break
            if name_col is None:
                name_col = df.columns[0]
            for _, row in df.iterrows():
                symbol = str(row[ticker_col]).strip()
                name = str(row[name_col]).strip()
                if symbol and len(symbol) < 15:
                    result[symbol] = name
            if len(result) >= 30:
                log.info("Euro Stoxx 50: %d Ticker geladen", len(result))
                return result
    return {}


def fetch_hangseng() -> dict[str, str]:
    """Hang Seng Index Bestandteile von Wikipedia."""
    tables = _fetch_table("https://en.wikipedia.org/wiki/Hang_Seng_Index")
    if not tables:
        return {}
    for df in tables:
        cols = [str(c).lower() for c in df.columns]
        if "ticker" in cols:
            result = {}
            ticker_col = df.columns[cols.index("ticker")]
            name_col = None
            for c in ["name", "company"]:
                if c in cols:
                    name_col = df.columns[cols.index(c)]
                    break
            if name_col is None:
                name_col = df.columns[0]
            for _, row in df.iterrows():
                raw = str(row[ticker_col]).strip()
                name = str(row[name_col]).strip()
                # Format: "SEHK: 5" oder "0005" → "0005.HK"
                number = raw.replace("SEHK:", "").replace("sehk:", "").strip()
                try:
                    number = str(int(float(number))).zfill(4)
                except (ValueError, TypeError):
                    continue
                symbol = f"{number}.HK"
                result[symbol] = name
            if len(result) >= 30:
                log.info("Hang Seng: %d Ticker geladen", len(result))
                return result
    return {}


def fetch_nikkei225() -> dict[str, str]:
    """Nikkei 225 Bestandteile von japanischer Wikipedia."""
    tables = _fetch_table("https://ja.wikipedia.org/wiki/%E6%97%A5%E7%B5%8C%E5%B9%B3%E5%9D%87%E6%A0%AA%E4%BE%A1")
    if not tables:
        return {}
    result = {}
    for df in tables:
        cols = list(df.columns)
        # Suche nach Tabellen mit Ticker-Code Spalte (証券コード)
        code_col = None
        name_col = None
        for i, c in enumerate(cols):
            c_str = str(c)
            if "コード" in c_str or "証券" in c_str:
                code_col = cols[i]
            if "銘柄" in c_str or "企業" in c_str or "名" in c_str:
                name_col = cols[i]
        if code_col is None:
            continue
        if name_col is None:
            name_col = cols[1] if len(cols) > 1 else code_col
        for _, row in df.iterrows():
            try:
                code = str(int(float(row[code_col])))
                name = str(row[name_col]).strip()
                symbol = f"{code}.T"
                result[symbol] = name
            except (ValueError, TypeError):
                continue
    if result:
        log.info("Nikkei 225: %d Ticker geladen", len(result))
    return result


def update_ticker_list() -> dict[str, str]:
    """Aktualisiert die komplette Ticker-Liste von allen Indizes."""
    all_tickers = {}

    # Indizes selbst immer dabei
    all_tickers.update(INDEX_TICKERS)

    fetchers = [
        ("S&P 500", fetch_sp500),
        ("NASDAQ-100", fetch_nasdaq100),
        ("DAX 40", fetch_dax),
        ("MDAX", fetch_mdax),
        ("FTSE 100", fetch_ftse100),
        ("Euro Stoxx 50", fetch_eurostoxx50),
        ("Hang Seng", fetch_hangseng),
        ("Nikkei 225", fetch_nikkei225),
    ]

    index_stats = {}
    for index_name, fetcher in fetchers:
        try:
            tickers = fetcher()
            count = len(tickers)
            all_tickers.update(tickers)
            index_stats[index_name] = count
            print(f"  ✅ {index_name}: {count} Ticker")
        except Exception as e:
            print(f"  ❌ {index_name}: Fehler – {e}")
            index_stats[index_name] = 0
        time.sleep(1)  # Wikipedia nicht überlasten

    # Speichern
    # Bereinigung: nan/leere Namen durch Symbol ersetzen
    for symbol in list(all_tickers.keys()):
        name = all_tickers[symbol]
        if not name or name == "nan" or name == "NaN" or str(name) == "nan":
            clean = symbol.replace(".DE", "").replace(".L", "").replace(".T", "").replace(".HK", "")
            all_tickers[symbol] = clean

    data = {
        "tickers": all_tickers,
        "meta": {
            "updated": datetime.now().isoformat(),
            "total_count": len(all_tickers),
            "indices": index_stats,
        }
    }
    TICKERS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\n📊 Gesamt: {len(all_tickers)} Ticker gespeichert in {TICKERS_FILE.name}")
    return all_tickers


def load_tickers() -> dict[str, str]:
    """Lädt Ticker-Liste aus Datei. Falls nicht vorhanden, wird sie erstellt."""
    if TICKERS_FILE.exists():
        try:
            data = json.loads(TICKERS_FILE.read_text())
            tickers = data.get("tickers", {})
            if tickers:
                return tickers
        except (json.JSONDecodeError, KeyError):
            pass
    # Datei fehlt oder leer → neu erstellen
    print("⚠️ Ticker-Liste nicht gefunden, erstelle neu...")
    return update_ticker_list()


# ------------------------------------------------------------------ #
#  Markt-Check                                                         #
# ------------------------------------------------------------------ #

def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def check_markets() -> list[dict]:
    """Prüft alle Ticker auf Kurseinbrüche. Gibt Liste der Alerts zurück."""
    watchlist = load_tickers()
    alerts = []
    new_state = {}
    errors = []
    total_checked = 0

    # In Batches aufteilen
    symbols = list(watchlist.keys())
    batches = [symbols[i:i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]

    print(f"Prüfe {len(symbols)} Ticker in {len(batches)} Batches...")

    for batch_num, batch in enumerate(batches, 1):
        tickers_str = " ".join(batch)
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
            errors.append(f"Batch {batch_num} Download-Fehler: {e}")
            continue

        for symbol in batch:
            try:
                # Kursdaten extrahieren
                if len(batch) == 1:
                    ticker_data = data
                else:
                    ticker_data = data[symbol] if symbol in data.columns.get_level_values(0) else None

                if ticker_data is None or ticker_data.empty:
                    continue

                closes = ticker_data["Close"].dropna()
                if len(closes) < 2:
                    continue

                current_price = float(closes.iloc[-1])
                prev_close = float(closes.iloc[-2])

                if prev_close == 0:
                    continue

                change_pct = ((current_price - prev_close) / prev_close) * 100
                name = watchlist.get(symbol, symbol)
                total_checked += 1

                # Nur bei Crash State speichern (spart Speicher bei ~1000 Tickern)
                if change_pct <= CRASH_THRESHOLD:
                    alerts.append({
                        "symbol": symbol,
                        "name": name,
                        "price": round(current_price, 2),
                        "prev_close": round(prev_close, 2),
                        "change_pct": round(change_pct, 2),
                    })

            except Exception as e:
                errors.append(f"{symbol}: {e}")

        # Kurze Pause zwischen Batches
        if batch_num < len(batches):
            time.sleep(0.5)

    # State speichern (kompakt: nur Meta + Alerts)
    new_state["_meta"] = {
        "last_check": datetime.now().isoformat(),
        "tickers_total": len(symbols),
        "tickers_checked": total_checked,
        "alerts_count": len(alerts),
        "batches": len(batches),
        "errors_count": len(errors),
        "errors": errors[:10] if errors else [],
    }
    if alerts:
        new_state["_alerts"] = alerts
    _save_state(new_state)

    return alerts


def format_alert(alerts: list[dict]) -> str:
    """Formatiert Alerts als Telegram-Nachricht."""
    if not alerts:
        return ""

    lines = [f"🚨 AKTIEN-CRASH ALERT ({len(alerts)} Titel) 🚨\n"]

    # Sortiert nach stärkstem Einbruch
    alerts_sorted = sorted(alerts, key=lambda a: a["change_pct"])

    for a in alerts_sorted:
        lines.append(
            f"📉 {a['name']} ({a['symbol']})\n"
            f"   Kurs: {a['price']} (Vortag: {a['prev_close']})\n"
            f"   Veränderung: {a['change_pct']:+.1f}%\n"
        )

    # State laden für Gesamtstatistik
    state = _load_state()
    meta = state.get("_meta", {})
    lines.append(
        f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"📊 {meta.get('tickers_checked', '?')}/{meta.get('tickers_total', '?')} Ticker geprüft"
    )
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
        state = _load_state()
        meta = state.get("_meta", {})
        checked = meta.get("tickers_checked", 0)
        total = meta.get("tickers_total", 0)
        err = meta.get("errors_count", 0)
        print(f"OK: {checked}/{total} Ticker geprüft, keine Crashes (Schwelle: {CRASH_THRESHOLD}%)")
        if err:
            print(f"   ⚠️ {err} Fehler (siehe data/stock_state.json)")
        return False


def show_stats():
    """Zeigt Statistiken der Ticker-Liste und letztem Check."""
    if TICKERS_FILE.exists():
        data = json.loads(TICKERS_FILE.read_text())
        meta = data.get("meta", {})
        print(f"📊 Ticker-Liste: {meta.get('total_count', '?')} Ticker")
        print(f"   Aktualisiert: {meta.get('updated', '?')}")
        for idx, count in meta.get("indices", {}).items():
            print(f"   {idx}: {count}")
    else:
        print("❌ Keine Ticker-Liste vorhanden (--update ausführen)")

    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())
        meta = state.get("_meta", {})
        print(f"\n📈 Letzter Check: {meta.get('last_check', '?')}")
        print(f"   Geprüft: {meta.get('tickers_checked', '?')}/{meta.get('tickers_total', '?')}")
        print(f"   Alerts: {meta.get('alerts_count', 0)}")
        print(f"   Fehler: {meta.get('errors_count', 0)}")


if __name__ == "__main__":
    if "--update" in sys.argv:
        print("🔄 Aktualisiere Ticker-Liste von Wikipedia...")
        update_ticker_list()
    elif "--test" in sys.argv:
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
    elif "--stats" in sys.argv:
        show_stats()
    else:
        run()
