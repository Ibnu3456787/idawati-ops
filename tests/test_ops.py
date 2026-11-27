"""Unit tests for IDAWATI Ops — pure functions only (no network)."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from idawati_ops.format import render_table
from idawati_ops.square import filter_sort_tickers
from idawati_ops.boards import (
    parse_gofrantic_board,
    parse_mcp_response,
    parse_opire_rewards,
    parse_task_bounty,
)
from idawati_ops.recon import build_sourcify_url, parse_sources
from idawati_ops.patrol import is_valid_address, wei_to_bnb
from idawati_ops.video import endcard_filter, escape_drawtext, segment_filter


class TestFormat(unittest.TestCase):
    def test_table_aligns_columns(self):
        out = render_table(["A", "BB"], [["x", "yy"], ["longer", "z"]])
        lines = out.splitlines()
        self.assertEqual(lines[0], "A       BB")
        self.assertEqual(lines[1], "------  --")
        self.assertEqual(lines[2], "x       yy")

    def test_empty_rows(self):
        out = render_table(["A"], [])
        self.assertIn("(no rows)", out)


class TestSquare(unittest.TestCase):
    def test_filters_by_volume_and_symbol(self):
        tickers = [
            {"symbol": "AAAUSDT", "lastPrice": "1", "priceChangePercent": "5",
             "quoteVolume": "6000000"},
            {"symbol": "BBBUSDT", "lastPrice": "2", "priceChangePercent": "50",
             "quoteVolume": "100000"},  # below $5M floor
            {"symbol": "CCCUSD", "lastPrice": "3", "priceChangePercent": "99",
             "quoteVolume": "9000000"},  # not a USDT pair
            {"symbol": "DDDUSDT", "lastPrice": "4", "priceChangePercent": "10",
             "quoteVolume": "7000000"},
            {"symbol": "EEEUSDT", "lastPrice": "bad", "priceChangePercent": "1",
             "quoteVolume": "7000000"},  # unparseable price
        ]
        rows = filter_sort_tickers(tickers)
        self.assertEqual([r["symbol"] for r in rows], ["DDDUSDT", "AAAUSDT"])
        self.assertEqual(rows[0]["change_pct"], 10.0)
        self.assertEqual(rows[0]["quote_volume"], 7_000_000.0)

    def test_limit(self):
        tickers = [
            {"symbol": f"T{i}USDT", "lastPrice": "1",
             "priceChangePercent": str(i), "quoteVolume": "6000000"}
            for i in range(5)
        ]
        self.assertEqual(len(filter_sort_tickers(tickers, limit=2)), 2)


class TestBoards(unittest.TestCase):
    def test_task_bounty_empty(self):
        self.assertEqual(parse_task_bounty({"data": [], "meta": {}}), [])

    def test_task_bounty_row(self):
        rows = parse_task_bounty({"data": [{"id": 7, "title": "Do X",
                                            "reward": 25, "status": "open",
                                            "url": "https://example.com"}]})
        self.assertEqual(rows[0]["reward"], "$25.00")
        self.assertEqual(rows[0]["platform"], "task-bounty")

    def test_mcp_response_plain_json(self):
        raw = {"result": {"content": [{"type": "text", "text": '{"ok": true}'}]}}
        self.assertEqual(parse_mcp_response(raw), raw["result"])

    def test_mcp_response_sse(self):
        raw = 'event: message\ndata: {"result": {"ok": true}}\n\n'
        self.assertEqual(parse_mcp_response(raw), {"ok": True})

    def test_gofrantic_board_parses_double_json(self):
        inner = {
            "ok": True,
            "board": {"bounties": [
                {"number": 97, "title": "First bounty", "price_usd": 10,
                 "work_status": "open", "url": "https://example.com/b/97"}]},
        }
        import json
        result = {"content": [{"type": "text", "text": json.dumps(inner)}]}
        rows = parse_gofrantic_board(result)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "97")
        self.assertEqual(rows[0]["reward"], "$10.00")

    def test_opire_rewards_cents(self):
        rows = parse_opire_rewards([
            {"id": "01KSXXX60RR76RSSXZXD0F4AGF", "title": "c1work",
             "url": "https://github.com/x/y/issues/1",
             "pendingPrice": {"value": 10000, "unit": "USD_CENT"},
             "claimerUsers": [{"id": "a"}], "tryingUsers": [],
             "programmingLanguages": ["Rust"]},
        ])
        self.assertEqual(rows[0]["reward"], "$100.00")
        self.assertEqual(rows[0]["status"], "claimers 1 / trying 0")
        self.assertEqual(rows[0]["id"], "01KSXXX60RR7")


class TestRecon(unittest.TestCase):
    def test_sourcify_url(self):
        self.assertEqual(
            build_sourcify_url("bsc", "0xabc"),
            "https://sourcify.dev/server/v2/contract/56/0xabc"
            "?fields=sources,metadata",
        )
        self.assertEqual(
            build_sourcify_url("eth", "0xabc").split("/")[6], "1"
        )

    def test_parse_sources(self):
        sources = {
            "Token.sol": {"content": (
                "contract MyToken is ERC20 {\n"
                "  function transfer(address to, uint256 v) public {}\n"
                "  function balanceOf(address a) public view returns (uint256) {}\n"
                "}\n"
                "library SafeMath { function add(uint a, uint b) internal pure {} }"
            )},
            "README.md": {"content": "function notAFunction()"},
        }
        contracts, functions = parse_sources(sources)
        self.assertEqual(contracts, ["MyToken", "SafeMath"])
        self.assertEqual(functions, ["add", "balanceOf", "transfer"])

    def test_parse_sources_ignores_comments(self):
        sources = {
            "A.sol": {"content": (
                "// This contract presents a definition that displays\n"
                "/* contract FakeOne { function nope() } */\n"
                "contract RealOne { function go() public {} }"
            )},
        }
        contracts, functions = parse_sources(sources)
        self.assertEqual(contracts, ["RealOne"])
        self.assertEqual(functions, ["go"])


class TestPatrol(unittest.TestCase):
    def test_valid_address(self):
        self.assertTrue(is_valid_address("0x" + "a" * 40))
        self.assertFalse(is_valid_address("0x123"))
        self.assertFalse(is_valid_address("not an address"))
        self.assertFalse(is_valid_address(""))

    def test_wei_to_bnb(self):
        self.assertEqual(wei_to_bnb("0xde0b6b3a7640000"), "1")
        self.assertEqual(wei_to_bnb("0x0"), "0")
        self.assertEqual(wei_to_bnb("0x3d77a0500"), "0.0000000165")


class TestVideo(unittest.TestCase):
    def test_segment_filter(self):
        f = segment_filter()
        self.assertIn("scale=704:1248", f)
        self.assertIn("crop=704:1248", f)
        self.assertIn("fps=30", f)
        self.assertNotIn("blur", f)
        self.assertNotIn("pad", f)

    def test_escape_drawtext(self):
        self.assertEqual(escape_drawtext("a:b%c'd\\e"), "a\\:b\\%c\\'d\\\\e")

    def test_endcard_filter(self):
        from idawati_ops.video import endcard_input
        self.assertIn("6B1F2A", endcard_input())
        f = endcard_filter("animator: by. TestName", "/some/font.ttf")
        self.assertIn("D4AF37", f)
        self.assertIn("animator\\: by. TestName", f)
        self.assertIn("fontfile=/some/font.ttf", f)
        self.assertIn("drawbox", f)
        self.assertIn("drawtext", f)


if __name__ == "__main__":
    unittest.main()
