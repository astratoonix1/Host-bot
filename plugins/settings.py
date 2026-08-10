"""
plugins/settings.py
/settings command: view active bot info, stop/start it, or delete it
entirely, all via an inline menu.
"""

import logging

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot_manager import is_bot_running, start_user_bot, stop_user_bot
from database import (
    delete_user_bot,
    get_files_count,
    get_user_bot,
    set_bot_active_state,
)

logger = logging.getLogger(__name__)


def settings_keyboard(is_running: bool) -> InlineKeyboardMarkup:
    toggle_btn = (
        InlineKeyboardButton("⏹ Stop Bot", callback_data="set_stop")
        if is_running
        else InlineKeyboardButton("▶️ Start Bot", callback_data="set_start")
    )
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("ℹ️ Bot Info", callback_data="set_info")],
            [toggle_btn, InlineKeyboardButton("🗑 Delete Bot", callback_data="set_delete")],
            [InlineKeyboardButton("🔙 Back", callback_data="menu_back")],
        ]
    )


async def show_settings_panel(client: Client, message: Message, user_id: int) -> None:
    """Render the main settings panel for a user's spawned bot."""
    bot_doc = await get_user_bot(user_id)
    if not bot_doc:
        await _send_or_edit(message, "You don't have a bot yet. Use /create to spawn one!")
        return

    running = is_bot_running(user_id)
    status = "🟢 Running" if running else "🔴 Stopped"
    text = (
        "⚙️ **Bot Settings**\n\n"
        f"**Bot:** @{bot_doc.get('bot_username', 'unknown')}\n"
        f"**Status:** {status}\n"
    )
    await _send_or_edit(message, text, settings_keyboard(running))


async def _send_or_edit(message: Message, text: str, keyboard: InlineKeyboardMarkup = None) -> None:
    """Edit the message if it's editable (came from a callback), else reply."""
    try:
        await message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await message.reply_text(text, reply_markup=keyboard)


@Client.on_message(filters.command("settings") & filters.private)
async def settings_command(client: Client, message: Message) -> None:
    await show_settings_panel(client, message, message.from_user.id)


@Client.on_callback_query(filters.regex("^set_"))
async def settings_callback(client: Client, query: CallbackQuery) -> None:
    """Handle Info / Stop / Start / Delete actions from the settings panel."""
    action = query.data.split("_", 1)[1]
    user_id = query.from_user.id

    try:
        bot_doc = await get_user_bot(user_id)
        if not bot_doc:
            await query.answer("No bot found. Use /create first.", show_alert=True)
            return

        if action == "info":
            files_count = await get_files_count(bot_doc["bot_id"])
            running = is_bot_running(user_id)
            info_text = (
                "ℹ️ **Bot Info**\n\n"
                f"**Username:** @{bot_doc.get('bot_username')}\n"
                f"**Bot ID:** `{bot_doc.get('bot_id')}`\n"
                f"**Status:** {'🟢 Running' if running else '🔴 Stopped'}\n"
                f"**Indexed Files:** {files_count}\n"
                f"**Created:** {bot_doc.get('created_at')}\n"
            )
            await query.message.edit_text(
                info_text,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🔙 Back", callback_data="menu_settings")]]
                ),
            )
            await query.answer()

        elif action == "stop":
            await stop_user_bot(user_id)
            await set_bot_active_state(user_id, False)
            await show_settings_panel(client, query.message, user_id)
            await query.answer("Bot stopped.")

        elif action == "start":
            started = await start_user_bot(
                user_id=user_id,
                bot_token=bot_doc["bot_token"],
                api_id=bot_doc["api_id"],
                api_hash=bot_doc["api_hash"],
            )
            if started:
                await set_bot_active_state(user_id, True)
            await show_settings_panel(client, query.message, user_id)
            await query.answer("Bot started." if started else "Failed to start bot.", show_alert=not started)

        elif action == "delete":
            await query.message.edit_text(
                "⚠️ **Are you sure you want to delete your bot?**\n"
                "This stops it and removes its saved configuration "
                "(indexed files are kept in the database).",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("✅ Yes, delete", callback_data="set_delete_confirm"),
                            InlineKeyboardButton("❌ Cancel", callback_data="menu_settings"),
                        ]
                    ]
                ),
            )
            await query.answer()

        elif action == "delete_confirm":
            await stop_user_bot(user_id)
            await delete_user_bot(user_id)
            await query.message.edit_text("🗑 Your bot has been deleted successfully.")
            await query.answer("Deleted.")

        else:
            await query.answer()

    except Exception as e:
        logger.error(f"settings_callback error: {e}")
        await query.answer("⚠️ Something went wrong.", show_alert=True)
