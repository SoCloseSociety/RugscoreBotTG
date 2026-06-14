# NEO_CONNECTOR -- RugScore Bot (RugscoreBotTG)
- service: rugscore
- base_url_prod: N/A (no inbound HTTP API -- pure Telegram bot, long-polling)
- auth: none (HTTP) ; bot auth is Telegram-side via TELEGRAM_BOT_TOKEN ; admin commands gated by ADMIN_IDS
- env_required: [TELEGRAM_BOT_TOKEN, BOT_USERNAME, HELIUS_API_KEY, ADMIN_IDS, SOLANA_RPC_URL, DATABASE_URL, CHANNEL_ID, DONATE_WALLET, CACHE_TTL_SECONDS, ANALYSIS_TIMEOUT_SECONDS, MAX_CONCURRENT_ANALYSES, LOG_LEVEL]
- generated_at:

## IMPORTANT -- No HTTP API
This project exposes **no inbound HTTP/REST/webhook/SSE/WebSocket surface**. It is a Telegram
bot that runs via **long-polling** (`app.run_polling(drop_pending_updates=True)` in
`bot/main.py:319`), built with `python-telegram-bot` (`ApplicationBuilder`, `bot/main.py:242`).
There is no FastAPI/Flask/Express/aiohttp web server, no `set_webhook`, and no listening port.

Therefore NeoBot **cannot call this service over HTTP**. Neo can only interact with it the way
any user does: by sending Telegram commands/messages to the bot account (`BOT_USERNAME`). The
"endpoints" below are the bot's **Telegram command surface** (the closest machine-actionable
contract), documented so Neo knows what the bot can do and how to drive it via Telegram.

The actual HTTP traffic this project makes is **outbound** (it consumes external APIs:
DexScreener, Helius DAS/RPC, Solana RPC, Jupiter, Pump.fun, RugCheck) -- see ## Outbound APIs.

## Endpoints
> These are Telegram bot commands, not HTTP routes. Registered in `bot/main.py:251-266`.
> "input" = command arguments. There is no JSON request/response; responses are Telegram
> HTML messages (and inline keyboards). Handlers live in `bot/handlers/`.

### CMD /start
- auth: no (any Telegram user)
- async: false
- input: none
- output: welcome message + main menu inline keyboard (`bot/handlers/start.py`)
- errors: none specific
- example_curl: N/A -- send Telegram message `/start` to @BOT_USERNAME

### CMD /help
- auth: no
- async: false
- input: none
- output: help text describing commands (`bot/handlers/start.py:help_command`)
- errors: none
- example_curl: N/A -- `/help`

### CMD /scan <token_mint>
- auth: no
- async: false (single reply, but internally runs the 8-criteria analysis engine in parallel)
- input: | param | type | required | description |
         | token_mint | string (Solana base58 mint, 32-44 chars) | yes | token contract address to analyze |
         (parsed at `bot/handlers/analyze.py:40` via `context.args[0]`; if missing -> usage prompt)
- output: Telegram HTML message with safety score 0-100, risk label, per-criterion breakdown,
          + inline keyboard (refresh / watch / dev wallet / holders). Built by `analysis/engine.py`
          + `bot/formatters/display.py`.
- errors: usage message if no arg; "analysis failed/timeout" reply on engine error/timeout
          (ANALYSIS_TIMEOUT_SECONDS)
- example_curl: N/A -- `/scan So11111111111111111111111111111111111111112`

### CMD /quick <token_mint>
- auth: no
- async: false
- input: | param | type | required | description |
         | token_mint | string (Solana base58 mint) | yes | token to analyze (lightweight) |
         (`bot/handlers/quick.py:28`)
- output: condensed score message (faster/lighter than /scan)
- errors: usage message if no arg
- example_curl: N/A -- `/quick <CA>`

### CMD /watch <token_mint>
- auth: no
- async: false
- input: | token_mint | string (base58) | yes | token to add to caller's watchlist | (`bot/handlers/watch.py:34`)
- output: confirmation; persists to DB (per-user watchlist). Threshold via threshold_ callbacks.
- errors: usage if no arg; "Failed to add to watchlist" on DB error (`watch.py:95`)
- example_curl: N/A -- `/watch <CA>`

