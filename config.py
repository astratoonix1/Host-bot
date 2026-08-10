"""
config.py
Centralized configuration loader. All secrets/config come from environment
variables so nothing sensitive is hard-coded into source control.
"""

import os


class Config:
    # --- Core Telegram API credentials (for the Main Manager Bot) ---
    API_ID: int = int(os.environ.get("API_ID", "0"))
    API_HASH: str = os.environ.get("API_HASH", "")
    BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "")

    # --- Database ---
    MONGO_URI: str = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    DB_NAME: str = os.environ.get("DB_NAME", "bot_maker_db")

    # --- Optional / misc ---
    # Owner's Telegram user ID, used for admin-only commands / broadcasts.
    OWNER_ID: int = int(os.environ.get("OWNER_ID", "0"))

    # Optional log channel where the manager posts startup/error logs.
    _log_channel = os.environ.get("LOG_CHANNEL")
    LOG_CHANNEL: int | None = int(_log_channel) if _log_channel else None

    # Fallback public API_ID/API_HASH pair (Telegram's official test app
    # credentials) used ONLY to validate a bot token during /create, never
    # to run a real bot.
    VALIDATION_API_ID: int = int(os.environ.get("VALIDATION_API_ID", "2040"))
    VALIDATION_API_HASH: str = os.environ.get(
        "VALIDATION_API_HASH", "b18441a1ff607e10a989891a5462e627"
    )

    @classmethod
    def validate(cls) -> None:
        """Raise a clear error early if required env vars are missing."""
        missing = []
        if not cls.API_ID:
            missing.append("API_ID")
        if not cls.API_HASH:
            missing.append("API_HASH")
        if not cls.BOT_TOKEN:
            missing.append("BOT_TOKEN")
        if not cls.MONGO_URI:
            missing.append("MONGO_URI")

        if missing:
            raise EnvironmentError(
                "Missing required environment variable(s): "
                f"{', '.join(missing)}. Set them before starting the bot."
            )
