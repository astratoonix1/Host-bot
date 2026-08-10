"""
plugins/creator.py
/create setup wizard: collects Bot Token, API ID, API Hash, and MongoDB URI
from the user, validates each step, then saves and spawns the user's bot.

A lightweight in-memory FSM (finite state machine) tracks each user's
progress through the wizard. This keeps the flow simple without requiring
an external "conversation" library.
"""

import logging
import re
from typing import Any, Dict

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError
from pyrogram import Client, StopPropagation, filters
from pyrogram.errors import RPCError
from pyrogram.types import Message

from bot_manager import start_user_bot, stop_user_bot
from config import Config
from database import get_user_bot, save_user_bot

logger = logging.getLogger(__name__)

# In-memory FSM: {user_id: {"step": str, "data": {...}}}
SESSIONS: Dict[int, Dict[str, Any]] = {}

TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")
API_HASH_RE = re.compile(r"^[a-f0-9]{32}$")


async def begin_creation_wizard(client: Client, message: Message, user_id: int) -> None:
    """Kick off (or restart) the bot-creation wizard for a user."""
    existing = await get_user_bot(user_id)
    if existing:
        await message.reply_text(
            "⚠️ You already have a bot registered "
            f"(@{existing.get('bot_username', 'unknown')}).\n\n"
            "Continuing will overwrite it once setup completes."
        )

    SESSIONS[user_id] = {"step": "token", "data": {}}
    await message.reply_text(
        "🛠 **Bot Creation Wizard**\n\n"
        "**Step 1/4:** Send me your **Bot Token** from @BotFather.\n\n"
        "_Send /cancel anytime to stop._"
    )


@Client.on_message(filters.command("create") & filters.private)
async def create_command(client: Client, message: Message) -> None:
    await begin_creation_wizard(client, message, message.from_user.id)


@Client.on_message(filters.command("cancel") & filters.private)
async def cancel_command(client: Client, message: Message) -> None:
    if SESSIONS.pop(message.from_user.id, None):
        await message.reply_text("❌ Setup cancelled.")
    else:
        await message.reply_text("There's nothing to cancel.")


# group=1: runs before filter.py's search handler (group=2). We explicitly
# stop propagation below whenever a wizard session is active so that a
# user's token/api_id/api_hash/mongo_uri input never gets treated as a
# file-search query by plugins/filter.py.
@Client.on_message(
    filters.private
    & filters.text
    & ~filters.command(["create", "cancel", "start", "help", "settings"]),
    group=1,
)
async def wizard_step_handler(client: Client, message: Message) -> None:
    """Process each step of the creation wizard based on session state."""
    user_id = message.from_user.id
    session = SESSIONS.get(user_id)
    if not session:
        return  # Not in a wizard session -- let other handlers process it

    step = session["step"]
    text = message.text.strip()

    try:
        if step == "token":
            await handle_token_step(message, session, text)
        elif step == "api_id":
            await handle_api_id_step(message, session, text)
        elif step == "api_hash":
            await handle_api_hash_step(message, session, text)
        elif step == "mongo_uri":
            await handle_mongo_uri_step(message, session, text)
    except Exception as e:
        logger.error(f"wizard_step_handler error for {user_id}: {e}")
        await message.reply_text("⚠️ An unexpected error occurred. Setup cancelled.")
        SESSIONS.pop(user_id, None)

    # A wizard session was in progress for this message -- don't let it
    # fall through to the auto-filter search handler in plugins/filter.py.
    raise StopPropagation


async def handle_token_step(message: Message, session: dict, text: str) -> None:
    """Validate the bot token by attempting a lightweight auth check."""
    if not TOKEN_RE.match(text):
        await message.reply_text("❌ That doesn't look like a valid bot token. Please try again.")
        return

    status_msg = await message.reply_text("🔍 Validating bot token...")
    temp_client = Client(
        name=f"validate_{message.from_user.id}",
        api_id=Config.VALIDATION_API_ID,
        api_hash=Config.VALIDATION_API_HASH,
        bot_token=text,
        in_memory=True,
    )
    try:
        await temp_client.start()
        me = await temp_client.get_me()
        await temp_client.stop()
    except RPCError as e:
        await status_msg.edit_text(f"❌ Invalid bot token ({e}). Please send it again.")
        return
    except Exception as e:
        await status_msg.edit_text(f"❌ Could not validate token ({e}). Please send it again.")
        return

    session["data"]["bot_token"] = text
    session["data"]["bot_id"] = me.id
    session["data"]["bot_username"] = me.username
    session["step"] = "api_id"
    await status_msg.edit_text(
        f"✅ Token valid for @{me.username}!\n\n"
        "**Step 2/4:** Send me your **API ID** (from my.telegram.org)."
    )


async def handle_api_id_step(message: Message, session: dict, text: str) -> None:
    if not text.isdigit():
        await message.reply_text("❌ API ID must be a number. Please try again.")
        return
    session["data"]["api_id"] = int(text)
    session["step"] = "api_hash"
    await message.reply_text("**Step 3/4:** Now send me your **API Hash**.")


async def handle_api_hash_step(message: Message, session: dict, text: str) -> None:
    if not API_HASH_RE.match(text):
        await message.reply_text(
            "❌ That doesn't look like a valid API Hash (32 hex characters). Try again."
        )
        return
    session["data"]["api_hash"] = text
    session["step"] = "mongo_uri"
    await message.reply_text(
        "**Step 4/4:** Send me your **MongoDB URI** "
        "(e.g. `mongodb+srv://user:pass@cluster.mongodb.net`)."
    )


async def handle_mongo_uri_step(message: Message, session: dict, text: str) -> None:
    """Validate the Mongo URI with a quick ping, then finalize and launch the bot."""
    if not text.startswith(("mongodb://", "mongodb+srv://")):
        await message.reply_text("❌ That doesn't look like a valid MongoDB URI. Try again.")
        return

    status_msg = await message.reply_text("🔍 Validating MongoDB connection...")
    test_client = AsyncIOMotorClient(text, serverSelectionTimeoutMS=5000)
    try:
        await test_client.admin.command("ping")
    except PyMongoError as e:
        await status_msg.edit_text(f"❌ Could not connect to MongoDB ({e}). Please send a valid URI.")
        return
    finally:
        test_client.close()

    session["data"]["mongo_uri"] = text
    user_id = message.from_user.id
    data = session["data"]

    await status_msg.edit_text("💾 Saving configuration and starting your bot...")

    # Stop any previously running instance for this user before restarting.
    await stop_user_bot(user_id)

    saved = await save_user_bot(
        user_id=user_id,
        bot_token=data["bot_token"],
        api_id=data["api_id"],
        api_hash=data["api_hash"],
        mongo_uri=data["mongo_uri"],
        bot_id=data["bot_id"],
        bot_username=data["bot_username"],
    )

    if not saved:
        await status_msg.edit_text("❌ Failed to save your bot configuration. Please try /create again.")
        SESSIONS.pop(user_id, None)
        return

    started = await start_user_bot(
        user_id=user_id,
        bot_token=data["bot_token"],
        api_id=data["api_id"],
        api_hash=data["api_hash"],
    )

    SESSIONS.pop(user_id, None)

    if started:
        await status_msg.edit_text(
            f"🎉 **Your bot @{data['bot_username']} is now live!**\n\n"
            "Add it as admin to your channel to start auto-indexing files, "
            "then use /settings anytime to manage it."
        )
    else:
        await status_msg.edit_text(
            "⚠️ Configuration saved, but the bot failed to start. "
            "It will retry automatically on the next manager restart, "
            "or you can try /settings → Start Bot."
        )
