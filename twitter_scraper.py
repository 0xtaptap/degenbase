"""
Twitter scraper using Twikit for DEGEN community tweets.
Based on: https://github.com/d60/twikit

Auth pattern: tries login() with cookies_file first,
falls back to set_cookies() from raw JSON if login fails.
"""

import os
import json
import asyncio
import random
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TWITTER_USERNAME = os.getenv("TWITTER_USERNAME", "")
TWITTER_PASSWORD = os.getenv("TWITTER_PASSWORD", "")
TWITTER_EMAIL = os.getenv("TWITTER_EMAIL", "")

DATA_DIR = Path(__file__).parent / "data"
CACHE_FILE = DATA_DIR / "twitter_cache.json"
COOKIES_FILE = DATA_DIR / "twitter_cookies.json"
CACHE_TTL_SECONDS = 600  # 10 min

# Team accounts to track (configurable via .env)
TEAM_ACCOUNTS = [x.strip() for x in os.getenv("DEGEN_TEAM_ACCOUNTS", "degentokenbase,BR4ted").split(",") if x.strip()]
SEARCH_KEYWORDS = [x.strip() for x in os.getenv("DEGEN_SEARCH_KEYWORDS", "$DEGEN,Degen Dream,#DEGEN").split(",") if x.strip()]

# Singleton client
_client = None
_initialized = False
_disabled = False


def _load_cache() -> dict:
    try:
        if CACHE_FILE.exists():
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return {"pulse": [], "team": [], "last_updated": None}