### CMD /unwatch <token_mint>
- auth: no
- async: false
- input: | token_mint | string (base58) | yes | token to remove from watchlist | (`bot/handlers/watch.py:105`)
- output: confirmation; "You have no watchlist" / "Failed to remove" on edge cases
- errors: usage if no arg
- example_curl: N/A -- `/unwatch <CA>`

### CMD /watchlist
- auth: no
- async: false
- input: none
- output: caller's watched tokens with current scores + refresh_watchlist inline button (`bot/handlers/watch.py`)
- errors: "Failed to load watchlist" on DB error
- example_curl: N/A -- `/watchlist`

### CMD /wallet <address>
- auth: no
- async: false
- input: | address | string (Solana base58 wallet) | yes | wallet to inspect (dev/holder history) | (`bot/handlers/wallet.py:31`)
- output: wallet analysis message
- errors: usage if no arg
- example_curl: N/A -- `/wallet <wallet_address>`

### CMD /trending
- auth: no
- async: false
- input: none
- output: trending tokens report (`bot/handlers/trending.py`)
- errors: none specific
- example_curl: N/A -- `/trending`

### CMD /myid
- auth: no
- async: false
- input: none
- output: caller's Telegram user ID (`bot/handlers/myid.py`)
- errors: none
- example_curl: N/A -- `/myid`

### CMD /donate
- auth: no
- async: false
- input: none
- output: donation message with DONATE_WALLET SOL address (`bot/handlers/donate.py`)
- errors: none (shows configured wallet or nothing if unset)
- example_curl: N/A -- `/donate`

### CMD /settings
- auth: no
- async: false
- input: none
- output: settings menu inline keyboard (settings_ + threshold_ callbacks) (`bot/handlers/settings.py`)
- errors: none
- example_curl: N/A -- `/settings`

### CMD /stats
- auth: no
- async: false
- input: none
- output: usage/scan statistics message (`bot/handlers/stats.py`)
- errors: none specific
- example_curl: N/A -- `/stats`

### CMD /broadcast <message...>  [ADMIN ONLY]
- auth: yes -- caller's Telegram id must be in ADMIN_IDS (`settings.is_admin`, `bot/handlers/admin.py:36`)
- async: false (sends to all users; shows "Broadcasting..." progress)
- input: | message | string (rest of args joined) | yes | text broadcast to all bot users | (`admin.py:47`)
- output: "Admin only ser." if not admin; otherwise broadcast progress/result
- errors: "Admin only" (not authorized); usage if no message
- example_curl: N/A -- `/broadcast <text>`

### CMD /health  [ADMIN ONLY]
- auth: yes -- ADMIN_IDS (`bot/handlers/admin.py:79`)
- async: false
- input: none
- output: health/diagnostics text (RPC, cache, DB status)
- errors: "Admin only ser."
- example_curl: N/A -- `/health`

### CMD /testreports  [ADMIN ONLY]
- auth: yes -- ADMIN_IDS (`bot/handlers/admin.py:111`)
- async: false
- input: none
- output: triggers test channel reports
- errors: "Admin only ser."
- example_curl: N/A -- `/testreports`

### INLINE  @BOT_USERNAME <token_mint>
- auth: no
- async: false
- input: inline query text = Solana mint address (`InlineQueryHandler`, `bot/main.py:284`; handler `bot/handlers/inline.py`)
- output: inline result card with score, shareable in any chat
- errors: empty/invalid -> no/placeholder result
- example_curl: N/A -- type `@BOT_USERNAME <CA>` in any Telegram chat

### AUTO-DETECT  (private chat, plain message)
- auth: no
- async: false
- input: any non-command text in a **private** chat; if it contains a Solana address it is scanned
         (`MessageHandler` filter `TEXT & ~COMMAND & ChatType.PRIVATE`, `bot/main.py:289`; handler
         `auto_detect_handler` in `bot/handlers/analyze.py:50`). Disabled in groups to prevent spam.
