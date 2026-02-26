#!/usr/bin/env bash
# ─────────────────────────────────────────────
#  RugScore Bot — Launch Script
# ─────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="venv"
PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"

# ── Colors ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

banner() {
    echo -e "${CYAN}"
    echo "  ╔══════════════════════════════════════╗"
    echo "  ║       🛡️  RugScore Bot  🛡️            ║"
    echo "  ║     Solana Memecoin Safety Scanner   ║"
    echo "  ╚══════════════════════════════════════╝"
    echo -e "${NC}"
}

# ── 1. Check Python ──
check_python() {
    if ! command -v python3 &>/dev/null; then
        echo -e "${RED}Error: python3 not found. Install Python 3.10+${NC}"
        exit 1
    fi
    PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    echo -e "${GREEN}✓${NC} Python $PY_VERSION detected"
}

# ── 2. Setup venv ──
setup_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        echo -e "${YELLOW}Creating virtual environment...${NC}"
        python3 -m venv "$VENV_DIR"
        echo -e "${GREEN}✓${NC} Virtual environment created"
    fi
}

# ── 3. Install dependencies ──
install_deps() {
    if [ ! -f "$VENV_DIR/.deps_installed" ] || [ "requirements.txt" -nt "$VENV_DIR/.deps_installed" ]; then
        echo -e "${YELLOW}Installing dependencies...${NC}"
        "$PIP" install --upgrade pip -q
        "$PIP" install -r requirements.txt -q
        touch "$VENV_DIR/.deps_installed"
        echo -e "${GREEN}✓${NC} Dependencies installed"
    else
        echo -e "${GREEN}✓${NC} Dependencies up to date"
    fi
}

# ── 4. Check .env ──
check_env() {
    if [ ! -f ".env" ]; then
        echo -e "${RED}Error: .env file not found!${NC}"
        echo -e "  Copy the example and fill in your keys:"
        echo -e "  ${CYAN}cp .env.example .env${NC}"
        exit 1
    fi

    # Check required keys
    source .env 2>/dev/null
    if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ "$TELEGRAM_BOT_TOKEN" = "your_telegram_bot_token_here" ]; then
        echo -e "${RED}Error: TELEGRAM_BOT_TOKEN not configured in .env${NC}"
        exit 1
    fi
    if [ -z "$HELIUS_API_KEY" ] || [ "$HELIUS_API_KEY" = "your_helius_api_key_here" ]; then
        echo -e "${YELLOW}Warning: HELIUS_API_KEY not set — some features will be limited${NC}"
    fi
    echo -e "${GREEN}✓${NC} Environment configured"
}

# ── 5. Launch ──
launch() {
    echo -e "${GREEN}Starting RugScore Bot...${NC}"
    echo ""
    exec "$PYTHON" -m bot.main
}

# ── Main ──
banner
check_python
setup_venv
install_deps
check_env
launch
