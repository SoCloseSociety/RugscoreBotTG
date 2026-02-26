"""Constants for scoring weights, thresholds, known addresses, and risk labels."""

# ─── Scoring Weights (must sum to 1.0) ───
SCORING_WEIGHTS = {
    "contract": 0.20,
    "liquidity": 0.15,
    "holders": 0.15,
    "dev_wallet": 0.15,
    "volume": 0.10,
    "social": 0.10,
    "metadata": 0.05,
    "smart_money": 0.10,
}

# ─── Risk Labels (degen culture) ───
RISK_LABELS = {
    (90, 100): {"emoji": "\U0001f7e2", "label": "SAFU", "desc": "Diamond hands approved \u2014 all checks passed \U0001f48e"},
    (70, 89): {"emoji": "\U0001f7e1", "label": "LOOKS GOOD", "desc": "Decent play \u2014 DYOR ser"},
    (50, 69): {"emoji": "\U0001f7e0", "label": "SKETCHY", "desc": "Multiple red flags \u2014 ape with caution"},
    (25, 49): {"emoji": "\U0001f534", "label": "DANGER", "desc": "High rug risk \u2014 don't ape blindly"},
    (0, 24): {"emoji": "\u26d4", "label": "LIKELY RUG", "desc": "Stay away fren \u2014 you'll get rekt"},
}

# ─── Known Addresses ───
BURN_ADDRESSES = [
    "1nc1nerator11111111111111111111111111111111",
    "11111111111111111111111111111111",             # System program (null account)
    "1111111111111111111111111111111112",            # Solana native burn
]

RAYDIUM_AUTHORITY = "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1"

PUMP_FUN_BONDING_CURVE = "Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1"
PUMP_FUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMP_FUN_AUTHORITY = "TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM"

KNOWN_EXCLUDE_ADDRESSES = set(BURN_ADDRESSES + [RAYDIUM_AUTHORITY, PUMP_FUN_BONDING_CURVE])

# Program addresses that are NOT real wallets/creators
KNOWN_PROGRAM_ADDRESSES = {
    PUMP_FUN_PROGRAM,
    PUMP_FUN_AUTHORITY,
    PUMP_FUN_BONDING_CURVE,
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",   # SPL Token program
    "11111111111111111111111111111111",                  # System program
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",   # ATA program
    "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s",    # Metaplex Metadata
}

# ─── Liquidity Thresholds ───
LIQUIDITY_EXCELLENT = 50_000
LIQUIDITY_GOOD = 10_000
LIQUIDITY_LOW = 5_000

MCAP_LIQ_RATIO_HEALTHY = 10
MCAP_LIQ_RATIO_CAUTION = 30

# ─── Holder Thresholds ───
TOP10_CONCENTRATION_EXCELLENT = 25
TOP10_CONCENTRATION_CAUTION = 50

TOP1_HOLDER_EXCELLENT = 5
TOP1_HOLDER_OK = 15

HOLDER_COUNT_GOOD = 500
HOLDER_COUNT_MODERATE = 100
HOLDER_COUNT_LOW = 50

# ─── Volume Thresholds ───
VOLUME_TX_ACTIVE = 200
VOLUME_TX_MODERATE = 50

BUY_SELL_RATIO_MIN = 0.35
BUY_SELL_RATIO_MAX = 0.65

VOLUME_MCAP_HEALTHY_MIN = 0.1
VOLUME_MCAP_HEALTHY_MAX = 2.0
VOLUME_MCAP_SUSPICIOUS = 5.0

# ─── Dev Wallet Thresholds ───
WALLET_AGE_ESTABLISHED = 30  # days
WALLET_AGE_MODERATE = 7  # days

TOKEN_FARM_THRESHOLD = 10  # tokens created

# ─── Social Thresholds ───
TWITTER_FOLLOWERS_GOOD = 500
TWITTER_FOLLOWERS_GREAT = 1000
TWITTER_AGE_ESTABLISHED = 30  # days
TWITTER_AGE_SUSPICIOUS = 7  # days

WEBSITE_DOMAIN_AGE_ESTABLISHED = 30  # days
WEBSITE_DOMAIN_AGE_SUSPICIOUS = 7  # days

# ─── Metadata Thresholds ───
DESCRIPTION_MIN_LENGTH = 50

# ─── Smart Money Thresholds ───
SMART_MONEY_STRONG = 3
SMART_MONEY_MODERATE = 1
WHALE_THRESHOLD_PCT = 5.0

# ─── RPC Endpoints (free) ───
FALLBACK_RPC_ENDPOINTS = [
    "https://api.mainnet-beta.solana.com",
    "https://solana-mainnet.rpc.extrnode.com",
]

# ─── Rate Limits ───
RATE_LIMITS = {
    "helius": {"max_concurrent": 10, "per_second": 50},
    "dexscreener": {"max_concurrent": 5, "per_second": 5},
    "solana_rpc": {"max_concurrent": 5, "per_second": 10},
    "http_scrape": {"max_concurrent": 3, "per_second": 2},
}

# ─── Cache TTLs ───
CACHE_TTL_ANALYSIS = 60  # seconds
CACHE_TTL_DEX_DATA = 30
CACHE_TTL_HOLDER_DATA = 120
CACHE_TTL_SOCIAL = 300

# ─── Known Token Names (for copycat detection) ───
KNOWN_TOKEN_NAMES = [
    "PEPE", "DOGE", "SHIB", "BONK", "WIF", "FLOKI", "MEME",
    "BITCOIN", "ETHEREUM", "SOLANA", "SOL", "BTC", "ETH",
    "TRUMP", "BODEN", "TREMP",
]

# ─── Test Tokens ───
TEST_TOKEN_BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
TEST_TOKEN_WIF = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
