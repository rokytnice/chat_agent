#!/usr/bin/env python3
"""
Fake Defense AI – Video Radar Agent
Sucht täglich nach aktuellen YouTube-Videos über Fake-Shops, Online-Betrug
und Internetkriminalität und erstellt daraus einen WordPress-Blogbeitrag.

Usage:
    python -m lib.video_agent              # Normaler Lauf (JSON-Output)
    python -m lib.video_agent --dry-run    # Nur Vorschau, kein State-Update
    python -m lib.video_agent --force      # Auch wenn heute schon gelaufen
    python -m lib.video_agent --lookback 30  # Videos der letzten 30 Tage
"""

import json
import hashlib
import sys
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus, parse_qs, urlparse

import feedparser
import requests

# Pfade
BASE_DIR = Path(__file__).parent.parent
STATE_FILE = BASE_DIR / "data" / "video_seen.json"

# Suchbegriffe für YouTube-Videos via Google News RSS
SEARCH_QUERIES_DE = [
    "site:youtube.com Fake Shop Betrug",
    "site:youtube.com Online Betrug erkennen",
    "site:youtube.com Fakeshop Warnung",
    "site:youtube.com Internet Abzocke Schutz",
    "site:youtube.com Verbraucherschutz Online Shopping",
]

SEARCH_QUERIES_EN = [
    "site:youtube.com fake online shop scam",
    "site:youtube.com how to spot fake website scam",
    "site:youtube.com online shopping fraud warning",
    "site:youtube.com e-commerce scam protection",
]

# Google News RSS URL Templates
GNEWS_RSS_DE = "https://news.google.com/rss/search?q={query}&hl=de&gl=DE&ceid=DE:de"
GNEWS_RSS_EN = "https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en"

# YouTube Search RSS (alternative)
YT_SEARCH_RSS = "https://www.youtube.com/feeds/videos.xml?search_query={query}"

# Maximale Videos pro Blogpost
MAX_VIDEOS = 10

# Fallback: Videos nicht älter als X Stunden
DEFAULT_MAX_AGE_HOURS = 72  # 3 Tage, da Videos seltener sind als News


def load_state() -> dict:
    """Lade den State mit bereits gesehenen Videos."""
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


def video_hash(title: str, channel: str) -> str:
    """Erzeuge einen eindeutigen Hash für ein Video."""
    text = f"{title.strip().lower()}|{channel.strip().lower()}"
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def fix_mojibake(text: str) -> str:
    """Repariere doppelt-kodierte UTF-8 Texte (Mojibake)."""
    if not text:
        return text
    mojibake_markers = ['\u00c3\u00a4', '\u00c3\u00b6', '\u00c3\u00bc',
                        '\u00c3\u009f', '\u00c3\u009c', '\u00c3\u0084', '\u00c3\u0096']
    if any(m in text for m in mojibake_markers):
        try:
            return text.encode('latin-1').decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
    return text


def extract_youtube_id(url: str) -> str | None:
    """Extrahiere die YouTube Video-ID aus verschiedenen URL-Formaten."""
    if not url:
        return None

    # Standard: youtube.com/watch?v=XXXX
    parsed = urlparse(url)
    if 'youtube.com' in parsed.netloc:
        params = parse_qs(parsed.query)
        if 'v' in params:
            return params['v'][0]
        # youtube.com/embed/XXXX
        if '/embed/' in parsed.path:
            return parsed.path.split('/embed/')[1].split('/')[0].split('?')[0]
        # youtube.com/shorts/XXXX
        if '/shorts/' in parsed.path:
            return parsed.path.split('/shorts/')[1].split('/')[0].split('?')[0]

    # youtu.be/XXXX
    if 'youtu.be' in parsed.netloc:
        return parsed.path.strip('/').split('/')[0].split('?')[0]

    return None


