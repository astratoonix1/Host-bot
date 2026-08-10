"""
main.py
Entry point for the Main Manager Bot.

- Initializes Pyrogram with plugins=dict(root="plugins")
- Ensures MongoDB indexes exist
- Auto-loads and starts every previously-created ACTIVE user bot stored
  in MongoDB, in the background, without blocking the manager's startup.
"""

import asyncio
import logging

from pyrogram import Client, idle

from bot_manager import RUNNING_BOTS, start_user_bot
from config import Config
from database import get_all_active_bots, init_indexes

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logger = logging.getLogger("BotMakerManager")

Config.validate()

# The Main Manager Bot -- the one users talk to for /start, /create, /settings.
app = Client(
    name="bot_maker_manager",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    plugins=dict(root="plugins"),
)


async def autostart_saved_bots() -> None:
    """Load every active bot from MongoDB and start it concurrently."""
    active_bots = await get_all_active_bots()
    if not active_bots:
        logger.info("No previously active user bots to restart.")
        return

    logger.info(f"Restarting {len(active_bots)} saved user bot(s)...")
    tasks = [
        start_user_bot(
            user_id=bot_doc["user_id"],
            bot_token=bot_doc["bot_token"],
            api_id=bot_doc["api_id"],
            api_hash=bot_doc["api_hash"],
        )
        for bot_doc in active_bots
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    started = sum(1 for r in results if r is not None and not isinstance(r, Exception))
    logger.info(f"Successfully restarted {started}/{len(active_bots)} user bot(s).")


async def shutdown() -> None:
    """Gracefully stop the manager bot and every spawned bot."""
    logger.info("Shutting down manager bot...")
    try:
        await app.stop()
    except Exception:
        pass
    for user_id, client in list(RUNNING_BOTS.items()):
        try:
            await client.stop()
        except Exception:
            pass
    RUNNING_BOTS.clear()
    logger.info("Shutdown complete.")


async def main() -> None:
    await init_indexes()
    await app.start()

    me = await app.get_me()
    logger.info(f"Main Manager Bot started as @{me.username}")

    # Launch all previously created user bots in the background so the
    # manager itself becomes responsive immediately.
    asyncio.create_task(autostart_saved_bots())

    logger.info("Bot Maker & Auto-Filter Manager is now online.")
    try:
        await idle()
    finally:
        await shutdown()


if __name__ == "__main__":
    asyncio.run(main())
