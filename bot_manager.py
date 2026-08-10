"""
bot_manager.py
Runtime registry that keeps track of all spawned (user-created) Pyrogram
Client instances so they can be started/stopped dynamically without
restarting the Main Manager Bot. Used by plugins/creator.py and
plugins/settings.py, and by main.py on boot to restore saved bots.
"""

import logging
from typing import Dict, Optional

from pyrogram import Client
from pyrogram.errors import RPCError

logger = logging.getLogger(__name__)

# In-memory registry: {user_id: Client}
RUNNING_BOTS: Dict[int, Client] = {}


async def start_user_bot(
    user_id: int, bot_token: str, api_id: int, api_hash: str
) -> Optional[Client]:
    """Instantiate, start, and register a spawned user bot."""
    if user_id in RUNNING_BOTS:
        logger.info(f"Bot for user {user_id} is already running.")
        return RUNNING_BOTS[user_id]

    try:
        app = Client(
            name=f"user_bot_{user_id}",
            api_id=api_id,
            api_hash=api_hash,
            bot_token=bot_token,
            plugins=dict(root="plugins"),
            in_memory=True,  # avoid writing .session files per spawned bot
        )
        await app.start()
        RUNNING_BOTS[user_id] = app
        logger.info(f"Started spawned bot for user {user_id}.")
        return app
    except RPCError as e:
        logger.error(f"Failed to start bot for user {user_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error starting bot for user {user_id}: {e}")
        return None


async def stop_user_bot(user_id: int) -> bool:
    """Stop and unregister a running spawned bot, if any."""
    app = RUNNING_BOTS.get(user_id)
    if not app:
        return False
    try:
        await app.stop()
    except Exception as e:
        logger.warning(f"Error stopping bot for user {user_id}: {e}")
    finally:
        RUNNING_BOTS.pop(user_id, None)
    return True


def is_bot_running(user_id: int) -> bool:
    """Quick lookup for whether a user's bot is currently active."""
    return user_id in RUNNING_BOTS
