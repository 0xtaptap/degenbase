"""
Degen Dream Hub — FastAPI Server
Serves the frontend + API endpoints for dreams, on-chain data, and Twitter pulse.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from alchemy_client import (
    get_degen_balance, get_degen_transfers, get_recent_activity,
    BASE_URL, DEGEN_CONTRACT, DEGEN_DECIMALS, _format_number, _shorten_address
)
from twitter_scraper import scrape_degen_pulse, scrape_team_tweets

app = FastAPI(title="Degen Dream Hub", version="2.0.0")

# Data paths
DATA_DIR = Path(__file__).parent / "data"
DREAMS_FILE = DATA_DIR / "dreams.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
if not DREAMS_FILE.exists():
    DREAMS_FILE.write_text('{"dreams": []}', encoding="utf-8")


# === Models ===

class DreamSubmission(BaseModel):
    text: str
    image_url: Optional[str] = None
    wallet: Optional[str] = None


class DreamUpvote(BaseModel):
    dream_id: str


# === Command Center Endpoints ===

# Cache for token stats (avoid hammering DexScreener)
_token_stats_cache = {"data": None, "timestamp": 0}
_STATS_CACHE_TTL = 30  # seconds


@app.get("/api/token/stats")
async def get_token_stats():
    """Live DEGEN token stats from DexScreener + Alchemy."""
    import time
    now = time.time()

    # Return cache if fresh
    if _token_stats_cache["data"] and (now - _token_stats_cache["timestamp"]) < _STATS_CACHE_TTL:
        return _token_stats_cache["data"]

    stats = {
        "price": 0,
        "price_formatted": "$0.00",
        "price_change_24h": 0,
        "market_cap": 0,
        "market_cap_formatted": "$0",
        "volume_24h": 0,
        "volume_24h_formatted": "$0",
        "liquidity": 0,
        "liquidity_formatted": "$0",
        "fdv": 0,
        "fdv_formatted": "$0",
        "holders": 0,
        "holders_formatted": "0",
        "pair_url": "",
        "dex_name": "",
        "chain": "Base",
        "token": "DEGEN",
        "last_updated": datetime.now(timezone.utc).isoformat()
    }

    # 1. Get price/volume/mcap from DexScreener (free, no key)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{DEGEN_CONTRACT}"
            )
            dex_data = resp.json()

        pairs = dex_data.get("pairs", [])
        if pairs:
            # Pick the pair with highest liquidity
            top_pair = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
            stats["price"] = float(top_pair.get("priceUsd", 0) or 0)
            stats["price_formatted"] = f"${stats['price']:.6f}" if stats["price"] < 1 else f"${stats['price']:.2f}"
            stats["price_change_24h"] = float(top_pair.get("priceChange", {}).get("h24", 0) or 0)
            stats["volume_24h"] = float(top_pair.get("volume", {}).get("h24", 0) or 0)
            stats["volume_24h_formatted"] = f"${_format_number(stats['volume_24h'])}"
            stats["market_cap"] = float(top_pair.get("marketCap", 0) or 0)
            stats["market_cap_formatted"] = f"${_format_number(stats['market_cap'])}"
            liq = float(top_pair.get("liquidity", {}).get("usd", 0) or 0)
            stats["liquidity"] = liq
            stats["liquidity_formatted"] = f"${_format_number(liq)}"
            fdv = float(top_pair.get("fdv", 0) or 0)
            stats["fdv"] = fdv
            stats["fdv_formatted"] = f"${_format_number(fdv)}"
            stats["pair_url"] = top_pair.get("url", "")
            stats["dex_name"] = top_pair.get("dexId", "unknown")
    except Exception as e:
        print(f"[TokenStats] DexScreener error: {e}")

    # 2. Get holder count from Alchemy
    try:
        payload = {
            "jsonrpc": "2.0", "id": 1,
            "method": "alchemy_getTokenMetadata",
            "params": [DEGEN_CONTRACT]
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(BASE_URL, json=payload)
            meta = resp.json()
        if "result" in meta:
            # Note: Alchemy doesn't return holder count directly via this endpoint
            # We'll estimate from DexScreener data or set a placeholder
            pass
    except Exception:
        pass

    _token_stats_cache["data"] = stats
    _token_stats_cache["timestamp"] = now
    return stats


@app.get("/api/whales/recent")
async def get_whale_transfers():
    """Get recent big DEGEN transfers (whale activity)."""
    try:
        # Fetch more transfers to filter for whales
        payload = {
            "jsonrpc": "2.0", "id": 1,
            "method": "alchemy_getAssetTransfers",
            "params": [{
                "fromBlock": "0x0",
                "toBlock": "latest",
                "contractAddresses": [DEGEN_CONTRACT],
                "category": ["erc20"],
                "order": "desc",
                "maxCount": hex(50),
                "withMetadata": True
            }]
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(BASE_URL, json=payload)
            data = resp.json()

        transfers = data.get("result", {}).get("transfers", [])
        whales = []

        for t in transfers:
            value = t.get("value")
            if value is not None:
                val = float(value)
            else:
                raw = t.get("rawContract", {}).get("value", "0x0")
                try:
                    val = int(raw, 16) / (10 ** DEGEN_DECIMALS)
                except (ValueError, TypeError):
                    val = 0.0

            # Only include transfers > 50K DEGEN (lower threshold for more activity)
            if val >= 50000:
                whales.append({
                    "from": _shorten_address(t.get("from", "")),
                    "to": _shorten_address(t.get("to", "")),
                    "from_full": t.get("from", ""),
                    "to_full": t.get("to", ""),
                    "value": round(val, 2),
                    "value_formatted": _format_number(val),
                    "hash": t.get("hash", ""),
                    "timestamp": t.get("metadata", {}).get("blockTimestamp", ""),
                    "size": "whale" if val >= 1_000_000 else "shark" if val >= 500_000 else "dolphin"
                })

        return {"whales": whales[:20], "total": len(whales), "token": "DEGEN", "chain": "Base"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Whale tracking error: {str(e)}")


@app.get("/api/wallet/xray/{address}")
async def wallet_xray(address: str):
    """Enhanced wallet analysis — balance, rank estimate, stats."""
    if not address.startswith("0x") or len(address) != 42:
        raise HTTPException(status_code=400, detail="Invalid wallet address")

    try:
        # Get balance
        balance = await get_degen_balance(address)

        # Get transfer history
        transfers = await get_degen_transfers(address, max_count=50)

        # Calculate stats
        all_transfers = transfers.get("transfers", [])
        total_received = sum(t["value"] for t in all_transfers if t["type"] == "received")
        total_sent = sum(t["value"] for t in all_transfers if t["type"] == "sent")

        # Find first interaction
        first_tx = min(all_transfers, key=lambda t: t.get("timestamp", "z")) if all_transfers else None
        # Find largest single TX
        largest_tx = max(all_transfers, key=lambda t: t.get("value", 0)) if all_transfers else None

        # Get current price for USD value
        usd_value = 0
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"https://api.dexscreener.com/latest/dex/tokens/{DEGEN_CONTRACT}"
                )
                dex_data = resp.json()
            pairs = dex_data.get("pairs", [])
            if pairs:
                price = float(pairs[0].get("priceUsd", 0) or 0)
                usd_value = round(balance.get("balance", 0) * price, 2)
        except Exception:
            pass

        return {
            "address": address,
            "address_short": _shorten_address(address),
            "balance": balance.get("balance", 0),
            "balance_formatted": balance.get("balance_formatted", "0"),
            "usd_value": usd_value,
            "usd_value_formatted": f"${_format_number(usd_value)}",
            "total_transfers": len(all_transfers),
            "total_received": round(total_received, 2),
            "total_received_formatted": _format_number(total_received),
            "total_sent": round(total_sent, 2),
            "total_sent_formatted": _format_number(total_sent),
            "first_interaction": first_tx.get("timestamp", "") if first_tx else "",
            "largest_tx": {
                "value": largest_tx.get("value", 0) if largest_tx else 0,
                "value_formatted": _format_number(largest_tx.get("value", 0)) if largest_tx else "0",
                "type": largest_tx.get("type", "") if largest_tx else "",
                "hash": largest_tx.get("hash", "") if largest_tx else ""
            },
            "token": "DEGEN",
            "chain": "Base"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"X-Ray error: {str(e)}")


# === Dream Board Endpoints (legacy) ===

@app.get("/api/dreams")
async def get_dreams():
    """Get all submitted dreams."""
    data = _load_dreams()
    dreams = sorted(data.get("dreams", []), key=lambda d: d.get("timestamp", ""), reverse=True)
    return {"dreams": dreams, "total": len(dreams)}


@app.post("/api/dreams")
async def submit_dream(dream: DreamSubmission):
    """Submit a new dream to the board."""
    if not dream.text.strip():
        raise HTTPException(status_code=400, detail="Dream text cannot be empty")

    degen_balance = "0"
    degen_balance_formatted = "0"
    if dream.wallet:
        try:
            balance_data = await get_degen_balance(dream.wallet)
            degen_balance = str(balance_data.get("balance", 0))
            degen_balance_formatted = balance_data.get("balance_formatted", "0")
        except Exception:
            pass

    new_dream = {
        "id": str(uuid.uuid4()),
        "text": dream.text.strip(),
        "image_url": dream.image_url or "",
        "wallet": dream.wallet or "",
        "degen_balance": degen_balance,
        "degen_balance_formatted": degen_balance_formatted,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "upvotes": 0
    }

    data = _load_dreams()
    data["dreams"].append(new_dream)
    _save_dreams(data)
    return {"success": True, "dream": new_dream}


@app.post("/api/dreams/upvote")
async def upvote_dream(upvote: DreamUpvote):
    """Upvote a dream."""
    data = _load_dreams()
    for dream in data["dreams"]:
        if dream["id"] == upvote.dream_id:
            dream["upvotes"] = dream.get("upvotes", 0) + 1
            _save_dreams(data)
            return {"success": True, "upvotes": dream["upvotes"]}
    raise HTTPException(status_code=404, detail="Dream not found")


# === On-Chain Endpoints ===

@app.get("/api/onchain/activity/recent")
async def get_network_activity():
    """Get recent DEGEN transfer activity on the network."""
    try:
        activity = await get_recent_activity(max_count=15)
        return activity
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Alchemy API error: {str(e)}")


@app.get("/api/onchain/{wallet}")
async def get_wallet_data(wallet: str):
    """Get DEGEN balance and transfer history for a wallet."""
    if not wallet.startswith("0x") or len(wallet) != 42:
        raise HTTPException(status_code=400, detail="Invalid wallet address")

    try:
        balance = await get_degen_balance(wallet)
        transfers = await get_degen_transfers(wallet, max_count=15)
        return {
            "balance": balance,
            "transfers": transfers,
            "token": "DEGEN",
            "chain": "Base"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Alchemy API error: {str(e)}")



# === Twitter Endpoints ===

@app.get("/api/twitter/pulse")
async def get_twitter_pulse():
    """Get latest tweets mentioning DEGEN."""
    try:
        tweets = await scrape_degen_pulse()
        return {"tweets": tweets, "total": len(tweets)}
    except Exception as e:
        return {"tweets": [], "total": 0, "error": str(e)}


@app.get("/api/twitter/team")
async def get_team_tweets():
    """Get latest tweets from team accounts."""
    try:
        tweets = await scrape_team_tweets()
        return {"tweets": tweets, "total": len(tweets)}
    except Exception as e:
        return {"tweets": [], "total": 0, "error": str(e)}


# === Static File Serving ===

@app.get("/")
async def serve_index():
    """Serve the main frontend."""
    return FileResponse(Path(__file__).parent / "index.html")


# Mount static files (CSS, JS)
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# === Helpers ===

def _load_dreams() -> dict:
    """Load dreams from JSON file."""
    try:
        with open(DREAMS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"dreams": []}


def _save_dreams(data: dict):
    """Save dreams to JSON file."""
    with open(DREAMS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