def clean_video_title(title: str) -> tuple[str, str]:
    """Extrahiere Titel und Kanal/Quelle aus Google News Titel.
    Google News Format: 'Videotitel - Quellenname'
    """
    title = fix_mojibake(title)
    parts = title.rsplit(" - ", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return title.strip(), "YouTube"


def fetch_videos_gnews(state: dict, lookback_hours: int = None) -> list[dict]:
    """Hole Videos über Google News RSS mit site:youtube.com Filter."""
    all_videos = []
    seen_ids = set()

    # Cutoff berechnen
    if lookback_hours:
        cutoff = datetime.now() - timedelta(hours=lookback_hours)
        days = lookback_hours // 24
        print(f"\u23f1\ufe0f Cutoff: Letzte {days} Tage ({cutoff.strftime('%d.%m.%Y %H:%M')})", file=sys.stderr)
    else:
        last_run_ts = state.get("last_run_timestamp")
        if last_run_ts:
            try:
                cutoff = datetime.fromisoformat(last_run_ts)
                print(f"\u23f1\ufe0f Cutoff: Videos seit letztem Lauf ({cutoff.strftime('%d.%m.%Y %H:%M')})", file=sys.stderr)
            except (ValueError, TypeError):
                cutoff = datetime.now() - timedelta(hours=DEFAULT_MAX_AGE_HOURS)
        else:
            cutoff = datetime.now() - timedelta(hours=DEFAULT_MAX_AGE_HOURS)
            print(f"\u23f1\ufe0f Cutoff: Letzte {DEFAULT_MAX_AGE_HOURS}h (erster Lauf)", file=sys.stderr)

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    }

    # Deutsche und englische Queries
    all_queries = [(q, GNEWS_RSS_DE) for q in SEARCH_QUERIES_DE]
    all_queries += [(q, GNEWS_RSS_EN) for q in SEARCH_QUERIES_EN]

    for query, rss_template in all_queries:
        url = rss_template.format(query=quote_plus(query))
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.encoding = resp.apparent_encoding or "utf-8"
            feed = feedparser.parse(resp.text)

            for entry in feed.entries:
                entry_url = entry.get("link", "")

                # Nur YouTube-Links
                video_id = extract_youtube_id(entry_url)
                if not video_id:
                    # Manchmal verlinkt Google News auf Artikel ÜBER YouTube-Videos
                    continue

                # Duplikat-Check
                if video_id in seen_ids:
                    continue
                seen_ids.add(video_id)

                title_clean, channel = clean_video_title(entry.get("title", ""))

                # Datum parsen
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6])

                # Zu alt?
                if published and published < cutoff:
                    continue

                # Zusammenfassung
                summary = entry.get("summary", "")
                summary = re.sub(r"<[^>]+>", "", summary).strip()
                summary = fix_mojibake(summary)
                summary = re.sub(r"\s*-\s*[^-]+$", "", summary).strip()
                if len(summary) > 300:
                    summary = summary[:297] + "..."

                video = {
                    "title": title_clean,
                    "channel": channel,
                    "video_id": video_id,
                    "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
                    "embed_url": f"https://www.youtube.com/embed/{video_id}",
                    "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
                    "thumbnail_hq": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                    "summary": summary if summary else "Video zum Thema Online-Betrug und Fake-Shops.",
                    "published": published.isoformat() if published else None,
                    "published_display": published.strftime("%d.%m.%Y, %H:%M") if published else "Unbekannt",
                    "hash": video_hash(title_clean, channel),
                    "query": query,
                    "source": "google_news",
                }
                all_videos.append(video)

        except Exception as e:
            print(f"\u26a0\ufe0f Fehler bei Query '{query}': {e}", file=sys.stderr)
            continue

    return all_videos


