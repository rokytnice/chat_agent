#!/usr/bin/env python3
"""
Fake Defense AI – Twitter/X Poster
Postet Tweets über die X API v2 mit Tweepy, optional mit Bildern.

Usage:
    python -m lib.twitter_poster "Tweet-Text hier"
    python -m lib.twitter_poster --test  # Testet die Verbindung
    echo '[articles]' | python -m lib.twitter_poster --batch
"""

import os
import re
import sys
import requests
import tweepy
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import urlparse

# .env laden
load_dotenv(Path(__file__).parent.parent / ".env")

# Twitter API Credentials aus .env
API_KEY = os.getenv("TWITTER_API_KEY")
API_SECRET = os.getenv("TWITTER_API_SECRET")
ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")

# Fallback-Logo für Tweets ohne eigenes Bild
LOGO_PATH = Path("/home/aroc/projects/ShopperProtection/backend/src/main/resources/static/images/logo.png")
LOGO_HQ_PATH = Path("/home/aroc/projects/ShopperProtection/design/logo.jpg")


def get_client() -> tweepy.Client:
    """Erstelle einen authentifizierten Twitter/X API v2 Client."""
    if not all([API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET]):
        raise ValueError(
            "Twitter API Credentials fehlen! "
            "Bitte TWITTER_API_KEY, TWITTER_API_SECRET, "
            "TWITTER_ACCESS_TOKEN und TWITTER_ACCESS_TOKEN_SECRET in .env setzen."
        )

    return tweepy.Client(
        consumer_key=API_KEY,
        consumer_secret=API_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_TOKEN_SECRET,
    )


def get_api_v1() -> tweepy.API:
    """Erstelle einen Tweepy v1.1 API Client (nötig für Media-Upload)."""
    if not all([API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET]):
        raise ValueError("Twitter API Credentials fehlen!")

    auth = tweepy.OAuth1UserHandler(
        API_KEY, API_SECRET,
        ACCESS_TOKEN, ACCESS_TOKEN_SECRET,
    )
    return tweepy.API(auth)


def upload_media(image_path: str) -> int | None:
    """Lade ein Bild auf Twitter hoch und gib die media_id zurück.

    Args:
        image_path: Pfad zum Bild (JPG, PNG)

    Returns:
        media_id (int) oder None bei Fehler
    """
    if not image_path or not os.path.exists(image_path):
        print(f"⚠️ Bilddatei nicht gefunden: {image_path}", file=sys.stderr)
        return None

    # Dateigröße prüfen (max 5MB für Bilder auf Twitter)
    file_size = os.path.getsize(image_path)
    if file_size > 5 * 1024 * 1024:
        print(f"⚠️ Bild zu groß ({file_size / 1024 / 1024:.1f}MB > 5MB): {image_path}", file=sys.stderr)
        return None

    if file_size < 1000:
        print(f"⚠️ Bild zu klein ({file_size} bytes), vermutlich fehlerhaft: {image_path}", file=sys.stderr)
        return None

    try:
        api = get_api_v1()
        media = api.media_upload(filename=image_path)
        print(f"📸 Bild hochgeladen: media_id={media.media_id}", file=sys.stderr)
        return media.media_id
    except Exception as e:
        print(f"❌ Media-Upload fehlgeschlagen: {e}", file=sys.stderr)
        return None


def download_article_image(url: str, index: int = 0) -> str | None:
    """Lade das OG-Image eines Artikels herunter.

    Versucht das Open Graph Image (og:image) der Artikel-URL zu extrahieren
    und herunterzuladen.

    Args:
        url: URL des Artikels
        index: Index für eindeutigen Dateinamen

    Returns:
        Pfad zur heruntergeladenen Bilddatei oder None
    """
    if not url:
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        resp.raise_for_status()

        # OG-Image aus HTML extrahieren
        og_patterns = [
            r'<meta\s+property=["\']og:image["\']\s+content=["\'](.*?)["\']',
            r'<meta\s+content=["\'](.*?)["\']\s+property=["\']og:image["\']',
            r'<meta\s+name=["\']twitter:image["\']\s+content=["\'](.*?)["\']',
            r'<meta\s+content=["\'](.*?)["\']\s+name=["\']twitter:image["\']',
        ]

        image_url = None
        for pattern in og_patterns:
            match = re.search(pattern, resp.text, re.IGNORECASE)
            if match:
                image_url = match.group(1)
                break

        if not image_url:
            print(f"⚠️ Kein OG-Image gefunden für: {url[:60]}", file=sys.stderr)
            return None

        # Relative URLs auflösen
        if image_url.startswith("//"):
            image_url = "https:" + image_url
        elif image_url.startswith("/"):
            parsed = urlparse(url)
            image_url = f"{parsed.scheme}://{parsed.netloc}{image_url}"

        # Bild herunterladen
        img_resp = requests.get(image_url, headers=headers, timeout=10)
        if img_resp.status_code != 200 or len(img_resp.content) < 5000:
            print(f"⚠️ OG-Image Download fehlgeschlagen: {image_url[:60]}", file=sys.stderr)
            return None

        # Dateiendung bestimmen
        content_type = img_resp.headers.get("Content-Type", "")
        ext = ".jpg"
        if "png" in content_type:
            ext = ".png"
        elif "webp" in content_type:
            ext = ".webp"

        filepath = f"/tmp/tweet_img_{index}{ext}"
        with open(filepath, "wb") as f:
            f.write(img_resp.content)

        print(f"🖼 OG-Image heruntergeladen: {filepath} ({len(img_resp.content) / 1024:.0f}KB)", file=sys.stderr)
        return filepath

    except Exception as e:
        print(f"⚠️ Fehler beim OG-Image Download: {e}", file=sys.stderr)
        return None


