# IDAWATI Ops

![ModtDoctor Team logo](assets/logo.png)

> Created by ModtDoctor Team

An all-in-one ops CLI for a solo crypto AI-agent operator. One tool that
combines the daily workflows of running an agent operation:

- **boards** — poll the public agent-bounty boards (task-bounty, gofrantic, opire)
- **square** — top 24h USDT movers from Binance public market data
- **patrol** — read-only health snapshot: BSC wallet balance + Flop testnet status
- **recon** — check a contract's Sourcify verification status (read-only)
- **video** — assemble 3 clips + audio + end card into a 30s 9:16 video (ffmpeg)

## Safety first — read-only by design

- **No keys, no seeds, no passwords, ever.** The tool never asks for, reads,
  or stores any credential.
- **Public endpoints only, no auth.** Every network call is an unauthenticated
  read of a public API. There is no wallet connect, no signing, no spending,
  no submitting anything.
- **No faked data.** If a board or endpoint cannot be read, the command says
  so (`UNREADABLE` / `FAIL`) instead of inventing a result.

## Use it yourself

No account, no login, no API key needed. You only need Python 3.10+ and
ffmpeg (for the `video` command).

```bash
git clone https://github.com/Ibnu3456787/idawati-ops.git
cd idawati-ops
pip install -r requirements.txt
```

Run it with `python -m idawati_ops <command>` (or `idawati-ops <command>`
after `pip install -e .`).

### boards — agent-bounty boards

```bash
python -m idawati_ops boards
python -m idawati_ops boards --json
```

Lists open bounties from task-bounty, gofrantic (public MCP board) and
opire as a table. Exit code is 0 when all three boards were readable, 1
when any board failed. Only what the live responses return is shown.

### square — top Binance movers

```bash
python -m idawati_ops square
python -m idawati_ops square --min-volume 10000000 --limit 5
python -m idawati_ops square --json
```

Top 24h USDT movers by percent change, filtered to 24h quote volume above
$5M by default. Data comes from Binance's public market-data mirror
(`data-api.binance.vision`).

### patrol — health snapshot

```bash
python -m idawati_ops patrol --wallet 0xYourWalletAddressHere
python -m idawati_ops patrol --wallet 0xYourWalletAddressHere --json
```

Checks your BSC wallet balance via a public BSC RPC and the Flop testnet
endpoints (faucet chain info, gateway models, and whether the public
testnet page still says "unscored"). Each check prints `OK`/`FAIL` with
its evidence. Pass **your own** wallet address with `--wallet` — there is
no default.

### recon — Sourcify verification check

```bash
python -m idawati_ops recon 0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c --chain bsc
python -m idawati_ops recon 0xYourContractAddress --chain eth
```

Reports whether a contract's source is verified on Sourcify (API v2),
plus the contract and function names found in the published source. An
unverified contract is reported plainly as unverified.

### video — assemble a 30s 9:16 video

```bash
python -m idawati_ops video \
  --clips clip1.mp4 clip2.mp4 clip3.mp4 \
  --audio music.wav \
  --text "animator: by. YourName" \
  --out out.mp4
```

Builds a 30-second 704x1248 video: three 9-second clips (crop-fill, full
frame, no blur bands) plus a 3-second end card (solid maroon background,
gold lines, your credit text in bold serif). Audio is prepared separately
and muxed in. You supply your own clips and audio — the tool generates no
media. Requires ffmpeg + ffprobe in `PATH`. Pass your own end-card text
with `--text` — there is no default.

### about

```bash
python -m idawati_ops about
python -m idawati_ops --version
```

```
IDAWATI Ops 1.0.0 — Created by ModtDoctor Team — MIT License
```

## Not included, by design

These need each operator's own private credentials, so they are
deliberately **out of scope** for this tool and will never be added as
silent defaults:

- **Posting to Binance Square** — needs your own Binance API key.
- **Telegram / X actions** (follow, like, repost, comment) — need your own
  logins on your own device.
- **Auto-claiming or submitting bounties** — needs your own board accounts.
- **Anything that signs, approves, or spends** — this tool never will.

## Roadmap

- **v1 (this release):** boards, square, patrol, recon, video. Read-only.
- **v2 (planned):** X/Telegram task helpers that run against *your own*
  logged-in session; video image-to-video generation (needs a paid media
  API key — out of scope for v1); board watch mode with a local seen-file.

## Development

```bash
python -m unittest discover -s tests -v   # unit tests (stdlib only)
python -m idawati_ops --help              # every command has --help
```

Live smoke-test results from the build machine are recorded in
[`SMOKE-20261127.md`](SMOKE-20261127.md) — real outputs, including the
failures found and fixed during testing.

## License

MIT — see [LICENSE](LICENSE).

---

Created by ModtDoctor Team — IDAWATI Ops, MIT License.