def fetch_videos_youtube_rss(state: dict, lookback_hours: int = None) -> list[dict]:
    """Alternative: Suche direkt via YouTube RSS (weniger zuverlässig)."""
    all_videos = []
    seen_ids = set()

    cutoff = datetime.now() - timedelta(hours=lookback_hours or DEFAULT_MAX_AGE_HOURS)

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    }

    # Nur die YouTube-spezifischen Queries (ohne site:youtube.com)
    yt_queries = [
        "Fake Shop Betrug",
        "Online Betrug erkennen",
        "Fakeshop Warnung",
        "fake online shop scam",
        "how to spot fake website",
    ]

    for query in yt_queries:
        url = YT_SEARCH_RSS.format(query=quote_plus(query))
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.encoding = "utf-8"
            feed = feedparser.parse(resp.text)

            for entry in feed.entries:
                video_id = entry.get("yt_videoid", "")
                if not video_id:
                    video_id = extract_youtube_id(entry.get("link", ""))
                if not video_id or video_id in seen_ids:
                    continue
                seen_ids.add(video_id)

                title = fix_mojibake(entry.get("title", ""))
                channel = entry.get("author", "YouTube")

                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])

                if published and published < cutoff:
                    continue

                summary = entry.get("media_description", entry.get("summary", ""))
                summary = re.sub(r"<[^>]+>", "", summary).strip()
                summary = fix_mojibake(summary)
                if len(summary) > 300:
                    summary = summary[:297] + "..."

                video = {
                    "title": title,
                    "channel": channel,
                    "video_id": video_id,
                    "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
                    "embed_url": f"https://www.youtube.com/embed/{video_id}",
                    "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
                    "thumbnail_hq": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                    "summary": summary if summary else "Video zum Thema Online-Betrug.",
                    "published": published.isoformat() if published else None,
                    "published_display": published.strftime("%d.%m.%Y, %H:%M") if published else "Unbekannt",
                    "hash": video_hash(title, channel),
                    "query": query,
                    "source": "youtube_rss",
                }
                all_videos.append(video)

        except Exception as e:
            print(f"\u26a0\ufe0f YT-RSS Fehler bei '{query}': {e}", file=sys.stderr)
            continue

    return all_videos


def fetch_videos_youtube_search(state: dict) -> list[dict]:
    """Suche Videos direkt auf YouTube via HTML-Scraping der Suchergebnisse."""
    all_videos = []
    seen_ids = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    }

    yt_queries = [
        "fake shop betrug",
        "online betrug erkennen warnung",
        "fakeshop scam warnung deutsch",
        "fake online shop scam",
        "online shopping fraud how to spot",
    ]

    for query in yt_queries:
        url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.encoding = "utf-8"

            # Extract ytInitialData JSON
            match = re.search(r'var ytInitialData = ({.*?});</script>', resp.text)
            if not match:
                match = re.search(r'ytInitialData\s*=\s*({.*?});</script>', resp.text)
            if not match:
                continue

            data = json.loads(match.group(1))
            contents = (data.get("contents", {})
                       .get("twoColumnSearchResultsRenderer", {})
                       .get("primaryContents", {})
                       .get("sectionListRenderer", {})
                       .get("contents", []))

            for section in contents:
                items = section.get("itemSectionRenderer", {}).get("contents", [])
                for item in items:
                    vid = item.get("videoRenderer", {})
                    if not vid:
                        continue

                    video_id = vid.get("videoId", "")
                    if not video_id or video_id in seen_ids:
                        continue
                    seen_ids.add(video_id)

                    title = vid.get("title", {}).get("runs", [{}])[0].get("text", "")
                    title = fix_mojibake(title)
                    channel = vid.get("ownerText", {}).get("runs", [{}])[0].get("text", "YouTube")
                    views_text = vid.get("viewCountText", {}).get("simpleText", "")
                    published_text = vid.get("publishedTimeText", {}).get("simpleText", "")
                    length_text = vid.get("lengthText", {}).get("simpleText", "")

                    # Description snippet
                    desc = ""
                    for snip in vid.get("detailedMetadataSnippets", []):
                        for run in snip.get("snippetText", {}).get("runs", []):
                            desc += run.get("text", "")
                    if not desc:
                        for snip in vid.get("descriptionSnippet", {}).get("runs", []):
                            desc += snip.get("text", "")
                    desc = fix_mojibake(desc)
                    if len(desc) > 300:
                        desc = desc[:297] + "..."

                    video = {
                        "title": title,
                        "channel": channel,
                        "video_id": video_id,
                        "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
                        "embed_url": f"https://www.youtube.com/embed/{video_id}",
                        "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
                        "thumbnail_hq": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                        "summary": desc if desc else "Video zum Thema Online-Betrug und Fake-Shops.",
                        "published": None,
                        "published_display": published_text or "Unbekannt",
                        "views": views_text,
                        "length": length_text,
                        "hash": video_hash(title, channel),
                        "query": query,
                        "source": "youtube_search",
                    }
                    all_videos.append(video)

        except Exception as e:
            print(f"\u26a0\ufe0f YT-Search Fehler bei '{query}': {e}", file=sys.stderr)
            continue

    return all_videos


