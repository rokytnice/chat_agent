#!/usr/bin/env python3
"""
Fake Defense AI – Reddit Poster
Postet News-Artikel auf Reddit via PRAW (Python Reddit API Wrapper).

Usage:
    echo '[articles]' | python -m lib.reddit_poster --batch
    python -m lib.reddit_poster --test
    python -m lib.reddit_poster "Titel" "https://url" --subreddit scams
"""

import json
import os
import sys
import time
from pathlib import Path

import praw
from dotenv import load_dotenv

# .env laden
load_dotenv(Path(__file__).parent.parent / ".env")

# Reddit API Credentials aus .env
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "FakeDefenseAI/1.0 by FakeDefenseAI")

# Standard-Subreddits zum Posten
DEFAULT_SUBREDDITS = [
    "FakeDefenseAI",  # Eigener Subreddit
]

# Zusätzliche Subreddits für Cross-Posting (mit Vorsicht, Regeln beachten!)
CROSSPOST_SUBREDDITS = [
    "scams",
    "onlineshopping",
]


def get_reddit() -> praw.Reddit:
    """Erstelle eine authentifizierte Reddit-Instanz."""
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD]):
        raise ValueError(
            "Reddit API Credentials fehlen! "
            "Bitte REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, "
            "REDDIT_USERNAME und REDDIT_PASSWORD in .env setzen."
        )

    return praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        username=REDDIT_USERNAME,
        password=REDDIT_PASSWORD,
        user_agent=REDDIT_USER_AGENT,
    )


def post_link(
    title: str,
    url: str,
    subreddit_name: str = None,
    flair: str = None,
) -> dict:
    """Poste einen Link-Post auf Reddit.

    Args:
        title: Post-Titel (max 300 Zeichen)
        url: Link-URL
        subreddit_name: Ziel-Subreddit (ohne r/)
        flair: Optional – Flair-Text

    Returns:
        dict mit success, post_id, post_url oder error
    """
    if not subreddit_name:
        subreddit_name = DEFAULT_SUBREDDITS[0]

    if len(title) > 300:
        title = title[:297] + "..."

    try:
        reddit = get_reddit()
        subreddit = reddit.subreddit(subreddit_name)

        submission = subreddit.submit(
            title=title,
            url=url,
            resubmit=False,  # Verhindert Duplikate
        )

        if flair:
            try:
                submission.mod.flair(text=flair)
            except Exception:
                pass  # Flair-Fehler ignorieren

        return {
            "success": True,
            "post_id": submission.id,
            "post_url": f"https://www.reddit.com{submission.permalink}",
            "subreddit": subreddit_name,
            "title": title,
        }

    except praw.exceptions.RedditAPIException as e:
        error_msg = str(e)
        # Rate-Limiting erkennen
        if "RATELIMIT" in error_msg.upper():
            return {
                "success": False,
                "error": f"Rate-Limit erreicht: {error_msg}",
                "subreddit": subreddit_name,
                "retry": True,
            }
        return {
            "success": False,
            "error": error_msg,
            "subreddit": subreddit_name,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "subreddit": subreddit_name,
        }


def post_text(
    title: str,
    body: str,
    subreddit_name: str = None,
    flair: str = None,
) -> dict:
    """Poste einen Text-Post (Self-Post) auf Reddit.

    Args:
        title: Post-Titel (max 300 Zeichen)
        body: Post-Text (Markdown)
        subreddit_name: Ziel-Subreddit (ohne r/)
        flair: Optional – Flair-Text

    Returns:
        dict mit success, post_id, post_url oder error
    """
    if not subreddit_name:
        subreddit_name = DEFAULT_SUBREDDITS[0]

    if len(title) > 300:
        title = title[:297] + "..."

    try:
        reddit = get_reddit()
        subreddit = reddit.subreddit(subreddit_name)

        submission = subreddit.submit(
            title=title,
            selftext=body,
        )

        if flair:
            try:
                submission.mod.flair(text=flair)
            except Exception:
                pass

        return {
            "success": True,
            "post_id": submission.id,
            "post_url": f"https://www.reddit.com{submission.permalink}",
            "subreddit": subreddit_name,
            "title": title,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "subreddit": subreddit_name,
        }


