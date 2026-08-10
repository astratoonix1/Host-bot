"""
plugins/filter.py
Auto-indexes files posted to a channel and provides regex-based file
search with inline pagination for users of spawned bots.

NOTE: For simplicity, the search query itself is embedded in the callback
data (Telegram's 64-byte limit means very long queries get truncated when
paginating -- for production use with long queries, swap this for a short
lived server-side cache keyed by an id).
"""

import logging

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database import count_search_results, save_file, search_files

logger = logging.getLogger(__name__)

RESULTS_PER_PAGE = 8
MAX_QUERY_LEN_IN_CALLBACK = 40  # keeps callback_data comfortably under 64 bytes


def human_readable_size(size: int) -> str:
    """Convert bytes into a human-friendly size string."""
    if not size:
        return "Unknown size"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    size = float(size)
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    return f"{size:.2f} {units[idx]}"


# ---------------------------------------------------------------------------
# Auto-indexing: triggered when media is posted in a channel the bot admins
# ---------------------------------------------------------------------------
@Client.on_message(filters.channel & (filters.document | filters.video | filters.audio))
async def index_new_file(client: Client, message: Message) -> None:
    """Automatically index any document/video/audio posted to the channel."""
    media = message.document or message.video or message.audio
    if not media:
        return

    try:
        me = await client.get_me()
        saved = await save_file(
            bot_id=me.id,
            file_id=media.file_id,
            file_name=getattr(media, "file_name", None) or "Untitled",
            file_size=getattr(media, "file_size", 0),
            file_type=message.media.value if message.media else "document",
            caption=message.caption or "",
        )
        if saved:
            logger.info(f"Indexed file: {getattr(media, 'file_name', media.file_id)}")
    except Exception as e:
        logger.error(f"index_new_file error: {e}")


# ---------------------------------------------------------------------------
# Search: triggered by plain text messages in groups/PM (non-command)
# ---------------------------------------------------------------------------
def build_results_keyboard(query: str, page: int, total: int) -> InlineKeyboardMarkup:
    total_pages = max(1, -(-total // RESULTS_PER_PAGE))  # ceil division
    cb_query = query[:MAX_QUERY_LEN_IN_CALLBACK]

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"srch_{page - 1}_{cb_query}"))
    nav_row.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"srch_{page + 1}_{cb_query}"))

    buttons = [nav_row] if nav_row else []
    buttons.append([InlineKeyboardButton("❌ Close", callback_data="menu_close")])
    return InlineKeyboardMarkup(buttons)


async def render_search_results(client: Client, query: str, page: int):
    me = await client.get_me()
    total = await count_search_results(me.id, query)
    results = await search_files(me.id, query, skip=page * RESULTS_PER_PAGE, limit=RESULTS_PER_PAGE)

    if not results:
        return "😕 No files found for your query.", None

    lines = [f"🔎 **Results for:** `{query}`\n"]
    for i, doc in enumerate(results, start=1 + page * RESULTS_PER_PAGE):
        lines.append(f"{i}. `{doc['file_name']}` — {human_readable_size(doc['file_size'])}")
    text = "\n".join(lines)
    keyboard = build_results_keyboard(query, page, total)
    return text, keyboard


@Client.on_message(
    filters.text
    & ~filters.command(["start", "help", "create", "cancel", "settings"])
    & (filters.group | filters.private),
    group=2,  # runs after the creator wizard handler (group=1)
)
async def search_handler(client: Client, message: Message) -> None:
    """Search indexed files by name whenever a user sends plain text."""
    query = message.text.strip()
    if len(query) < 2:
        return  # ignore very short queries to reduce noise/false triggers

    try:
        text, keyboard = await render_search_results(client, query, page=0)
        await message.reply_text(text, reply_markup=keyboard, quote=True)
    except Exception as e:
        logger.error(f"search_handler error: {e}")


@Client.on_callback_query(filters.regex(r"^srch_"))
async def search_pagination_callback(client: Client, query: CallbackQuery) -> None:
    """Handle Prev/Next pagination button presses."""
    try:
        payload = query.data[len("srch_"):]
        page_str, raw_query = payload.split("_", 1)
        page = int(page_str)
        text, keyboard = await render_search_results(client, raw_query, page)
        await query.message.edit_text(text, reply_markup=keyboard)
        await query.answer()
    except Exception as e:
        logger.error(f"search_pagination_callback error: {e}")
        await query.answer("⚠️ Could not load results.", show_alert=True)


@Client.on_callback_query(filters.regex("^noop$"))
async def noop_callback(client: Client, query: CallbackQuery) -> None:
    await query.answer()
