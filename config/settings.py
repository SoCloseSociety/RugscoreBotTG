from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class Settings(BaseSettings):
    """Centralized configuration loaded from environment variables."""

    # Telegram
    telegram_bot_token: str = ""
    bot_username: str = "YourBotUsername"

    # Admin (comma-separated Telegram user IDs)
    admin_ids: str = ""

    # Helius
    helius_api_key: str = ""

    # Channel (public channel for auto-reports, e.g. @MyChannel or -100xxxx)
    channel_id: str = ""

    # Donate
    donate_wallet: str = ""

    # Solana RPC
    solana_rpc_url: str = "https://api.mainnet-beta.solana.com"

    # Database
    database_url: str = "sqlite+aiosqlite:///rugscore.db"

    # Cache
    cache_ttl_seconds: int = Field(default=60, gt=0)

    # Limits
    analysis_timeout_seconds: int = Field(default=20, gt=0)
    max_concurrent_analyses: int = Field(default=20, gt=0, le=100)
    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _VALID_LOG_LEVELS:
            raise ValueError(f"log_level must be one of {_VALID_LOG_LEVELS}, got '{v}'")
        return upper

    @property
    def admin_id_set(self) -> set[int]:
        """Parse ADMIN_IDS comma-separated string into a set of ints."""
        if not self.admin_ids:
            return set()
        ids = set()
        for part in self.admin_ids.split(","):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
        return ids

    def is_admin(self, telegram_id: int) -> bool:
        """Check if a Telegram user ID is an admin."""
        return telegram_id in self.admin_id_set

    @property
    def helius_rpc_url(self) -> str:
        return f"https://mainnet.helius-rpc.com/?api-key={self.helius_api_key}"

    @property
    def helius_api_url(self) -> str:
        return "https://api.helius.xyz/v0"

    def validate_startup(self) -> list:
        """Run startup checks. Returns list of warning strings."""
        warnings = []
        if not self.telegram_bot_token:
            warnings.append("TELEGRAM_BOT_TOKEN not set")
        if not self.helius_api_key:
            warnings.append("HELIUS_API_KEY not set -- some features limited")
        if not self.admin_id_set:
            warnings.append("ADMIN_IDS not configured -- admin commands inaccessible")
        return warnings

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
