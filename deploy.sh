#!/bin/bash
# RugScore Bot — VPS deploy script
# Usage: ./deploy.sh [command]
#   start    — Build & start (default)
#   stop     — Stop the bot
#   restart  — Rebuild & restart
#   logs     — Tail live logs
#   status   — Show container status
#   update   — Git pull + rebuild + restart

set -e

COMPOSE="docker compose"
SERVICE="rugscore-bot"

# Check .env exists
check_env() {
    if [ ! -f .env ]; then
        echo "ERROR: .env file not found!"
        echo "Create one with at least:"
        echo "  TELEGRAM_BOT_TOKEN=your_token"
        echo "  HELIUS_API_KEY=your_key"
        echo "  ADMIN_IDS=your_telegram_id"
        exit 1
    fi
}

case "${1:-start}" in
    start)
        check_env
        echo "Building & starting RugScore Bot..."
        $COMPOSE up -d --build
        echo "Done! Use './deploy.sh logs' to see output."
        ;;
    stop)
        echo "Stopping RugScore Bot..."
        $COMPOSE down
        echo "Stopped."
        ;;
    restart)
        check_env
        echo "Rebuilding & restarting RugScore Bot..."
        $COMPOSE down
        $COMPOSE up -d --build
        echo "Done! Use './deploy.sh logs' to see output."
        ;;
    logs)
        $COMPOSE logs -f $SERVICE
        ;;
    status)
        $COMPOSE ps
        ;;
    update)
        check_env
        echo "Pulling latest code..."
        git pull
        echo "Rebuilding & restarting..."
        $COMPOSE down
        $COMPOSE up -d --build
        echo "Updated! Use './deploy.sh logs' to see output."
        ;;
    *)
        echo "Usage: ./deploy.sh {start|stop|restart|logs|status|update}"
        exit 1
        ;;
esac