def format_reddit_post(articles: list[dict], date_str: str = "") -> tuple[str, str]:
    """Erstelle Titel und Body für einen Reddit-Sammelpost.

    Args:
        articles: Liste von Artikel-Dicts
        date_str: Datum-String für den Titel

    Returns:
        (title, body) Tuple
    """
    if not date_str:
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")

    title = f"Fake-Shop News Radar – {date_str} – {len(articles)} new warnings / neue Warnungen"

    # Reddit Markdown Body (zweisprachig)
    body = (
        f"# Fake-Shop News Radar – {date_str}\n\n"
        f"**{len(articles)} current articles on online fraud & fake shops**\n"
        f"*{len(articles)} aktuelle Artikel zu Online-Betrug & Fake-Shops*\n\n"
        "---\n\n"
    )

    for i, article in enumerate(articles, 1):
        source = article.get("source", "Unknown")
        title_text = article.get("title", "No title")
        url = article.get("url", "")
        summary = article.get("summary", "")
        published = article.get("published", article.get("published_display", ""))

        body += f"### {i}. {title_text}\n"
        body += f"**Source / Quelle:** {source}"
        if published:
            body += f" | {published}"
        body += "\n\n"

        if summary:
            body += f"> {summary}\n\n"

        if url:
            body += f"[Read article / Artikel lesen]({url})\n\n"

        body += "---\n\n"

    # Footer mit Copyright und CTA
    body += (
        "## Protect yourself / Schuetze dich\n\n"
        "[Fake Defense AI - Free Download](https://play.google.com/store/apps/details?id=com.shopperprotection)\n\n"
        "---\n\n"
        "*All articles are property of their respective authors and publishers. "
        "Used as citation/preview with links to the original source (Sec. 51 UrhG).*\n\n"
        "*Alle Artikel sind Eigentum der jeweiligen Autoren und Verlage. "
        "Verwendung als Zitat/Vorschau mit Verlinkung zur Originalquelle (§ 51 UrhG).*\n\n"
        "© 2026 Fake Defense AI | Automatically curated / Automatisch kuratiert\n"
    )

    return title, body


def post_article_batch(articles: list[dict], subreddits: list[str] = None) -> list[dict]:
    """Poste einen Sammelpost mit allen Artikeln auf Reddit.

    Args:
        articles: Liste von Artikel-Dicts mit 'title', 'source', 'url', 'summary'
        subreddits: Liste von Subreddits (ohne r/). Default: DEFAULT_SUBREDDITS

    Returns:
        Liste von Ergebnis-Dicts
    """
    if not subreddits:
        subreddits = DEFAULT_SUBREDDITS

    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")

    title, body = format_reddit_post(articles, date_str)
    results = []

    for sub in subreddits:
        print(f"📝 Poste auf r/{sub}...", file=sys.stderr)
        result = post_text(
            title=title,
            body=body,
            subreddit_name=sub,
            flair="News",
        )
        results.append(result)

        if result["success"]:
            print(f"✅ r/{sub}: {result['post_url']}", file=sys.stderr)
        else:
            print(f"❌ r/{sub}: {result['error']}", file=sys.stderr)

        # Pause zwischen Subreddits (Rate-Limiting)
        if len(subreddits) > 1:
            time.sleep(10)

    return results


def test_connection() -> dict:
    """Teste die Reddit API Verbindung."""
    try:
        reddit = get_reddit()
        user = reddit.user.me()
        return {
            "success": True,
            "username": user.name,
            "comment_karma": user.comment_karma,
            "link_karma": user.link_karma,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def main():
    if "--test" in sys.argv:
        result = test_connection()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if "--batch" in sys.argv:
        # Batch-Modus: JSON-Array von Artikeln von stdin lesen
        articles = json.loads(sys.stdin.read())

        # Optional: --subreddits sub1,sub2
        subreddits = None
        if "--subreddits" in sys.argv:
            idx = sys.argv.index("--subreddits")
            if idx + 1 < len(sys.argv):
                subreddits = sys.argv[idx + 1].split(",")

        results = post_article_batch(articles, subreddits=subreddits)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    # Einzelpost-Modus
    if len(sys.argv) < 3:
        print("Usage: python -m lib.reddit_poster \"Titel\" \"https://url\"", file=sys.stderr)
        print("       python -m lib.reddit_poster --test", file=sys.stderr)
        print("       echo '[articles]' | python -m lib.reddit_poster --batch", file=sys.stderr)
        sys.exit(1)

    title = sys.argv[1]
    url = sys.argv[2]

    subreddit = None
    if "--subreddit" in sys.argv:
        idx = sys.argv.index("--subreddit")
        if idx + 1 < len(sys.argv):
            subreddit = sys.argv[idx + 1]

    result = post_link(title, url, subreddit_name=subreddit)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