def fetch_videos(state: dict, lookback_hours: int = None) -> list[dict]:
    """Hole Videos aus allen Quellen und kombiniere sie."""
    all_videos = []
    seen_ids = set()

    # Quelle 1: YouTube Direct Search (Hauptquelle)
    yt_search_videos = fetch_videos_youtube_search(state)
    for v in yt_search_videos:
        if v["video_id"] not in seen_ids:
            all_videos.append(v)
            seen_ids.add(v["video_id"])
    print(f"\U0001f50d YouTube Search: {len(yt_search_videos)} Videos", file=sys.stderr)

    # Quelle 2: Google News RSS (site:youtube.com)
    gnews_videos = fetch_videos_gnews(state, lookback_hours)
    for v in gnews_videos:
        if v["video_id"] not in seen_ids:
            all_videos.append(v)
            seen_ids.add(v["video_id"])
    print(f"\U0001f4f0 Google News: {len(gnews_videos)} Videos", file=sys.stderr)

    # Quelle 3: YouTube RSS (Fallback)
    yt_videos = fetch_videos_youtube_rss(state, lookback_hours)
    for v in yt_videos:
        if v["video_id"] not in seen_ids:
            all_videos.append(v)
            seen_ids.add(v["video_id"])
    print(f"\U0001f3ac YouTube RSS: {len(yt_videos)} Videos", file=sys.stderr)

    return all_videos


def filter_new_videos(videos: list[dict], state: dict) -> list[dict]:
    """Filtere bereits gesehene Videos heraus."""
    seen = set(state.get("seen_hashes", []))
    return [v for v in videos if v["hash"] not in seen]


def download_thumbnail(video: dict) -> str | None:
    """Lade das YouTube-Thumbnail herunter für Instagram-Posts."""
    video_id = video["video_id"]
    filepath = f"/tmp/yt_thumb_{video_id}.jpg"

    if os.path.exists(filepath):
        return filepath

    # Versuche maxresdefault, dann hqdefault
    for url in [video["thumbnail_url"], video["thumbnail_hq"]]:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200 and len(resp.content) > 5000:
                with open(filepath, 'wb') as f:
                    f.write(resp.content)
                return filepath
        except Exception:
            continue

    return None


