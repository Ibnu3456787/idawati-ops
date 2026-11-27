"""Bug-bounty recon helper: Sourcify contract verification check (read-only).

Uses the Sourcify API v2 (v1 was removed):
    GET https://sourcify.dev/server/v2/contract/{chainId}/{address}
        ?fields=sources,metadata

Reports whether the contract source is verified, plus the contract and
function names found in the published source. An unverified contract is
reported plainly as unverified — never guessed.
"""

from __future__ import annotations

import json
import re

from .http import HttpError, get_json
from .patrol import is_valid_address

CHAIN_IDS = {"bsc": 56, "eth": 1}
SOURCIFY_BASE = "https://sourcify.dev/server/v2/contract"

_CONTRACT_RE = re.compile(r"\b(?:contract|library|interface)\s+(\w+)")
_FUNCTION_RE = re.compile(r"\bfunction\s+(\w+)\s*\(")
_MAX_FUNCTIONS_SHOWN = 30


def build_sourcify_url(chain: str, address: str) -> str:
    """Build the Sourcify v2 contract URL for a chain name + address."""
    chain_id = CHAIN_IDS[chain]
    return f"{SOURCIFY_BASE}/{chain_id}/{address}?fields=sources,metadata"


_COMMENT_RE = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)


def _strip_comments(source: str) -> str:
    """Remove // and /* */ comments so declarations in prose are not read."""
    return _COMMENT_RE.sub(" ", source)


def parse_sources(sources: dict) -> tuple[list[str], list[str]]:
    """Extract (contract names, function names) from Sourcify source files.

    Only ``.sol`` files are scanned, and comments are stripped first so
    words like "contract" inside a comment sentence are not mistaken for
    declarations. Names are deduplicated and sorted.
    """
    contracts: set[str] = set()
    functions: set[str] = set()
    for filename, entry in (sources or {}).items():
        if not filename.endswith(".sol"):
            continue
        content = entry.get("content", "") if isinstance(entry, dict) else ""
        if not isinstance(content, str):
            continue
        content = _strip_comments(content)
        contracts.update(_CONTRACT_RE.findall(content))
        functions.update(_FUNCTION_RE.findall(content))
    return sorted(contracts), sorted(functions)


def _contract_name_from_metadata(metadata: object) -> str:
    """Best-effort main contract name from Sourcify metadata, else ''."""
    data = metadata
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, ValueError):
            return ""
    if not isinstance(data, dict):
        return ""
    settings = data.get("settings")
    if not isinstance(settings, dict):
        return ""
    target = settings.get("compilationTarget")
    if isinstance(target, dict) and target:
        return str(next(iter(target.values())))
    return ""


def check_contract(chain: str, address: str) -> dict:
    """Check a contract on Sourcify. Returns a result dict.

    Keys: chain, address, verified (bool), match, creation_match,
    runtime_match, contract_name, contracts, functions, source_files,
    error ('' when the check itself succeeded).
    """
    result: dict = {
        "chain": chain,
        "address": address,
        "verified": False,
        "match": None,
        "creation_match": None,
        "runtime_match": None,
        "contract_name": "",
        "contracts": [],
        "functions": [],
        "source_files": [],
        "error": "",
    }
    if chain not in CHAIN_IDS:
        result["error"] = f"unknown chain {chain!r} (use bsc or eth)"
        return result
    if not is_valid_address(address):
        result["error"] = f"invalid address: {address!r}"
        return result
    url = build_sourcify_url(chain, address)
    try:
        payload = get_json(url)
    except HttpError as exc:
        # Sourcify answers 404 with a JSON body for unverified contracts.
        if exc.status == 404:
            return result
        result["error"] = str(exc)
        return result
    if not isinstance(payload, dict):
        result["error"] = "Sourcify did not return an object"
        return result
    result["match"] = payload.get("match")
    result["creation_match"] = payload.get("creationMatch")
    result["runtime_match"] = payload.get("runtimeMatch")
    result["verified"] = bool(payload.get("match"))
    sources = payload.get("sources") or {}
    if isinstance(sources, dict):
        result["source_files"] = sorted(sources.keys())
        contracts, functions = parse_sources(sources)
        result["contracts"] = contracts
        result["functions"] = functions[:_MAX_FUNCTIONS_SHOWN]
    result["contract_name"] = _contract_name_from_metadata(payload.get("metadata"))
    return result