- output: same as /scan
- errors: ignored if no address found
- example_curl: N/A -- DM a contract address to the bot

### CALLBACK BUTTONS (inline keyboard taps)
- Registered in `bot/main.py:270-281`; not user-typed commands. Patterns:
  `refresh_<mint>`, `scan_<mint>`, `watch_<mint>`, `dev_<mint>`, `holders_<mint>`,
  `refresh_watchlist`, `threshold_<n>`, `admin_*` (admin-gated in `callback_admin`), `settings_*` (no-op ack).

### SCHEDULED JOBS (internal cron, not callable)
- `post_trending_report` + `post_most_scanned_report` posted to CHANNEL_ID via PTB `job_queue.run_repeating`
  (`bot/main.py:295-310`). Only active if CHANNEL_ID is set. Intervals TRENDING_INTERVAL /
  MOST_SCANNED_INTERVAL (defined in `config/constants.py`). Not externally triggerable except admin `/testreports`.

## Flows
- **Scan (synchronous, no poll):** user sends `/scan <CA>` -> `analysis/engine.py` runs Phase 1
  parallel data fetch (DexScreener, Helius DAS, Solana RPC, etc.) -> Phase 2 parallel 8-criteria
  scoring -> Phase 3 weighted composite + risk label -> cached (CACHE_TTL_SECONDS, default 60s) +
  written to DB -> single Telegram HTML reply with inline keyboard. There is **no async
  generate->poll->result** pattern; it is one request/one reply bounded by ANALYSIS_TIMEOUT_SECONDS.
- **Watch:** `/watch <CA>` persists per-user entry to SQLite (DATABASE_URL); scheduled/monitoring
  logic (`monitoring/watcher.py`, `monitoring/alerts.py`) compares scores and pushes alerts via the bot.

## Outbound APIs (consumed by this project -- for Neo's awareness, NOT endpoints Neo can call here)
- DexScreener -- price/liquidity/volume/socials (`data/dexscreener.py`)
- Helius DAS API -- `https://api.helius.xyz/v0` and RPC `https://mainnet.helius-rpc.com/?api-key=...`
  (built in `config/settings.py` `helius_api_url` / `helius_rpc_url`; needs HELIUS_API_KEY) (`data/helius_client.py`)
- Solana RPC -- SOLANA_RPC_URL fallback, default `https://api.mainnet-beta.solana.com` (`data/solana_rpc.py`, `utils/rpc_rotator.py`)
- Jupiter (`data/jupiter.py`), Pump.fun (`data/pumpfun.py`), RugCheck (`data/rugcheck_client.py`), social checks (`data/social_checker.py`)

## Gaps
- **base_url_prod = N/A**: no HTTP server exists in code. If a future REST wrapper is added it must be re-audited.
- **CHANNEL_ID / DONATE_WALLET**: optional; behavior (reports / donate) only active when set. Confirmed optional in `.env.example` and `config/settings.py`.
- **Job intervals** (TRENDING_INTERVAL, MOST_SCANNED_INTERVAL): exact values not inlined here -- defined in `config/constants.py` (verify there).
- **DB schema** (watchlist/stats tables): not enumerated in this manifest -- see `database/` for models if Neo needs row-level access (out of scope; SQLite, not network-reachable).
- **No auth header / API key for inbound calls** because there is no inbound API. Neo integration = Telegram messaging only (would require a Telegram client + the bot username, not an HTTP tool).

## Récap
- Endpoints found: 0 HTTP endpoints. 17 Telegram commands (3 admin-only) + 1 inline mode + 1 auto-detect + 8 callback patterns + 2 scheduled jobs.
- Async (generate->poll->result): 0.
- Coverage vs NeoBot integrations.py: NEW and **not wirable as an HTTP tool** -- this is a polling Telegram bot with no callable HTTP surface. Recommend NOT adding rugscore_* HTTP tools; if interaction is desired, it requires a Telegram-client-based connector, which is a different integration class.