def format_blog_html(videos: list[dict], date_str: str) -> str:
    """Erstelle das WordPress-HTML mit eingebetteten YouTube-Videos."""

    video_cards = ""
    for i, video in enumerate(videos[:MAX_VIDEOS]):
        # Kategorie-Tag basierend auf Sprache
        is_english = not any(de_kw in video["query"].lower() for de_kw in ["betrug", "warnung", "abzocke", "verbraucherschutz", "deutsch"])
        if not is_english:
            tag = "DEUTSCH"
            tag_color = "#00b4d8"
        else:
            tag = "ENGLISH"
            tag_color = "#44bb44"

        watch_text = "Watch on YouTube" if is_english else "Auf YouTube ansehen"

        video_cards += f"""
    <div style="background:#151a45;border-radius:12px;padding:24px;
                margin-bottom:24px;border-left:4px solid {tag_color}">
      <div style="display:flex;justify-content:space-between;align-items:center;
                  margin-bottom:12px;flex-wrap:wrap;gap:8px">
        <span style="background:{tag_color};color:#fff;padding:3px 10px;
                     border-radius:20px;font-size:11px;font-weight:bold;
                     letter-spacing:1px">{tag}</span>
        <span style="color:#8899cc;font-size:12px">&copy; {video['channel']}</span>
      </div>
      <h3 style="color:#ffffff;margin:8px 0;font-size:18px;line-height:1.4">
        {video['title']}
      </h3>
      <div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;
                  border-radius:8px;margin:16px 0">
        <iframe src="{video['embed_url']}" frameborder="0"
                allow="accelerometer;autoplay;clipboard-write;encrypted-media;gyroscope;picture-in-picture"
                allowfullscreen
                style="position:absolute;top:0;left:0;width:100%;height:100%;border-radius:8px">
        </iframe>
      </div>
      <p style="color:#8899cc;font-size:14px;line-height:1.6;margin:8px 0">
        {video['summary']}
      </p>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px">
        <span style="color:#8899cc;font-size:12px">
          {video['published_display']}
        </span>
        <a href="{video['youtube_url']}" target="_blank" rel="noopener noreferrer"
           style="color:#ff0000;font-size:13px;font-weight:bold;text-decoration:none">
          &#9654; {watch_text}
        </a>
      </div>
    </div>"""

    html = f"""<div style="font-family:'Segoe UI',system-ui,-apple-system,sans-serif;
              max-width:100%;margin:0;padding:0;background:#0d1137;color:#ffffff">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#0a0e27 0%,#1a1f4e 50%,#0d1137 100%);
              padding:50px 30px;text-align:center">
    <div style="font-size:40px;margin-bottom:12px;color:#00b4d8">&#9654;</div>
    <h1 style="color:#ffffff;font-size:28px;margin:0 0 10px 0;
               letter-spacing:1px">
      VIDEO RADAR
    </h1>
    <p style="color:#8899cc;font-size:16px;margin:0">
      Aktuelle Videos / Latest Videos &mdash; Online-Betrug &amp; Fake-Shops &mdash; {date_str}
    </p>
    <div style="width:60px;height:3px;background:#00b4d8;margin:20px auto 0"></div>
  </div>

  <!-- Intro -->
  <div style="background:#0d1137;padding:30px">
    <div style="background:rgba(0,180,216,0.1);border:1px solid rgba(0,180,216,0.3);
                border-radius:12px;padding:20px;margin-bottom:24px;text-align:center">
      <p style="color:#ffffff;margin:0;font-size:15px">
        <strong>{len(videos[:MAX_VIDEOS])} aktuelle Videos / current videos</strong>
        <br>Zum Thema Online-Betrug, Fake-Shops und Verbraucherschutz.
        <br><span style="color:#8899cc">On online fraud, fake shops and consumer protection.</span>
      </p>
    </div>

    <!-- Videos -->
    {video_cards}
  </div>

  <!-- CTA -->
  <div style="background:linear-gradient(135deg,#0a0e27 0%,#151a45 100%);
              padding:40px 30px;text-align:center">
    <h2 style="color:#ffffff;font-size:22px;margin:0 0 6px 0">
      SCH&Uuml;TZE DICH JETZT
    </h2>
    <p style="color:#667799;font-size:13px;margin:0 0 12px 0;font-style:italic">
      PROTECT YOURSELF NOW
    </p>
    <p style="color:#8899cc;font-size:14px;margin:0 0 8px 0">
      Mit Fake Defense AI bist du vor betr&uuml;gerischen Online-Shops gesch&uuml;tzt.
    </p>
    <p style="color:#667799;font-size:13px;margin:0 0 20px 0">
      Fake Defense AI protects you from fraudulent online shops.
    </p>
    <a href="https://play.google.com/store/apps/details?id=com.shopperprotection"
       target="_blank" rel="noopener noreferrer"
       style="display:inline-block;background:#00b4d8;color:#ffffff;
              padding:14px 32px;border-radius:30px;text-decoration:none;
              font-weight:bold;font-size:15px">
      FREE DOWNLOAD / KOSTENLOS
    </a>
  </div>

  <!-- Copyright & Disclaimer -->
  <div style="background:#080b1f;padding:20px 30px;text-align:center">
    <p style="color:#667799;font-size:11px;margin:0 0 4px 0;line-height:1.6">
      Alle Videos sind Eigentum der jeweiligen Ersteller und YouTube-Kan&auml;le.
      Die Einbettung erfolgt &uuml;ber die offizielle YouTube-Embed-API gem&auml;&szlig; den YouTube-Nutzungsbedingungen.
    </p>
    <p style="color:#556688;font-size:10px;margin:0 0 8px 0;line-height:1.6">
      All videos are property of their respective creators and YouTube channels.
      Embedded via the official YouTube Embed API in accordance with YouTube Terms of Service.
    </p>
    <p style="color:#8899cc;font-size:12px;margin:0">
      &copy; 2026 Fake Defense AI. Automatically curated / Automatisch kuratiert.
    </p>
  </div>
</div>"""

    return html


