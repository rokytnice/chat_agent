#!/usr/bin/env python3
"""
Fake Defense AI – News Agent
Sucht täglich nach aktuellen Nachrichten über Fake-Shops, Online-Betrug
und Internetkriminalität und erstellt daraus einen WordPress-Blogbeitrag.

Usage:
    python -m lib.news_agent              # Normaler Lauf (JSON-Output)
    python -m lib.news_agent --dry-run    # Nur Vorschau, kein State-Update
    python -m lib.news_agent --force      # Auch wenn heute schon gelaufen
    python -m lib.news_agent --lookback 180  # Artikel der letzten 180 Tage
"""

import json
import hashlib
import sys
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import feedparser
import requests

# Pfade
BASE_DIR = Path(__file__).parent.parent
STATE_FILE = BASE_DIR / "data" / "news_seen.json"

# Suchbegriffe für Google News RSS
SEARCH_QUERIES_DE = [
    "Fake Shop Betrug",
    "Fake-Shop Warnung",
    "Online Shopping Betrug Deutschland",
    "Fakeshop Polizei",
    "Internetbetrug Online-Handel",
    "Phishing Online-Shop",
    "Verbraucherschutz Fake Shop",
]

SEARCH_QUERIES_EN = [
    "fake online shop scam",
    "fake e-commerce fraud",
    "online shopping scam warning",
    "fraudulent online store",
    "consumer protection fake shop",
    "phishing online store",
]

# Google News RSS URL Templates
GNEWS_RSS_DE = "https://news.google.com/rss/search?q={query}&hl=de&gl=DE&ceid=DE:de"
GNEWS_RSS_EN = "https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en"

# Maximale Artikel pro Blogpost
MAX_ARTICLES = 15

# Fallback: Artikel nicht älter als X Stunden (wenn kein letzter Lauf bekannt)
DEFAULT_MAX_AGE_HOURS = 24


def load_state() -> dict:
    """Lade den State mit bereits gesehenen Artikeln."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "seen_hashes": [],
        "last_run": None,
        "last_run_timestamp": None,
        "total_posts_created": 0,
    }


def save_state(state: dict):
    """Speichere den State."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def article_hash(title: str, source: str) -> str:
    """Erzeuge einen eindeutigen Hash für einen Artikel."""
    text = f"{title.strip().lower()}|{source.strip().lower()}"
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def clean_google_title(title: str) -> tuple[str, str]:
    """Extrahiere Titel und Quelle aus Google News Titel.
    Google News Format: 'Artikeltitel - Quellenname'
    """
    parts = title.rsplit(" - ", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return title.strip(), "Unbekannt"


def extract_real_url(google_url: str) -> str:
    """Versuche die echte URL aus dem Google News Redirect zu extrahieren."""
    # Google News URLs sind Redirects, behalten wir erstmal so
    return google_url


def fetch_news(state: dict, lookback_hours: int = None) -> list[dict]:
    """Hole aktuelle Nachrichten aus Google News RSS Feeds.

    Der Cutoff basiert auf:
    - lookback_hours (wenn explizit angegeben)
    - dem letzten Lauf-Zeitstempel
    - Sonst → Fallback auf DEFAULT_MAX_AGE_HOURS (24h)
    """
    all_articles = []
    seen_titles = set()

    # Cutoff dynamisch berechnen
    if lookback_hours:
        cutoff = datetime.now() - timedelta(hours=lookback_hours)
        days = lookback_hours // 24
        print(f"⏱️ Cutoff: Letzte {days} Tage ({cutoff.strftime('%d.%m.%Y %H:%M')})", file=sys.stderr)
    else:
        last_run_ts = state.get("last_run_timestamp")
        if last_run_ts:
            try:
                cutoff = datetime.fromisoformat(last_run_ts)
                print(f"⏱️ Cutoff: Artikel seit letztem Lauf ({cutoff.strftime('%d.%m.%Y %H:%M')})", file=sys.stderr)
            except (ValueError, TypeError):
                cutoff = datetime.now() - timedelta(hours=DEFAULT_MAX_AGE_HOURS)
                print(f"⏱️ Cutoff: Letzte {DEFAULT_MAX_AGE_HOURS}h (Fallback)", file=sys.stderr)
        else:
            cutoff = datetime.now() - timedelta(hours=DEFAULT_MAX_AGE_HOURS)
            print(f"⏱️ Cutoff: Letzte {DEFAULT_MAX_AGE_HOURS}h (erster Lauf)", file=sys.stderr)

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    }

    # Deutsche und englische Queries mit passendem RSS-Template
    all_queries = [(q, GNEWS_RSS_DE) for q in SEARCH_QUERIES_DE]
    all_queries += [(q, GNEWS_RSS_EN) for q in SEARCH_QUERIES_EN]

    for query, rss_template in all_queries:
        url = rss_template.format(query=quote_plus(query))
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            feed = feedparser.parse(resp.content)

            for entry in feed.entries:
                # Duplikat-Check (innerhalb dieses Laufs)
                title_clean, source = clean_google_title(entry.get("title", ""))
                if title_clean.lower() in seen_titles:
                    continue
                seen_titles.add(title_clean.lower())

                # Datum parsen
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6])

                # Zu alt?
                if published and published < cutoff:
                    continue

                # Zusammenfassung extrahieren
                summary = entry.get("summary", "")
                # HTML-Tags entfernen
                summary = re.sub(r"<[^>]+>", "", summary).strip()
                # Google News fügt oft die Quelle am Ende hinzu
                summary = re.sub(r"\s*-\s*[^-]+$", "", summary).strip()
                if len(summary) > 300:
                    summary = summary[:297] + "..."

                article = {
                    "title": title_clean,
                    "source": source,
                    "url": extract_real_url(entry.get("link", "")),
                    "summary": summary if summary else "Keine Zusammenfassung verfügbar.",
                    "published": published.isoformat() if published else None,
                    "published_display": published.strftime("%d.%m.%Y, %H:%M") if published else "Unbekannt",
                    "hash": article_hash(title_clean, source),
                    "query": query,
                }
                all_articles.append(article)

        except Exception as e:
            print(f"⚠️ Fehler bei Query '{query}': {e}", file=sys.stderr)
            continue

    # Nach Datum sortieren (neueste zuerst)
    all_articles.sort(
        key=lambda a: a["published"] or "0000",
        reverse=True,
    )

    return all_articles


