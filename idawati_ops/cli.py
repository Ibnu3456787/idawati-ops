"""Command-line interface for IDAWATI Ops.

Usage: python -m idawati_ops <command> [options]

Commands: boards, square, patrol, recon, video, about.
Run `python -m idawati_ops <command> --help` for per-command options.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __author__, __license__, __version__
from .boards import fetch_all_boards
from .format import render_table
from .http import HttpError
from .patrol import is_valid_address, run_patrol
from .recon import check_contract
from .square import fetch_top_movers
from .video import CLIP_SECONDS, VideoError, build_video

ABOUT_LINE = f"IDAWATI Ops {__version__} — Created by {__author__} — {__license__} License"


def _add_json_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true",
                        help="print machine-readable JSON instead of a table")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="idawati-ops",
        description=(
            "IDAWATI Ops — all-in-one ops CLI for a solo crypto AI-agent "
            "operator. Read-only: public endpoints only, no keys, no "
            "signing, no spending."
        ),
    )
    parser.add_argument("--version", action="store_true",
                        help="print version, author and license, then exit")
    sub = parser.add_subparsers(dest="command", metavar="command")

    p_boards = sub.add_parser(
        "boards",
        help="poll the public agent-bounty boards (task-bounty, gofrantic, opire)",
        description="Poll the three public agent-bounty boards and list open bounties.",
    )
    _add_json_arg(p_boards)

    p_square = sub.add_parser(
        "square",
        help="top 24h USDT movers from Binance public market data",
        description="Top 24h USDT movers by percent change (quote volume > $5M).",
    )
    p_square.add_argument("--min-volume", type=float, default=5_000_000,
                          help="minimum 24h quote volume in USD (default: 5000000)")
    p_square.add_argument("--limit", type=int, default=10,
                          help="how many movers to show (default: 10)")
    _add_json_arg(p_square)

    p_patrol = sub.add_parser(
        "patrol",
        help="read-only health snapshot: BSC balance + Flop testnet status",
        description="Health snapshot: BSC wallet balance and Flop testnet endpoints.",
    )
    p_patrol.add_argument("--wallet", required=True,
                          help="EVM wallet address to check (0x...40 hex chars)")
    _add_json_arg(p_patrol)

    p_recon = sub.add_parser(
        "recon",
        help="check a contract's Sourcify verification status (read-only)",
        description="Check whether a contract's source is verified on Sourcify.",
    )
    p_recon.add_argument("address", help="contract address (0x...40 hex chars)")
    p_recon.add_argument("--chain", choices=["bsc", "eth"], default="bsc",
                         help="chain to check (default: bsc)")
    _add_json_arg(p_recon)

    p_video = sub.add_parser(
        "video",
        help="assemble 3 clips + audio + end card into a 30s 9:16 video",
        description=(
            "Assemble exactly 3 clips (9s each) + a 3s end card into a "
            "30s 704x1248 video with audio muxed in. ffmpeg required."
        ),
    )
    p_video.add_argument("--clips", nargs=3, required=True, metavar="CLIP",
                         help="exactly 3 clip files, in order")
    p_video.add_argument("--audio", required=True, help="audio file (wav/mp3/m4a)")
    p_video.add_argument("--text", required=True,
                         help="end-card credit text, e.g. 'animator: by. YourName'")
    p_video.add_argument("--out", required=True, help="output mp4 path")

    sub.add_parser(
        "about",
        help="show author, version and license",
        description="Print the tool name, version, author and license.",
    )
    return parser


def cmd_boards(args: argparse.Namespace) -> int:
    rows, status = fetch_all_boards()
    if args.json:
        print(json.dumps(
            {"bounties": rows, "boards": status}, indent=2, ensure_ascii=False
        ))
    else:
        table_rows = [
            [row["platform"], row["id"], row["title"][:60], row["reward"], row["status"]]
            for row in rows
        ]
        print(render_table(["PLATFORM", "ID", "TITLE", "REWARD", "STATUS"], table_rows))
        print()
        for name, line in status.items():
            print(f"{name}: {line}")
        print(f"\nTotal open bounties shown: {len(rows)}")
    failed = [name for name, line in status.items() if line.startswith("UNREADABLE")]
    return 1 if failed else 0


def cmd_square(args: argparse.Namespace) -> int:
    if args.limit < 1:
        print(f"square: --limit must be at least 1, got {args.limit}",
              file=sys.stderr)
        return 2
    if args.min_volume < 0:
        print(f"square: --min-volume must not be negative, got {args.min_volume}",
              file=sys.stderr)
        return 2
    try:
        movers = fetch_top_movers(args.min_volume, args.limit)
    except (HttpError, ValueError) as exc:
        print(f"square: FAILED — {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"movers": movers}, indent=2))
    else:
        table_rows = [
            [m["symbol"], f"{m['price']:.8g}", f"{m['change_pct']:+.2f}%",
             f"${m['quote_volume']:,.0f}"]
            for m in movers
        ]
        print(render_table(
            ["SYMBOL", "PRICE", "24H %", "24H QUOTE VOL"], table_rows
        ))
    return 0


def cmd_patrol(args: argparse.Namespace) -> int:
    if not is_valid_address(args.wallet):
        print(f"patrol: invalid wallet address: {args.wallet!r}", file=sys.stderr)
        return 2
    results = run_patrol(args.wallet)
    if args.json:
        print(json.dumps(
            {"wallet": args.wallet,
             "checks": [{"name": n, "ok": ok, "evidence": e}
                        for n, ok, e in results]},
            indent=2,
        ))
    else:
        for name, ok, evidence in results:
            print(f"[{'OK' if ok else 'FAIL'}] {name} — {evidence}")
        passed = sum(1 for _, ok, _ in results if ok)
        print(f"\nSummary: {passed}/{len(results)} checks OK")
    return 0 if all(ok for _, ok, _ in results) else 1


def cmd_recon(args: argparse.Namespace) -> int:
    result = check_contract(args.chain, args.address)
    if result["error"]:
        print(f"recon: FAILED — {result['error']}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Address : {result['address']} (chain: {result['chain']})")
        print(f"Verified: {'YES' if result['verified'] else 'NO'}"
              + (f" (match={result['match']}, creation={result['creation_match']}, "
                 f"runtime={result['runtime_match']})" if result["verified"] else
                 " — contract source is NOT verified on Sourcify"))
        if result["contract_name"]:
            print(f"Contract: {result['contract_name']}")
        if result["contracts"]:
            print(f"Contracts in source: {', '.join(result['contracts'])}")
        if result["source_files"]:
            print(f"Source files: {', '.join(result['source_files'])}")
        if result["functions"]:
            print(f"Functions ({len(result['functions'])} shown): "
                  f"{', '.join(result['functions'])}")
    return 0


def cmd_video(args: argparse.Namespace) -> int:
    try:
        result = build_video(args.clips, args.audio, args.text, args.out)
    except VideoError as exc:
        print(f"video: FAILED — {exc}", file=sys.stderr)
        return 1
    print(f"Done: {result['out']} ({result['duration']:.1f}s; "
          f"30s when each clip is {CLIP_SECONDS}s or longer)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(ABOUT_LINE)
        return 0
    if args.command == "boards":
        return cmd_boards(args)
    if args.command == "square":
        return cmd_square(args)
    if args.command == "patrol":
        return cmd_patrol(args)
    if args.command == "recon":
        return cmd_recon(args)
    if args.command == "video":
        return cmd_video(args)
    if args.command == "about":
        print(ABOUT_LINE)
        print("Read-only ops CLI: bounty boards, Binance movers, patrol "
              "health checks, Sourcify recon, 9:16 video assembly.")
        print("No keys, no signing, no spending. Public endpoints only.")
        return 0
    parser.print_help()
    return 0