def format_telegram_message(videos: list[dict], date_str: str) -> str:
    """Formatiere eine Telegram-Benachrichtigung."""
    msg = f"\U0001f3ac *Video Radar \u2013 {date_str}*\n\n"
    msg += f"\u2705 Neuer Blogbeitrag erstellt mit {len(videos)} Videos:\n\n"

    for i, video in enumerate(videos[:MAX_VIDEOS], 1):
        msg += f"{i}. *{video['channel']}*: {video['title'][:80]}\n"
        msg += f"   \U0001f517 {video['youtube_url']}\n"

    msg += "\n\U0001f517 Wird auf fakedefenseai.wordpress.com ver\u00f6ffentlicht."
    return msg


def main():
    """Hauptfunktion des Video Agents."""
    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv

    # --lookback N (Tage)
    lookback_hours = None
    if "--lookback" in sys.argv:
        idx = sys.argv.index("--lookback")
        if idx + 1 < len(sys.argv):
            lookback_hours = int(sys.argv[idx + 1]) * 24
            force = True

    state = load_state()
    today = datetime.now().strftime("%Y-%m-%d")

    # Pr\u00fcfe ob heute schon gelaufen
    if not force and state.get("last_run") == today:
        result = {
            "status": "skipped",
            "reason": "Bereits heute gelaufen",
            "date": today,
        }
        print(json.dumps(result, ensure_ascii=False))
        return

    # Videos fetchen
    print("\U0001f3ac Suche aktuelle Videos...", file=sys.stderr)
    all_videos = fetch_videos(state, lookback_hours=lookback_hours)
    print(f"\U0001f4e5 {len(all_videos)} Videos gefunden", file=sys.stderr)

    # Neue Videos filtern
    new_videos = filter_new_videos(all_videos, state)
    print(f"\U0001f195 {len(new_videos)} neue Videos", file=sys.stderr)

    if not new_videos:
        result = {
            "status": "no_videos",
            "reason": "Keine neuen Videos gefunden",
            "date": today,
            "total_fetched": len(all_videos),
        }
        print(json.dumps(result, ensure_ascii=False))
        return

    # Thumbnails herunterladen
    for video in new_videos[:MAX_VIDEOS]:
        thumb_path = download_thumbnail(video)
        video["thumbnail_local"] = thumb_path
        if thumb_path:
            print(f"\U0001f5bc Thumbnail: {video['video_id']}", file=sys.stderr)

    # HTML generieren
    date_display = datetime.now().strftime("%d. %B %Y").replace(
        "January", "Januar").replace("February", "Februar").replace(
        "March", "M\u00e4rz").replace("May", "Mai").replace(
        "June", "Juni").replace("July", "Juli").replace(
        "October", "Oktober").replace("December", "Dezember")

    html = format_blog_html(new_videos, date_display)
    post_title = f"Video Radar \u2013 {date_display}"

    telegram_msg = format_telegram_message(new_videos, date_display)

    # State aktualisieren
    if not dry_run:
        new_hashes = [v["hash"] for v in new_videos[:MAX_VIDEOS]]
        state["seen_hashes"] = list(set(state.get("seen_hashes", []) + new_hashes))
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
        "video_count": len(new_videos[:MAX_VIDEOS]),
        "html": html,
        "telegram_message": telegram_msg,
        "videos": [
            {
                "title": v["title"],
                "channel": v["channel"],
                "video_id": v["video_id"],
                "youtube_url": v["youtube_url"],
                "embed_url": v["embed_url"],
                "thumbnail_url": v["thumbnail_hq"],
                "thumbnail_local": v.get("thumbnail_local"),
                "published": v["published_display"],
                "source": v.get("source", "unknown"),
            }
            for v in new_videos[:MAX_VIDEOS]
        ],
    }

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