def filter_new_articles(articles: list[dict], state: dict) -> list[dict]:
    """Filtere bereits gesehene Artikel heraus."""
    seen = set(state.get("seen_hashes", []))
    return [a for a in articles if a["hash"] not in seen]


def format_blog_html(articles: list[dict], date_str: str) -> str:
    """Erstelle das WordPress-HTML im Stil der Fake Defense AI Website."""

    article_cards = ""
    for i, article in enumerate(articles[:MAX_ARTICLES]):
        # Kategorie-Tag basierend auf Suchbegriff
        if "warnung" in article["query"].lower():
            tag = "WARNUNG"
            tag_color = "#ff4444"
        elif "polizei" in article["query"].lower():
            tag = "POLIZEI"
            tag_color = "#ff8800"
        elif "verbraucherschutz" in article["query"].lower():
            tag = "VERBRAUCHERSCHUTZ"
            tag_color = "#44bb44"
        elif "phishing" in article["query"].lower():
            tag = "PHISHING"
            tag_color = "#ff44ff"
        else:
            tag = "NEWS"
            tag_color = "#00b4d8"

        article_cards += f"""
    <a href="{article['url']}" target="_blank" rel="noopener noreferrer"
       style="display:block;background:#151a45;border-radius:12px;padding:24px;
              margin-bottom:16px;text-decoration:none;
              border-left:4px solid {tag_color};
              transition:transform 0.2s">
      <div style="display:flex;justify-content:space-between;align-items:center;
                  margin-bottom:8px;flex-wrap:wrap;gap:8px">
        <span style="background:{tag_color};color:#fff;padding:3px 10px;
                     border-radius:20px;font-size:11px;font-weight:bold;
                     letter-spacing:1px">{tag}</span>
        <span style="color:#8899cc;font-size:12px">{article['source']}</span>
      </div>
      <h3 style="color:#ffffff;margin:8px 0;font-size:18px;line-height:1.4">
        {article['title']}
      </h3>
      <p style="color:#8899cc;font-size:14px;line-height:1.6;margin:8px 0">
        {article['summary']}
      </p>
      <div style="display:flex;justify-content:space-between;align-items:center;
                  margin-top:12px">
        <span style="color:#8899cc;font-size:12px">
          📅 {article['published_display']}
        </span>
        <span style="color:#00b4d8;font-size:13px;font-weight:bold">
          Artikel lesen →
        </span>
      </div>
    </a>"""

    html = f"""<div style="font-family:'Segoe UI',system-ui,-apple-system,sans-serif;
              max-width:100%;margin:0;padding:0;background:#0d1137;color:#ffffff">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#0a0e27 0%,#1a1f4e 50%,#0d1137 100%);
              padding:50px 30px;text-align:center">
    <div style="font-size:40px;margin-bottom:12px">📰</div>
    <h1 style="color:#ffffff;font-size:28px;margin:0 0 10px 0;
               letter-spacing:1px">
      FAKE-SHOP NEWS RADAR
    </h1>
    <p style="color:#8899cc;font-size:16px;margin:0">
      Aktuelle Nachrichten über Online-Betrug &amp; Fake-Shops — {date_str}
    </p>
    <div style="width:60px;height:3px;background:#00b4d8;margin:20px auto 0"></div>
  </div>

  <!-- Intro -->
  <div style="background:#0d1137;padding:30px">
    <div style="background:rgba(0,180,216,0.1);border:1px solid rgba(0,180,216,0.3);
                border-radius:12px;padding:20px;margin-bottom:24px;text-align:center">
      <p style="color:#ffffff;margin:0;font-size:15px">
        🔍 <strong>{len(articles[:MAX_ARTICLES])} aktuelle Artikel</strong>
        aus deutschen und internationalen Nachrichtenquellen zum Thema Online-Betrug und Fake-Shops
      </p>
    </div>

    <!-- Articles -->
    {article_cards}
  </div>

  <!-- CTA -->
  <div style="background:linear-gradient(135deg,#0a0e27 0%,#151a45 100%);
              padding:40px 30px;text-align:center">
    <h2 style="color:#ffffff;font-size:22px;margin:0 0 12px 0">
      🛡 SCHÜTZE DICH JETZT
    </h2>
    <p style="color:#8899cc;font-size:14px;margin:0 0 20px 0">
      Mit Fake Defense AI bist du vor betrügerischen Online-Shops geschützt
    </p>
    <a href="https://play.google.com/store/apps/details?id=com.shopperprotection"
       target="_blank" rel="noopener noreferrer"
       style="display:inline-block;background:#00b4d8;color:#ffffff;
              padding:14px 32px;border-radius:30px;text-decoration:none;
              font-weight:bold;font-size:15px">
      📱 KOSTENLOS HERUNTERLADEN
    </a>
  </div>

  <!-- Footer -->
  <div style="background:#080b1f;padding:20px 30px;text-align:center">
    <p style="color:#8899cc;font-size:12px;margin:0">
      © 2026 Fake Defense AI. Automatisch generiert vom News Radar Agent.
    </p>
  </div>
</div>"""

    return html


