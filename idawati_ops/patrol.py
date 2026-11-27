"""Read-only patrol health snapshot (no Muse tools, no keys, no signing).

Checks:
- BSC wallet balance for a --wallet address via a public BSC RPC.
- Flop testnet: faucet chain info + gateway model list + the public
  testnet page (reports whether it still says "unscored").

Every check prints OK/FAIL with its evidence. Nothing is invented: a
check that cannot be read is FAIL, with the error shown.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal

import requests

from .http import HttpError, get_json, get_text

BSC_RPC_URL = "https://bsc-dataseed.binance.org/"
FLOP_CHAIN_URL = "https://faucet.flop.network/chain"
FLOP_MODELS_URL = "https://api.flop.network/v1/models"
FLOP_TESTNET_PAGE_URL = "https://flop.finance/testnet"

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def is_valid_address(address: str) -> bool:
    """True for a well-formed 0x-prefixed 40-hex-char EVM address."""
    return bool(_ADDRESS_RE.match(address or ""))


def wei_to_bnb(wei_hex: str) -> str:
    """Convert a hex wei balance (e.g. '0x3d77a0500') to a BNB string."""
    wei = int(wei_hex, 16)
    bnb = Decimal(wei) / Decimal(10**18)
    return format(bnb.normalize(), "f")


def bsc_balance(wallet: str) -> tuple[bool, str]:
    """Read a wallet's BNB balance from the public BSC RPC.

    Returns (ok, evidence). Raises HttpError on transport failure.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_getBalance",
        "params": [wallet, "latest"],
    }
    try:
        resp = requests.post(
            BSC_RPC_URL, json=payload, timeout=25,
            headers={"Content-Type": "application/json"},
        )
    except requests.RequestException as exc:
        raise HttpError(f"BSC RPC request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise HttpError(f"BSC RPC returned HTTP {resp.status_code}",
                        status=resp.status_code)
    try:
        data = resp.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise HttpError(f"BSC RPC did not return JSON: {exc}") from exc
    if "error" in data:
        return False, f"RPC error: {data['error']}"
    result = data.get("result")
    if not isinstance(result, str):
        return False, f"unexpected RPC result: {data!r}"
    return True, f"{wallet} balance {wei_to_bnb(result)} BNB ({result} wei)"


def flop_chain() -> tuple[bool, str]:
    """Check the Flop faucet chain endpoint."""
    data = get_json(FLOP_CHAIN_URL)
    if not isinstance(data, dict):
        return False, "chain endpoint did not return an object"
    return True, (
        f"network={data.get('network')} chain={data.get('chain')} "
        f"rpc={data.get('rpc')}"
    )


def flop_models() -> tuple[bool, str]:
    """Check the Flop gateway model list endpoint."""
    data = get_json(FLOP_MODELS_URL)
    if not isinstance(data, dict):
        return False, "models endpoint did not return an object"
    models = data.get("data")
    count = len(models) if isinstance(models, list) else "?"
    return True, f"{count} models listed"


def flop_page_unscored() -> tuple[bool, str]:
    """Check whether the public Flop testnet page still says 'unscored'."""
    text = get_text(FLOP_TESTNET_PAGE_URL)
    if "unscored" in text.lower():
        match = re.search(r".{0,60}unscored.{0,60}", text, re.I | re.S)
        snippet = re.sub(r"\s+", " ", match.group(0)) if match else "unscored"
        return True, f"page says unscored — {snippet.strip()!r}"
    return True, "page does NOT say unscored anymore (scored phase may be open)"


CHECKS = (
    ("BSC balance", "bsc"),
    ("Flop faucet chain", "flop_chain"),
    ("Flop gateway models", "flop_models"),
    ("Flop testnet page", "flop_page"),
)


def run_patrol(wallet: str) -> list[tuple[str, bool, str]]:
    """Run every patrol check. Returns [(name, ok, evidence), ...]."""
    results: list[tuple[str, bool, str]] = []
    if not is_valid_address(wallet):
        results.append(("BSC balance", False, f"invalid wallet address: {wallet!r}"))
    else:
        try:
            ok, evidence = bsc_balance(wallet)
            results.append(("BSC balance", ok, evidence))
        except HttpError as exc:
            results.append(("BSC balance", False, str(exc)))
    for name, fn in (
        ("Flop faucet chain", flop_chain),
        ("Flop gateway models", flop_models),
        ("Flop testnet page", flop_page_unscored),
    ):
        try:
            ok, evidence = fn()
            results.append((name, ok, evidence))
        except HttpError as exc:
            results.append((name, False, str(exc)))
    return results
