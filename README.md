<p align="center">
  <img src="https://raw.githubusercontent.com/SoCloseSociety/RugscoreBotTG/main/assets/banner.svg" alt="RugScore — Solana Anti-Rug Scanner" width="900">
</p>

<p align="center">
  <strong>The fastest anti-rug scanner on Solana — 8-criteria deep analysis, real-time on-chain data, 100% free.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Solana-anti--rug-9945FF?style=flat-square&logo=solana&logoColor=white" alt="Solana">
  <img src="https://img.shields.io/badge/Telegram-bot-26A5E4?style=flat-square&logo=telegram&logoColor=white" alt="Telegram Bot">
  <img src="https://img.shields.io/badge/scoring-8_criteria-FF4500?style=flat-square" alt="8 Criteria">
  <img src="https://img.shields.io/badge/cost-$0%2Fmo-brightgreen?style=flat-square" alt="Zero Cost">
  <img src="https://img.shields.io/badge/Python-3.9+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker">
</p>

---

## What is RugScore?

RugScore is a **Telegram bot** that scans any Solana token and returns an instant **safety score from 0 to 100** based on 8 weighted criteria. It fetches real on-chain data, analyzes contract security, liquidity health, holder distribution, developer wallet history, and more — all in seconds.

Paste a contract address. Get a score. Know before you ape.

```
Token CA
  │
  ▼
Phase 1 — Parallel data fetch (5 simultaneous calls)
  ├── DexScreener API    (price, liquidity, volume, socials)
  ├── Helius DAS API     (metadata, authorities, creator)
  ├── Solana RPC         (top holders, supply, mint data)
  └── ...
  │
  ▼
Phase 2 — Parallel scoring (8 criteria, individual timeouts)
  ├── Contract Safety      20%
  ├── Liquidity Health     15%
  ├── Holder Distribution  15%
  ├── Dev Wallet History   15%
  ├── Volume Authenticity  10%
  ├── Social Legitimacy    10%
  ├── Smart Money Signal   10%
  └── Metadata Quality      5%
  │
  ▼
Phase 3 — Weighted composite score + risk label
  │
  ▼
Cache (60s) + Database + Telegram HTML response
```

---

## Features

- **8-criteria scoring engine** — Contract, Liquidity, Holders, Dev Wallet, Volume, Social, Metadata, Smart Money
- **Auto-detect** — Paste a Solana address in DM, instant analysis
- **Inline mode** — Type `@YourBot <CA>` in any chat for instant score sharing
- **Watchlist** — Track tokens and get alerts on score changes
- **Dev wallet analysis** — Creator history, rug pattern detection, token farm detection
- **Smart money tracking** — Detect whale wallets and known profitable traders
- **Trending** — Top 10 recently scanned tokens
- **Channel reports** — Automated trending & most-scanned reports to your Telegram channel
- **Group support** — Works in group chats with anti-spam guards
- **Deep links** — DexScreener, Solscan, RugCheck, Axiom, GMGN in every scan result
- **Zero cost** — Runs entirely on free APIs (Solana RPC, Helius free tier, DexScreener)
- **Docker ready** — One-command deployment

---

## Risk Levels

| Score | Label | Meaning |
|-------|-------|---------|
| 90-100 | SAFU | Diamond hands approved — all checks passed |
| 70-89 | LOOKS GOOD | Decent play — DYOR ser |
| 50-69 | SKETCHY | Multiple red flags — ape with caution |
| 25-49 | DANGER | High rug risk — don't ape blindly |
| 0-24 | LIKELY RUG | Stay away fren — you'll get rekt |

---

## Commands

| Command | Description |
|---------|-------------|
| `/scan <CA>` | Full 8-criteria deep scan with detailed breakdown |
| `/quick <CA>` | Lightning fast score (contract + liquidity + holders) |
| `/watch <CA>` | Add token to watchlist — get alerts on changes |
| `/unwatch <CA>` | Remove from watchlist |
| `/watchlist` | View all tracked tokens |
| `/wallet <addr>` | Deep check on a developer wallet |
| `/trending` | Top 10 recently scanned tokens |
| `/settings` | Configure alert threshold |
| `/donate` | Tip the devs |
| `/stats` | Usage statistics |

**Auto-detect**: paste any Solana CA directly in DM — the bot scans it automatically.

---

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/SoCloseSociety/RugscoreBotTG.git
cd RugscoreBotTG
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your keys:

```env
# REQUIRED — get from @BotFather on Telegram
TELEGRAM_BOT_TOKEN=your_token_here
BOT_USERNAME=YourBotName

# REQUIRED — free at helius.dev
HELIUS_API_KEY=your_key_here

# Your Telegram user ID (get via @userinfobot)
ADMIN_IDS=123456789
```

### 3. Run

```bash
python run.py
```

Or use the launcher script:

```bash
chmod +x run.sh
./run.sh
```

---

## Docker Deployment

```bash
cp .env.example .env
# Edit .env with your keys

docker compose up -d --build
```

Manage with `deploy.sh`:

```bash
./deploy.sh start     # Build & start
./deploy.sh stop      # Stop
./deploy.sh restart   # Rebuild & restart
./deploy.sh logs      # Tail logs
./deploy.sh update    # Git pull + rebuild
```

---

## Project Structure

```
RugscoreBotTG/
├── analysis/                # Scoring engine
│   ├── criteria/            # 8 individual criteria modules
│   │   ├── contract.py      # Mint/freeze authority, transfer fee
│   │   ├── liquidity.py     # LP burn, MCap/Liq ratio
│   │   ├── holders.py       # Top 10 concentration, snipers
│   │   ├── dev_wallet.py    # Wallet age, rug pattern detection
│   │   ├── volume.py        # Volume/MCap ratio, buy/sell balance
│   │   ├── social.py        # Twitter, Telegram, Website validation
│   │   ├── metadata.py      # Copycat detection (fuzzy matching)
│   │   └── smart_money.py   # Whale wallets, smart money signals
│   ├── engine.py            # Orchestrator (parallel fetch + scoring)
│   └── scoring.py           # Weighted composite score
├── bot/                     # Telegram interface
│   ├── main.py              # Bot entry point
│   ├── handlers/            # Command handlers (/scan, /quick, /watch...)
│   ├── formatters/          # HTML response formatting
│   ├── keyboards/           # Inline buttons
│   └── jobs/                # Scheduled channel reports
├── data/                    # External API clients
│   ├── solana_rpc.py        # Solana RPC (free)
│   ├── helius_client.py     # Helius DAS API
│   ├── dexscreener.py       # DexScreener (free)
│   ├── social_checker.py    # Twitter/TG/Website validation
│   └── cache.py             # In-memory TTL cache
├── database/                # SQLAlchemy models
├── smart_money/             # Smart money wallet tracking
├── monitoring/              # Watchlist alerts
├── config/                  # Settings + scoring constants
├── utils/                   # Helpers, rate limiter, RPC rotation
├── Dockerfile
├── docker-compose.yml
└── deploy.sh
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Bot framework | python-telegram-bot 21.7 (async) |
| HTTP client | httpx (async) |
| Database | SQLAlchemy 2.0 + aiosqlite |
| Blockchain | Solana RPC (free) + Helius DAS API |
| Market data | DexScreener API (free) |
| Config | pydantic-settings + .env |
| Fuzzy matching | fuzzywuzzy + python-Levenshtein |
| Serialization | orjson |
| Runtime | Python 3.9+ |
| Deployment | Docker |

---

## Data Sources

| Source | Cost | Data |
|--------|------|------|
| Solana RPC | Free | Accounts, supply, holders, transactions |
| Helius DAS | Free tier | Metadata, authorities, creator, holder count |
| DexScreener | Free | Price, liquidity, volume, pairs, socials |
| Twitter/X | Free (scraping) | Accessibility, follower estimation |
| Telegram | Free (scraping) | Accessibility, member estimation |

---

## Resilience

- **Per-criterion timeouts** — a slow criterion doesn't block others
- **Pre-loaded data** — Phase 1 shares data with Phase 2 (no redundant fetches)
- **Fallbacks** — if RPC fails, DexScreener provides estimates
- **Neutral scoring** — missing criteria count as 50/100
- **Multi-pair aggregation** — liquidity summed across all DEXs
- **RPC rotation** — automatic failover to backup endpoints
- **Multi-layer cache** — TTL adapted by data type (30s-600s)

---

## Contributing

Contributions welcome! Feel free to open issues and pull requests. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <sub>Built by <a href="https://github.com/SoCloseSociety"><strong>SoClose Society</strong></a> — Digital Innovation Through Automation & AI</sub>
</p>
