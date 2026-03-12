"""
Degen Dream Hub — FastAPI Server
Serves the frontend + API endpoints for dreams, on-chain data, and Twitter pulse.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from alchemy_client import get_degen_balance, get_degen_transfers, get_recent_activity
from twitter_scraper import scrape_degen_pulse, scrape_team_tweets

app = FastAPI(title="Degen Dream Hub", version="1.0.0")

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


# === Dream Board Endpoints ===

@app.get("/api/dreams")
async def get_dreams():
    """Get all submitted dreams."""
    data = _load_dreams()
    # Sort by timestamp, newest first
    dreams = sorted(data.get("dreams", []), key=lambda d: d.get("timestamp", ""), reverse=True)
    return {"dreams": dreams, "total": len(dreams)}


@app.post("/api/dreams")
async def submit_dream(dream: DreamSubmission):
    """Submit a new dream to the board."""
    if not dream.text.strip():
        raise HTTPException(status_code=400, detail="Dream text cannot be empty")

    # If wallet provided, try to get their DEGEN balance
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