def _save_cache(data: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def _is_cache_fresh() -> bool:
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


def _normalise_cookie_file():
    """Normalise cookie file from list format to dict format if needed."""
    try:
        with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        if isinstance(raw, list):
            cookie_dict = {c['name']: c['value'] for c in raw if 'name' in c}
            with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
                json.dump(cookie_dict, f)
            print("[Twitter] Normalised cookie file format")
    except Exception:
        pass


async def _get_client():
    """
    Initialize twikit client.
    Pattern from working finch codebase:
      1. If no cookies file, write from TWITTER_COOKIES env var
      2. Load cookies via set_cookies() (bypasses Cloudflare)
      3. Fallback: login() with credentials
    """
    global _client, _initialized, _disabled

    if _initialized and _client:
        return _client

    if _disabled:
        return None

    try:
        from twikit import Client
    except ImportError:
        print("[Twitter] twikit not installed — run: pip install twikit")
        _disabled = True
        return None

    # If no cookies file, try writing from TWITTER_COOKIES env var (Railway pattern)
    if not COOKIES_FILE.exists():
        env_cookies = os.environ.get("TWITTER_COOKIES", "")
        if env_cookies:
            try:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
                    f.write(env_cookies)
                print("[Twitter] Wrote cookies from TWITTER_COOKIES env var")
            except Exception as e:
                print(f"[Twitter] Failed to write cookies from env: {e}")

    has_cookies = COOKIES_FILE.exists()
    has_creds = bool(TWITTER_USERNAME and TWITTER_PASSWORD)

    if not has_cookies and not has_creds:
        print("[Twitter] No cookies and no credentials — scraper disabled")
        _disabled = True
        return None

    try:
        client = Client('en-US')

        # Step 1: Load cookies via set_cookies() (no login flow = no Cloudflare)
        if has_cookies:
            try:
                _normalise_cookie_file()
                with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
                    raw = json.load(f)

                if isinstance(raw, dict):
                    client.set_cookies(raw)
                elif isinstance(raw, list):
                    cookie_dict = {c['name']: c['value'] for c in raw if 'name' in c}
                    client.set_cookies(cookie_dict)

                _client = client
                _initialized = True
                print("[Twitter] ✓ Client ready via set_cookies()")
                return client
            except Exception as cookie_err:
                short_err = str(cookie_err)[:150]
                print(f"[Twitter] set_cookies() failed: {short_err} — trying login()")

        # Step 2: Fallback — login() with credentials
        if has_creds:
            try:
                await client.login(
                    auth_info_1=TWITTER_USERNAME,
                    auth_info_2=TWITTER_EMAIL or None,
                    password=TWITTER_PASSWORD,
                    cookies_file=str(COOKIES_FILE),
                )
                _client = client
                _initialized = True
                print("[Twitter] ✓ Client ready via login()")
                return client
            except Exception as login_err:
                short_err = str(login_err)[:150]
                print(f"[Twitter] login() failed: {short_err}")

        print("[Twitter] All auth methods failed — scraper disabled")
        _disabled = True
        return None

    except Exception as e:
        short_err = str(e)[:150]
        print(f"[Twitter] Init failed: {short_err}")
        _disabled = True
        return None



def _tweet_to_dict(tweet) -> dict | None:
    """Convert Twikit tweet object to dict."""
    try:
        user = tweet.user
        return {
            "id": str(tweet.id),
            "text": tweet.text or "",
            "username": getattr(user, 'screen_name', 'unknown') if user else "unknown",
            "display_name": getattr(user, 'name', 'Unknown') if user else "Unknown",
            "profile_image": getattr(user, 'profile_image_url_https', '') if user else "",
            "created_at": str(tweet.created_at) if tweet.created_at else "",
            "retweet_count": getattr(tweet, 'retweet_count', 0) or 0,
            "like_count": getattr(tweet, 'favorite_count', 0) or 0,
            "reply_count": getattr(tweet, 'reply_count', 0) or 0,
            "url": f"https://x.com/{user.screen_name}/status/{tweet.id}" if user else ""
        }
    except Exception:
        return None


async def _human_delay():
    """Random delay between calls to avoid rate limits."""
    await asyncio.sleep(random.uniform(1.0, 3.0))


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
        for keyword in SEARCH_KEYWORDS:
            results = await client.search_tweet(keyword, 'Latest', count=20)
            for tweet in results:
                td = _tweet_to_dict(tweet)
                if td:
                    tweets.append(td)
            await _human_delay()
    except Exception as e:
        _log_error("pulse search", e)
        return _get_fallback_pulse()

    # Deduplicate
    seen = set()
    unique = []
    for t in tweets:
        if t["id"] not in seen:
            seen.add(t["id"])
            unique.append(t)

    # Update cache
    cache = _load_cache()
    cache["pulse"] = unique[:20]
    cache["last_updated"] = datetime.now(timezone.utc).isoformat()
    _save_cache(cache)

    return unique[:20]


async def scrape_team_tweets(force_refresh: bool = False) -> list:
    """Scrape latest tweets from team accounts."""
    if not force_refresh and _is_cache_fresh():
        cache = _load_cache()
        return cache.get("team", [])

    client = await _get_client()
    if not client:
        return _get_fallback_team()

    team_tweets = []
    for account in TEAM_ACCOUNTS:
        try:
            # Resolve handle → user → tweets (same pattern as working code)
            user = await client.get_user_by_screen_name(account)
            if user:
                user_tweets = await client.get_user_tweets(user.id, 'Tweets', count=5)
                for tweet in user_tweets:
                    td = _tweet_to_dict(tweet)
                    if td:
                        td["team_member"] = True
                        team_tweets.append(td)
            await _human_delay()
        except Exception as e:
            _log_error(f"@{account}", e)
            continue

    if team_tweets:
        cache = _load_cache()
        cache["team"] = team_tweets[:15]
        cache["last_updated"] = datetime.now(timezone.utc).isoformat()
        _save_cache(cache)
        return team_tweets[:15]

    return _get_fallback_team()


def _log_error(context: str, error: Exception):
    msg = str(error)
    if len(msg) > 200:
        msg = msg[:200] + "..."
    print(f"[Twitter] {context}: {msg}")


def _get_fallback_pulse() -> list:
    cache = _load_cache()
    if cache.get("pulse"):
        return cache["pulse"]
    return [{
        "id": "info-1",
        "text": "🎩 Twitter Pulse is connecting... Add credentials to .env and a cookies file to data/twitter_cookies.json",
        "username": "degendreamhub",
        "display_name": "Degen Dream Hub",
        "profile_image": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "retweet_count": 0, "like_count": 0, "reply_count": 0,
        "url": "", "is_fallback": True
    }]


def _get_fallback_team() -> list:
    cache = _load_cache()
    if cache.get("team"):
        return cache["team"]
    return [{
        "id": "team-1",
        "text": "👑 @degentokenbase — Official DEGEN account. Follow for WL drops.",
        "username": "degentokenbase",
        "display_name": "DEGEN",
        "profile_image": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "retweet_count": 0, "like_count": 0, "reply_count": 0,
        "url": "https://x.com/degentokenbase",
        "team_member": True, "is_fallback": True
    }]


# === CLI: Run locally to generate cookies ===
async def _generate_cookies():
    """Login and save cookies for deployment."""
    print("=" * 50)
    print("DEGEN Dream Hub — Twitter Cookie Generator")
    print("=" * 50)

    if not TWITTER_USERNAME or not TWITTER_PASSWORD:
        print("\n❌ Set TWITTER_USERNAME, TWITTER_PASSWORD, TWITTER_EMAIL in .env first!")
        return

    try:
        from twikit import Client

        client = Client('en-US')

        print(f"\n🔐 Logging in as @{TWITTER_USERNAME}...")
        await client.login(
            auth_info_1=TWITTER_USERNAME,
            auth_info_2=TWITTER_EMAIL or None,
            password=TWITTER_PASSWORD,
            cookies_file=str(COOKIES_FILE),
        )

        print(f"✅ Login successful! Cookies saved to: {COOKIES_FILE}")

        # Quick test
        print(f"\n🧪 Testing search...")
        tweets = await client.search_tweet('$DEGEN', 'Latest', count=5)
        count = 0
        for tweet in tweets:
            if count >= 3:
                break
            print(f"   @{tweet.user.screen_name}: {tweet.text[:80]}...")
            count += 1
        print(f"\n✅ Everything works!")

    except Exception as e:
        msg = str(e)
        if len(msg) > 300:
            msg = msg[:300] + "..."
        print(f"\n❌ Error: {msg}")
        print(f"\n💡 If Cloudflare blocks login, copy cookies from your browser:")
        print(f"   1. Open x.com in Chrome, log in")
        print(f"   2. Open DevTools → Application → Cookies → x.com")
        print(f"   3. Export auth_token, ct0, twid cookies to {COOKIES_FILE}")


if __name__ == "__main__":
    asyncio.run(_generate_cookies())
