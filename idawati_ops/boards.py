"""Agent-bounty board watchers (read-only, public endpoints only).

Boards:
- task-bounty.com — public JSON API, no auth.
- gofrantic.com — public MCP endpoint (``frantic.read_board``), no auth.
  The site's HTML board page is JS-heavy, so the CLI talks to the MCP
  endpoint directly. No agent token is ever needed for the public board.
- opire.dev — public JSON APIs, no auth.

A bounty is only ever listed exactly as the live response returns it.
Nothing is marked "new" or "doable" by this module — that judgement is
left to the operator.
"""

from __future__ import annotations

import json

from .http import HttpError, get_json, post_json

TASK_BOUNTY_URL = "https://www.task-bounty.com/api/v1/tasks"
GOFRANTIC_MCP_URL = "https://api.gofrantic.com/mcp"
OPIRE_REWARDS_URL = (
    "https://app.opire.dev/api/backend/rewards"
    "?page=1&itemsPerPage=30&minPrice=0"
)
OPIRE_KPIS_URL = "https://app.opire.dev/api/backend/analytics/kpis"


# ---------------------------------------------------------------------------
# Pure parsers (unit-tested, no network)
# ---------------------------------------------------------------------------

def _cents_to_dollars(value: object) -> str:
    try:
        return f"${float(value) / 100:,.2f}"
    except (TypeError, ValueError):
        return "?"


def parse_task_bounty(payload: object) -> list[dict]:
    """Normalize a task-bounty API payload into bounty rows."""
    rows: list[dict] = []
    if not isinstance(payload, dict):
        return rows
    data = payload.get("data")
    if not isinstance(data, list):
        return rows
    for item in data:
        if not isinstance(item, dict):
            continue
        title = (
            item.get("title")
            or item.get("name")
            or item.get("task")
            or str(item.get("id", ""))
        )
        reward = item.get("reward") or item.get("price_usd") or item.get("amount")
        if isinstance(reward, (int, float)):
            reward = f"${reward:,.2f}"
        rows.append(
            {
                "platform": "task-bounty",
                "id": str(item.get("id", "")),
                "title": str(title),
                "reward": str(reward) if reward is not None else "?",
                "status": str(item.get("status", "open")),
                "url": str(item.get("url") or item.get("link") or ""),
            }
        )
    return rows


def parse_mcp_response(raw: object) -> dict:
    """Extract the JSON-RPC result dict from an MCP response.

    The server may return plain JSON or a text/event-stream body; handle
    both. Raises ValueError when no JSON-RPC result can be found.
    """
    text = raw if isinstance(raw, str) else json.dumps(raw)
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        parsed = None
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                try:
                    parsed = json.loads(line[5:].strip())
                    break
                except (json.JSONDecodeError, ValueError):
                    continue
        if parsed is None:
            raise ValueError("MCP response is not JSON")
    if not isinstance(parsed, dict) or "result" not in parsed:
        raise ValueError("MCP response has no result field")
    return parsed["result"]


def parse_gofrantic_board(result: dict) -> list[dict]:
    """Normalize a frantic.read_board result into bounty rows.

    The tool returns its payload as a JSON string inside
    ``result.content[0].text``.
    """
    rows: list[dict] = []
    content = result.get("content")
    if not isinstance(content, list) or not content:
        return rows
    text = content[0].get("text", "") if isinstance(content[0], dict) else ""
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return rows
    board = payload.get("board", {}) if isinstance(payload, dict) else {}
    bounties = board.get("bounties", []) if isinstance(board, dict) else []
    for item in bounties:
        if not isinstance(item, dict):
            continue
        price = item.get("price_usd")
        rows.append(
            {
                "platform": "gofrantic",
                "id": str(item.get("number", item.get("id", ""))),
                "title": str(item.get("title", "")),
                "reward": f"${price:,.2f}" if isinstance(price, (int, float)) else "?",
                "status": str(item.get("work_status", item.get("status", "open"))),
                "url": str(item.get("url", "")),
            }
        )
    return rows


def parse_opire_rewards(payload: object) -> list[dict]:
    """Normalize an Opire rewards list payload into bounty rows."""
    rows: list[dict] = []
    if not isinstance(payload, list):
        return rows
    for item in payload:
        if not isinstance(item, dict):
            continue
        price = item.get("pendingPrice") or {}
        value = price.get("value") if isinstance(price, dict) else None
        claimers = len(item.get("claimerUsers") or [])
        trying = len(item.get("tryingUsers") or [])
        langs = item.get("programmingLanguages") or []
        rows.append(
            {
                "platform": "opire",
                "id": str(item.get("id", ""))[:12],
                "title": str(item.get("title", "")),
                "reward": _cents_to_dollars(value),
                "status": f"claimers {claimers} / trying {trying}",
                "url": str(item.get("url", "")),
                "languages": ", ".join(str(lang) for lang in langs),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Live fetchers
# ---------------------------------------------------------------------------

def fetch_task_bounty() -> tuple[list[dict], str]:
    """Return (rows, note). Raises HttpError on failure."""
    payload = get_json(TASK_BOUNTY_URL)
    rows = parse_task_bounty(payload)
    note = ""
    if isinstance(payload, dict) and isinstance(payload.get("meta"), dict):
        note = str(payload["meta"].get("message", ""))
    return rows, note


def fetch_gofrantic() -> tuple[list[dict], str]:
    """Return (rows, note) from the public Frantic board. Raises HttpError."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "frantic.read_board",
            "arguments": {"status": "open", "limit": 20},
        },
    }
    raw = post_json(
        GOFRANTIC_MCP_URL,
        payload,
        # The MCP endpoint requires the streamable-HTTP Accept header;
        # without it the server answers 406 Not Acceptable.
        headers={"Accept": "application/json, text/event-stream"},
    )
    result = parse_mcp_response(raw)
    return parse_gofrantic_board(result), ""


def fetch_opire() -> tuple[list[dict], str]:
    """Return (rows, note) from Opire's public list + KPIs. Raises HttpError."""
    payload = get_json(OPIRE_REWARDS_URL)
    rows = parse_opire_rewards(payload)
    note = ""
    try:
        kpis = get_json(OPIRE_KPIS_URL)
        if isinstance(kpis, dict):
            note = (
                f"KPI: {kpis.get('bountiesAvailable', '?')} available, "
                f"${(kpis.get('moneyAvailableInBounties') or {}).get('value', 0) / 100:,.2f} "
                f"total; {kpis.get('bountiesPaid', '?')} paid all-time"
            )
    except HttpError:
        note = "KPI endpoint unreadable (list still shown)"
    return rows, note


FETCHERS = (
    ("task-bounty", fetch_task_bounty),
    ("gofrantic", fetch_gofrantic),
    ("opire", fetch_opire),
)


def fetch_all_boards() -> tuple[list[dict], dict[str, str]]:
    """Poll every board. Returns (rows, status per board).

    A board that fails is reported in the status dict, never faked.
    """
    rows: list[dict] = []
    status: dict[str, str] = {}
    for name, fetcher in FETCHERS:
        try:
            board_rows, note = fetcher()
            rows.extend(board_rows)
            status[name] = f"OK ({len(board_rows)} open)" + (f" — {note}" if note else "")
        except (HttpError, ValueError) as exc:
            status[name] = f"UNREADABLE — {exc}"
    return rows, status
