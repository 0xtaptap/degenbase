"""
Alchemy API client for DEGEN token on-chain data (Base chain).
DEGEN contract: 0x4ed4e862860bed51a9570b96d89af5e1b0efefed
"""

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

ALCHEMY_API_KEY = os.getenv("ALCHEMY_API_KEY", "")
BASE_URL = f"https://base-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
DEGEN_CONTRACT = "0x4ed4e862860bed51a9570b96d89af5e1b0efefed"
DEGEN_DECIMALS = 18


async def get_degen_balance(wallet_address: str) -> dict:
    """Get DEGEN token balance for a wallet on Base chain."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "alchemy_getTokenBalances",
        "params": [wallet_address, [DEGEN_CONTRACT]]
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(BASE_URL, json=payload)
        data = resp.json()

    if "result" not in data:
        return {"wallet": wallet_address, "balance": "0", "balance_formatted": "0", "error": data.get("error")}

    token_balances = data["result"].get("tokenBalances", [])
    if not token_balances:
        return {"wallet": wallet_address, "balance": "0", "balance_formatted": "0"}

    raw_balance = token_balances[0].get("tokenBalance", "0x0")
    balance_wei = int(raw_balance, 16)
    balance_formatted = balance_wei / (10 ** DEGEN_DECIMALS)

    return {
        "wallet": wallet_address,
        "balance_raw": str(balance_wei),
        "balance": round(balance_formatted, 2),
        "balance_formatted": _format_number(balance_formatted),
        "contract": DEGEN_CONTRACT,
        "chain": "Base"
    }


async def get_degen_transfers(wallet_address: str, max_count: int = 20) -> dict:
    """Get recent DEGEN token transfer history for a wallet."""
    transfers_in = await _fetch_transfers(wallet_address, direction="to", max_count=max_count)
    transfers_out = await _fetch_transfers(wallet_address, direction="from", max_count=max_count)

    all_transfers = []

    for t in transfers_in:
        all_transfers.append({
            "type": "received",
            "from": t.get("from", ""),
            "to": t.get("to", ""),
            "value": _parse_transfer_value(t),
            "value_formatted": _format_number(_parse_transfer_value(t)),
            "hash": t.get("hash", ""),
            "block": t.get("blockNum", ""),
            "timestamp": t.get("metadata", {}).get("blockTimestamp", "")
        })

    for t in transfers_out:
        all_transfers.append({
            "type": "sent",
            "from": t.get("from", ""),
            "to": t.get("to", ""),
            "value": _parse_transfer_value(t),
            "value_formatted": _format_number(_parse_transfer_value(t)),
            "hash": t.get("hash", ""),
            "block": t.get("blockNum", ""),
            "timestamp": t.get("metadata", {}).get("blockTimestamp", "")
        })

    # Sort by block number descending
    all_transfers.sort(key=lambda x: x.get("block", ""), reverse=True)

    return {
        "wallet": wallet_address,
        "total_received": len(transfers_in),
        "total_sent": len(transfers_out),
        "transfers": all_transfers[:max_count]
    }


async def get_recent_activity(max_count: int = 15) -> dict:
    """Get recent DEGEN transfer activity across the network."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "alchemy_getAssetTransfers",
        "params": [{
            "fromBlock": "0x0",
            "toBlock": "latest",
            "contractAddresses": [DEGEN_CONTRACT],
            "category": ["erc20"],
            "order": "desc",
            "maxCount": hex(max_count),
            "withMetadata": True
        }]
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(BASE_URL, json=payload)
        data = resp.json()

    transfers = data.get("result", {}).get("transfers", [])
    activity = []

    for t in transfers:
        value = _parse_transfer_value(t)
        activity.append({
            "from": _shorten_address(t.get("from", "")),
            "to": _shorten_address(t.get("to", "")),
            "from_full": t.get("from", ""),
            "to_full": t.get("to", ""),
            "value": value,
            "value_formatted": _format_number(value),
            "hash": t.get("hash", ""),
            "timestamp": t.get("metadata", {}).get("blockTimestamp", "")
        })

    return {"activity": activity, "token": "DEGEN", "chain": "Base"}


async def _fetch_transfers(wallet: str, direction: str = "from", max_count: int = 20) -> list:
    """Fetch DEGEN transfers from or to a wallet."""
    params = {
        "fromBlock": "0x0",
        "toBlock": "latest",
        "contractAddresses": [DEGEN_CONTRACT],
        "category": ["erc20"],
        "order": "desc",
        "maxCount": hex(max_count),
        "withMetadata": True
    }

    if direction == "from":
        params["fromAddress"] = wallet
    else:
        params["toAddress"] = wallet

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "alchemy_getAssetTransfers",
        "params": [params]
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(BASE_URL, json=payload)
        data = resp.json()

    return data.get("result", {}).get("transfers", [])


def _parse_transfer_value(transfer: dict) -> float:
    """Parse the value from an Alchemy transfer object."""
    value = transfer.get("value")
    if value is not None:
        return round(float(value), 2)

    raw = transfer.get("rawContract", {}).get("value", "0x0")
    try:
        return round(int(raw, 16) / (10 ** DEGEN_DECIMALS), 2)
    except (ValueError, TypeError):
        return 0.0


def _format_number(num: float) -> str:
    """Format number with K/M/B suffixes."""
    if num >= 1_000_000_000:
        return f"{num / 1_000_000_000:.1f}B"
    elif num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num / 1_000:.1f}K"
    else:
        return f"{num:,.2f}"


def _shorten_address(address: str) -> str:
    """Shorten wallet address for display."""
    if len(address) > 10:
        return f"{address[:6]}...{address[-4:]}"
    return address