def format_telegram_message(articles: list[dict], date_str: str) -> str:
    """Formatiere eine Telegram-Benachrichtigung über den neuen Blogpost."""
    msg = f"📰 *Fake-Shop News Radar – {date_str}*\n\n"
    msg += f"✅ Neuer Blogbeitrag erstellt mit {len(articles)} Artikeln:\n\n"

    for i, article in enumerate(articles[:MAX_ARTICLES], 1):
        msg += f"{i}. *{article['source']}*: {article['title'][:80]}\n"

    msg += "\n🔗 Wird auf fakedefenseai.wordpress.com veröffentlicht."
    return msg


def main():
    """Hauptfunktion des News Agents."""
    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv

    # --lookback N (Tage)
    lookback_hours = None
    if "--lookback" in sys.argv:
        idx = sys.argv.index("--lookback")
        if idx + 1 < len(sys.argv):
            lookback_hours = int(sys.argv[idx + 1]) * 24
            force = True  # lookback impliziert force

    state = load_state()
    today = datetime.now().strftime("%Y-%m-%d")

    # Prüfe ob heute schon gelaufen (außer bei --force)
    if not force and state.get("last_run") == today:
        result = {
            "status": "skipped",
            "reason": "Bereits heute gelaufen",
            "date": today,
        }
        print(json.dumps(result, ensure_ascii=False))
        return

    # News fetchen (Cutoff basiert auf letztem Lauf oder --lookback)
    print("🔍 Suche aktuelle Nachrichten...", file=sys.stderr)
    all_articles = fetch_news(state, lookback_hours=lookback_hours)
    print(f"📥 {len(all_articles)} Artikel gefunden", file=sys.stderr)

    # Neue Artikel filtern
    new_articles = filter_new_articles(all_articles, state)
    print(f"🆕 {len(new_articles)} neue Artikel", file=sys.stderr)

    if not new_articles:
        result = {
            "status": "no_news",
            "reason": "Keine neuen Artikel gefunden",
            "date": today,
            "total_fetched": len(all_articles),
        }
        print(json.dumps(result, ensure_ascii=False))
        return

    # HTML generieren
    date_display = datetime.now().strftime("%d. %B %Y").replace(
        "January", "Januar").replace("February", "Februar").replace(
        "March", "März").replace("April", "April").replace(
        "May", "Mai").replace("June", "Juni").replace(
        "July", "Juli").replace("August", "August").replace(
        "September", "September").replace("October", "Oktober").replace(
        "November", "November").replace("December", "Dezember")

    html = format_blog_html(new_articles, date_display)
    post_title = f"🔍 Fake-Shop News – {date_display}"

    telegram_msg = format_telegram_message(new_articles, date_display)

    # State aktualisieren (außer bei dry-run)
    if not dry_run:
        # Neue Hashes hinzufügen
        new_hashes = [a["hash"] for a in new_articles[:MAX_ARTICLES]]
        state["seen_hashes"] = list(set(state.get("seen_hashes", []) + new_hashes))
        # Nur die letzten 500 Hashes behalten
        state["seen_hashes"] = state["seen_hashes"][-500:]
        state["last_run"] = today
        state["last_run_timestamp"] = datetime.now().isoformat()
        state["total_posts_created"] = state.get("total_posts_created", 0) + 1
        save_state(state)

    # Ergebnis als JSON ausgeben
    result = {
        "status": "success",
        "date": today,
        "post_title": post_title,
        "article_count": len(new_articles[:MAX_ARTICLES]),
        "html": html,
        "telegram_message": telegram_msg,
        "articles": [
            {
                "title": a["title"],
                "source": a["source"],
                "url": a["url"],
                "published": a["published_display"],
            }
            for a in new_articles[:MAX_ARTICLES]
        ],
    }

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
