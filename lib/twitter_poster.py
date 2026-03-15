#!/usr/bin/env python3
"""
Fake Defense AI – Twitter/X Poster
Postet Tweets über die X API v2 mit Tweepy.

Usage:
    python -m lib.twitter_poster "Tweet-Text hier"
    python -m lib.twitter_poster --test  # Testet die Verbindung
"""

import os
import sys
import tweepy
from pathlib import Path
from dotenv import load_dotenv

# .env laden
load_dotenv(Path(__file__).parent.parent / ".env")

# Twitter API Credentials aus .env
API_KEY = os.getenv("TWITTER_API_KEY")
API_SECRET = os.getenv("TWITTER_API_SECRET")
ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")


def get_client() -> tweepy.Client:
    """Erstelle einen authentifizierten Twitter/X API Client."""
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


def post_tweet(text: str) -> dict:
    """Poste einen Tweet und gib das Ergebnis zurück."""
    if len(text) > 280:
        print(f"⚠️ Tweet zu lang ({len(text)} Zeichen), wird gekürzt...", file=sys.stderr)
        text = text[:277] + "..."

    client = get_client()
    response = client.create_tweet(text=text)

    tweet_id = response.data["id"]
    tweet_url = f"https://x.com/FakeDefenseAI/status/{tweet_id}"

    return {
        "success": True,
        "tweet_id": tweet_id,
        "tweet_url": tweet_url,
        "text": text,
    }


def post_article_tweets(articles: list[dict], blog_url: str = "") -> list[dict]:
    """Poste einen Tweet pro Artikel. Gibt Liste der Ergebnisse zurück.

    articles: Liste von dicts mit 'title', 'source', 'url'
    blog_url: Optional – Link zum Gesamt-Blogpost
    """
    import time
    results = []
    client = get_client()

    for i, article in enumerate(articles):
        title = article.get("title", "")
        source = article.get("source", "")
        url = article.get("url", "")

        # Tweet-Text zusammenbauen
        # Format: Emoji + Titel (gekürzt) + Quelle + Link + Hashtag
        hashtags = "#FakeShop #OnlineBetrug"
        prefix = "⚠️"

        # Maximale Titellänge berechnen (280 - Rest)
        fixed_parts = f"{prefix}  ({source})\n\n🔗 \n\n🛡️ Schützt euch – z.B. mit der Fake Defense AI App\n{hashtags}"
        max_title_len = 280 - len(fixed_parts) - len(url) - 5

        if len(title) > max_title_len:
            title = title[:max_title_len - 3] + "..."

        tweet_text = f"{prefix} {title} ({source})\n\n🔗 {url}\n\n🛡️ Schützt euch – z.B. mit der Fake Defense AI App\n{hashtags}"

        # Sicherheits-Kürzung
        if len(tweet_text) > 280:
            tweet_text = tweet_text[:277] + "..."

        try:
            response = client.create_tweet(text=tweet_text)
            tweet_id = response.data["id"]
            result = {
                "success": True,
                "tweet_id": tweet_id,
                "tweet_url": f"https://x.com/FakeDefenseAI/status/{tweet_id}",
                "text": tweet_text,
                "article_index": i,
            }
            print(f"✅ Tweet {i+1}/{len(articles)}: {title[:50]}...", file=sys.stderr)
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
        # Format: [{"title": "...", "source": "...", "url": "..."}, ...]
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

    try:
        result = post_tweet(text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        error = {"success": False, "error": str(e)}
        print(json.dumps(error, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