def get_youtube_thumbnail(video_id: str) -> str | None:
    """Lade ein YouTube-Thumbnail herunter.

    Args:
        video_id: YouTube Video-ID

    Returns:
        Pfad zur heruntergeladenen Bilddatei oder None
    """
    if not video_id:
        return None

    filepath = f"/tmp/yt_thumb_{video_id}.jpg"

    # Bereits vorhanden?
    if os.path.exists(filepath) and os.path.getsize(filepath) > 5000:
        return filepath

    # Versuche verschiedene Thumbnail-Qualitäten
    for quality in ["maxresdefault", "hqdefault", "mqdefault"]:
        url = f"https://img.youtube.com/vi/{video_id}/{quality}.jpg"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200 and len(resp.content) > 5000:
                with open(filepath, "wb") as f:
                    f.write(resp.content)
                print(f"🖼 YT-Thumbnail heruntergeladen: {video_id} ({quality})", file=sys.stderr)
                return filepath
        except Exception:
            continue

    return None


def get_fallback_logo() -> str | None:
    """Gibt den Pfad zum Fallback-Logo zurück."""
    if LOGO_HQ_PATH.exists():
        return str(LOGO_HQ_PATH)
    if LOGO_PATH.exists():
        return str(LOGO_PATH)
    return None


def post_tweet(text: str, image_path: str = None) -> dict:
    """Poste einen Tweet, optional mit Bild.

    Args:
        text: Tweet-Text (max 280 Zeichen)
        image_path: Optional - Pfad zum Bild
    """
    if len(text) > 280:
        print(f"⚠️ Tweet zu lang ({len(text)} Zeichen), wird gekürzt...", file=sys.stderr)
        text = text[:277] + "..."

    client = get_client()

    # Bild hochladen wenn vorhanden
    media_ids = None
    if image_path:
        media_id = upload_media(image_path)
        if media_id:
            media_ids = [media_id]

    response = client.create_tweet(text=text, media_ids=media_ids)

    tweet_id = response.data["id"]
    tweet_url = f"https://x.com/fake_defense_ai/status/{tweet_id}"

    return {
        "success": True,
        "tweet_id": tweet_id,
        "tweet_url": tweet_url,
        "text": text,
        "has_image": media_ids is not None,
    }


