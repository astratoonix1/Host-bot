"""
plugins/start.py
Handles /start and /help commands with an engaging welcome message and
interactive inline keyboard buttons ("Create Bot", "Settings", "Help").
"""

import logging

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database import add_user

logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "👋 **Hey {name}, welcome to Bot Maker & Auto-Filter Manager!**\n\n"
    "I can turn your own bot token into a full-fledged **Auto-Filter File "
    "Search Bot** — no coding required.\n\n"
    "✨ **What I can do:**\n"
    "• Spawn your personal bot in seconds\n"
    "• Auto-index files from your channel\n"
    "• Let users search files with a simple text query\n"
    "• Manage everything from one place\n\n"
    "Tap **Create Bot** below to get started, or **Help** to learn more."
)

HELP_TEXT = (
    "📖 **Help & Guide**\n\n"
    "**1. /create** — Start the setup wizard to spawn your own bot. "
    "You'll need:\n"
    "   • Bot Token (from @BotFather)\n"
    "   • API ID & API Hash (from my.telegram.org)\n"
    "   • MongoDB URI (from mongodb.com/atlas)\n\n"
    "**2. /settings** — View or manage your spawned bot (info, stop/start, delete).\n\n"
    "**3. Auto-Filter** — Once your bot is live, add it as admin to your "
    "channel. Every file posted there is indexed automatically. Users can "
    "then find it by typing the file name in your bot's chat or group.\n\n"
    "**4. /cancel** — Cancel any ongoing setup process.\n\n"
    "Need more help? Contact the bot owner."
)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🤖 Create Bot", callback_data="menu_create")],
            [
                InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings"),
                InlineKeyboardButton("❓ Help", callback_data="menu_help"),
            ],
            [InlineKeyboardButton("❌ Close", callback_data="menu_close")],
        ]
    )


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu_back")]])


@Client.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message) -> None:
    """Send an engaging welcome message with quick-action buttons."""
    try:
        await add_user(message.from_user.id, message.from_user.username)
        text = WELCOME_TEXT.format(name=message.from_user.mention)
        await message.reply_text(text, reply_markup=main_menu_keyboard(), quote=True)
    except Exception as e:
        logger.error(f"start_command error: {e}")
        await message.reply_text("⚠️ Something went wrong. Please try again.")


@Client.on_message(filters.command("help") & filters.private)
async def help_command(client: Client, message: Message) -> None:
    try:
        await message.reply_text(HELP_TEXT, reply_markup=back_keyboard(), quote=True)
    except Exception as e:
        logger.error(f"help_command error: {e}")


@Client.on_callback_query(filters.regex("^menu_"))
async def menu_callback(client: Client, query: CallbackQuery) -> None:
    """Route inline button presses from the main menu."""
    action = query.data.split("_", 1)[1]
    try:
        if action == "help":
            await query.message.edit_text(HELP_TEXT, reply_markup=back_keyboard())
        elif action == "back":
            text = WELCOME_TEXT.format(name=query.from_user.mention)
            await query.message.edit_text(text, reply_markup=main_menu_keyboard())
        elif action == "close":
            await query.message.delete()
        elif action == "create":
            # Delegate to the /create wizard defined in creator.py
            from plugins.creator import begin_creation_wizard

            await begin_creation_wizard(client, query.message, query.from_user.id)
        elif action == "settings":
            from plugins.settings import show_settings_panel

            await show_settings_panel(client, query.message, query.from_user.id)
        await query.answer()
    except Exception as e:
        logger.error(f"menu_callback error: {e}")
        await query.answer("⚠️ Something went wrong.", show_alert=True)
