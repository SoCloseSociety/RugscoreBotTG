# CLAUDE.md -- RugScore Bot (RugscoreBotTG)

RugScore is a **Telegram bot** (python-telegram-bot, long-polling) that scores Solana tokens
0-100 across 8 anti-rug criteria. It has **no inbound HTTP API** -- it consumes external APIs
(DexScreener, Helius, Solana RPC, Jupiter, Pump.fun, RugCheck) and replies over Telegram.

## Neo Connector (auto)
Ce projet expose `NEO_CONNECTOR.md` : le manifeste machine-lisible de TOUS ses
endpoints/auth/env, consommé par NeoBot pour se câbler automatiquement.
- RÈGLE : à chaque ajout/suppression/modif d'un endpoint, d'une auth ou d'une env var,
  régénère le manifeste via `/neo-connector` (ou le prompt dans .claude/skills/neo-connector).
- Ne jamais éditer NEO_CONNECTOR.md à la main : il est généré.
- Le hook pre-commit (.git/hooks/pre-commit) avertit si des routes ont changé sans MAJ du manifeste.
- NOTE: ce repo n'a PAS d'API HTTP (bot Telegram en polling). Le manifeste documente la
  surface de commandes Telegram + les API sortantes consommées, et marque base_url_prod = N/A.