def post_article_tweets(articles: list[dict], blog_url: str = "") -> list[dict]:
    """Poste einen Tweet pro Artikel mit Bild. Gibt Liste der Ergebnisse zurück.

    articles: Liste von dicts mit 'title', 'source', 'url'
              Optional: 'image_path' (lokaler Bildpfad),
                        'video_id' (YouTube Video-ID für Thumbnail),
                        'thumbnail_local' (bereits heruntergeladenes Thumbnail)
    blog_url: Optional – Link zum Gesamt-Blogpost
    """
    import time
    results = []
    client = get_client()

    for i, article in enumerate(articles):
        title = article.get("title", "")
        source = article.get("source", "")
        url = article.get("url", "")

        # === Bild ermitteln (Priorität) ===
        image_path = None

        # 1. Explizit mitgegebenes Bild
        if article.get("image_path") and os.path.exists(article["image_path"]):
            image_path = article["image_path"]
            print(f"📸 Verwende mitgegebenes Bild: {image_path}", file=sys.stderr)

        # 2. Bereits heruntergeladenes Thumbnail (vom Video-Agent)
        elif article.get("thumbnail_local") and os.path.exists(article["thumbnail_local"]):
            image_path = article["thumbnail_local"]
            print(f"📸 Verwende lokales Thumbnail: {image_path}", file=sys.stderr)

        # 3. YouTube Video-ID → Thumbnail herunterladen
        elif article.get("video_id"):
            image_path = get_youtube_thumbnail(article["video_id"])

        # 4. OG-Image von der Artikel-URL herunterladen
        elif url and "youtube.com" in url:
            # YouTube-URL → Video-ID extrahieren und Thumbnail holen
            from urllib.parse import parse_qs, urlparse as _urlparse
            parsed = _urlparse(url)
            params = parse_qs(parsed.query)
            vid = params.get("v", [None])[0]
            if vid:
                image_path = get_youtube_thumbnail(vid)
        elif url:
            image_path = download_article_image(url, index=i)

        # 5. Fallback: Logo verwenden
        if not image_path:
            image_path = get_fallback_logo()
            if image_path:
                print(f"📸 Verwende Fallback-Logo: {image_path}", file=sys.stderr)

        # === Bild hochladen ===
        media_ids = None
        if image_path:
            media_id = upload_media(image_path)
            if media_id:
                media_ids = [media_id]

        # === Tweet-Text zusammenbauen (zweisprachig EN/DE) ===
        hashtags = "#FakeShop #OnlineScam #FakeDefenseAI"
        prefix = "⚠️"

        # CTA zweisprachig (kurz, passt in 280 Zeichen)
        cta = "Protect yourself / Schützt euch – Fake Defense AI"

        # Maximale Titellänge berechnen (280 - Rest)
        fixed_parts = f"{prefix}  ({source})\n\n🔗 \n\n🛡️ {cta}\n{hashtags}"
        max_title_len = 280 - len(fixed_parts) - len(url) - 5

        if len(title) > max_title_len:
            title = title[:max_title_len - 3] + "..."

        tweet_text = f"{prefix} {title} ({source})\n\n🔗 {url}\n\n🛡️ {cta}\n{hashtags}"

        # Sicherheits-Kürzung
        if len(tweet_text) > 280:
            tweet_text = tweet_text[:277] + "..."

        try:
            response = client.create_tweet(text=tweet_text, media_ids=media_ids)
            tweet_id = response.data["id"]
            result = {
                "success": True,
                "tweet_id": tweet_id,
                "tweet_url": f"https://x.com/fake_defense_ai/status/{tweet_id}",
                "text": tweet_text,
                "article_index": i,
                "has_image": media_ids is not None,
            }
            img_tag = " 📸" if media_ids else ""
            print(f"✅ Tweet {i+1}/{len(articles)}{img_tag}: {title[:50]}...", file=sys.stderr)
        except Exception as e:
            result = {
                "success": False,
                "error": str(e),
                "article_index": i,
                "title": title,
            }
            print(f"❌ Tweet {i+1}/{len(articles)} fehlgeschlagen: {e}", file=sys.stderr)

        results.append(result)

        # 5 Sekunden Pause zwischen Tweets (Rate-Limiting)
        if i < len(articles) - 1:
            time.sleep(5)

    return results


def test_connection() -> dict:
    """Teste die Twitter API Verbindung."""
    try:
        client = get_client()
        me = client.get_me()
        return {
            "success": True,
            "username": me.data.username,
            "name": me.data.name,
            "id": me.data.id,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def main():
    import json

    if "--test" in sys.argv:
        result = test_connection()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if "--batch" in sys.argv:
        # Batch-Modus: JSON-Array von Artikeln von stdin lesen
        # Format: [{"title": "...", "source": "...", "url": "...", "image_path": "...", "video_id": "..."}, ...]
        # Optional: --blog-url URL
        blog_url = ""
        if "--blog-url" in sys.argv:
            idx = sys.argv.index("--blog-url")
            if idx + 1 < len(sys.argv):
                blog_url = sys.argv[idx + 1]

        articles = json.loads(sys.stdin.read())
        results = post_article_tweets(articles, blog_url=blog_url)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    if len(sys.argv) < 2:
        print("Usage: python -m lib.twitter_poster \"Tweet-Text\"", file=sys.stderr)
        print("       python -m lib.twitter_poster --test", file=sys.stderr)
        print("       echo '[articles]' | python -m lib.twitter_poster --batch", file=sys.stderr)
        sys.exit(1)

    text = sys.argv[1]

    # Optional: --image PFAD
    image_path = None
    if "--image" in sys.argv:
        idx = sys.argv.index("--image")
        if idx + 1 < len(sys.argv):
            image_path = sys.argv[idx + 1]

    try:
        result = post_tweet(text, image_path=image_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        error = {"success": False, "error": str(e)}
        print(json.dumps(error, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
