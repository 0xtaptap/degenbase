"""
Twitter scraper using Twikit for DEGEN community tweets.
Scrapes $DEGEN mentions, team accounts, and community buzz.
"""

import os
import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TWITTER_USERNAME = os.getenv("TWITTER_USERNAME", "")
TWITTER_PASSWORD = os.getenv("TWITTER_PASSWORD", "")
TWITTER_EMAIL = os.getenv("TWITTER_EMAIL", "")

CACHE_FILE = Path(__file__).parent / "data" / "twitter_cache.json"
COOKIES_FILE = Path(__file__).parent / "data" / "twitter_cookies.json"
CACHE_TTL_SECONDS = 300  # 5 minutes

# Team accounts to track
TEAM_ACCOUNTS = ["degentokenbase", "BR4ted"]
SEARCH_KEYWORDS = ["$DEGEN", "Degen Dream", "degen NFT", "#DEGEN"]


def _load_cache() -> dict:
    """Load cached Twitter data."""
    try:
        if CACHE_FILE.exists():
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return {"pulse": [], "team": [], "last_updated": None}


def _save_cache(data: dict):
    """Save Twitter data to cache."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def _is_cache_fresh() -> bool:
    """Check if cache is still within TTL."""
    cache = _load_cache()
    last_updated = cache.get("last_updated")
    if not last_updated:
        return False
    try:
        updated_time = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - updated_time).total_seconds() < CACHE_TTL_SECONDS
    except (ValueError, TypeError):
        return False


async def _get_client():
    """Initialize and authenticate Twikit client."""
    try:
        from twikit import Client

        client = Client("en-US")

        # Try to load saved cookies first
        if COOKIES_FILE.exists():
            try:
                client.load_cookies(str(COOKIES_FILE))
                return client
            except Exception:
                pass

        # Login with credentials
        if TWITTER_USERNAME and TWITTER_PASSWORD:
            await client.login(
                auth_info_1=TWITTER_USERNAME,
                auth_info_2=TWITTER_EMAIL,
                password=TWITTER_PASSWORD
            )
            # Save cookies for next time
            COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
            client.save_cookies(str(COOKIES_FILE))
            return client
        else:
            return None
    except ImportError:
        print("[Twitter] Twikit not installed. Run: pip install twikit")
        return None
    except Exception as e:
        print(f"[Twitter] Auth failed: {e}")
        return None


def _tweet_to_dict(tweet) -> dict:
    """Convert a Twikit tweet object to a serializable dictionary."""
    try:
        user = tweet.user
        return {
            "id": str(tweet.id),
            "text": tweet.text or "",
            "username": user.screen_name if user else "unknown",
            "display_name": user.name if user else "Unknown",
            "profile_image": user.profile_image_url_https if user else "",
            "created_at": str(tweet.created_at) if tweet.created_at else "",
            "retweet_count": tweet.retweet_count or 0,
            "like_count": tweet.favorite_count or 0,
            "reply_count": tweet.reply_count or 0,
            "url": f"https://x.com/{user.screen_name}/status/{tweet.id}" if user else ""
        }
    except Exception as e:
        return {
            "id": "error",
            "text": f"Error parsing tweet: {str(e)}",
            "username": "unknown",
            "display_name": "Unknown",
            "profile_image": "",
            "created_at": "",
            "retweet_count": 0,
            "like_count": 0,
            "reply_count": 0,
            "url": ""
        }


async def scrape_degen_pulse(force_refresh: bool = False) -> list:
    """Scrape latest tweets mentioning DEGEN."""
    if not force_refresh and _is_cache_fresh():
        cache = _load_cache()
        return cache.get("pulse", [])

    client = await _get_client()
    if not client:
        return _get_fallback_pulse()

    tweets = []
    try:
        for keyword in SEARCH_KEYWORDS[:2]:  # Limit to first 2 keywords
            results = await client.search_tweet(keyword, product="Latest", count=10)
            for tweet in results:
                tweet_dict = _tweet_to_dict(tweet)
                if tweet_dict["id"] != "error":
                    tweets.append(tweet_dict)
    except Exception as e:
        print(f"[Twitter] Scrape pulse error: {e}")
        return _get_fallback_pulse()

    # Deduplicate by ID
    seen = set()
    unique_tweets = []
    for t in tweets:
        if t["id"] not in seen:
            seen.add(t["id"])
            unique_tweets.append(t)

    # Update cache
    cache = _load_cache()
    cache["pulse"] = unique_tweets[:20]
    cache["last_updated"] = datetime.now(timezone.utc).isoformat()
    _save_cache(cache)

    return unique_tweets[:20]


async def scrape_team_tweets(force_refresh: bool = False) -> list:
    """Scrape latest tweets from team accounts."""
    if not force_refresh and _is_cache_fresh():
        cache = _load_cache()
        return cache.get("team", [])

    client = await _get_client()
    if not client:
        return _get_fallback_team()

    team_tweets = []
    try:
        for account in TEAM_ACCOUNTS:
            try:
                user = await client.get_user_by_screen_name(account)
                if user:
                    user_tweets = await client.get_user_tweets(user.id, tweet_type="Tweets", count=5)
                    for tweet in user_tweets:
                        tweet_dict = _tweet_to_dict(tweet)
                        if tweet_dict["id"] != "error":
                            tweet_dict["team_member"] = True
                            team_tweets.append(tweet_dict)
            except Exception as e:
                print(f"[Twitter] Error fetching @{account}: {e}")
                continue
    except Exception as e:
        print(f"[Twitter] Scrape team error: {e}")
        return _get_fallback_team()

    # Update cache
    cache = _load_cache()
    cache["team"] = team_tweets[:15]
    cache["last_updated"] = datetime.now(timezone.utc).isoformat()
    _save_cache(cache)

    return team_tweets[:15]


def _get_fallback_pulse() -> list:
    """Return cached data or placeholder when scraping fails."""
    cache = _load_cache()
    if cache.get("pulse"):
        return cache["pulse"]
    return [{
        "id": "fallback",
        "text": "🎩 Connect your Twitter credentials in .env to see live $DEGEN pulse!",
        "username": "system",
        "display_name": "Degen Dream Hub",
        "profile_image": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "retweet_count": 0,
        "like_count": 0,
        "reply_count": 0,
        "url": "",
        "is_fallback": True
    }]


def _get_fallback_team() -> list:
    """Return cached team data or placeholder."""
    cache = _load_cache()
    if cache.get("team"):
        return cache["team"]
    return [{
        "id": "fallback-team",
        "text": "🎩 Add Twitter creds to .env to see @degentokenbase and @BR4ted latest posts!",
        "username": "system",
        "display_name": "Degen Dream Hub",
        "profile_image": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "retweet_count": 0,
        "like_count": 0,
        "reply_count": 0,
        "url": "",
        "team_member": True,
        "is_fallback": True
    }]
