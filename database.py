"""
database.py
Motor (Async MongoDB driver) connection handler and helper functions
for the Bot Maker & Auto-Filter Manager system.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError, PyMongoError

from config import Config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection setup
# ---------------------------------------------------------------------------
_client = AsyncIOMotorClient(Config.MONGO_URI)
db = _client[Config.DB_NAME]

user_bots_col = db["user_bots"]  # Stores spawned bot credentials
files_col = db["indexed_files"]  # Stores indexed media files
users_col = db["users"]  # Stores bot end-users (for analytics/broadcast)


async def init_indexes() -> None:
    """Create required indexes. Call once on startup."""
    try:
        await user_bots_col.create_index("user_id", unique=True)
        await user_bots_col.create_index("bot_id", unique=True, sparse=True)
        await files_col.create_index([("bot_id", 1), ("file_id", 1)], unique=True)
        await files_col.create_index([("bot_id", 1), ("file_name_lower", 1)])
        await users_col.create_index("user_id", unique=True)
        logger.info("MongoDB indexes ensured successfully.")
    except PyMongoError as e:
        logger.error(f"Failed to create indexes: {e}")


# ---------------------------------------------------------------------------
# User-bot (spawned bot) management
# ---------------------------------------------------------------------------
async def save_user_bot(
    user_id: int,
    bot_token: str,
    api_id: int,
    api_hash: str,
    mongo_uri: str,
    bot_id: int,
    bot_username: str,
) -> bool:
    """Save or update a user's custom bot credentials."""
    try:
        await user_bots_col.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "user_id": user_id,
                    "bot_token": bot_token,
                    "api_id": api_id,
                    "api_hash": api_hash,
                    "mongo_uri": mongo_uri,
                    "bot_id": bot_id,
                    "bot_username": bot_username,
                    "is_active": True,
                    "updated_at": datetime.utcnow(),
                },
                "$setOnInsert": {"created_at": datetime.utcnow()},
            },
            upsert=True,
        )
        return True
    except PyMongoError as e:
        logger.error(f"save_user_bot error for {user_id}: {e}")
        return False


async def get_user_bot(user_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a single user's bot document."""
    try:
        return await user_bots_col.find_one({"user_id": user_id})
    except PyMongoError as e:
        logger.error(f"get_user_bot error for {user_id}: {e}")
        return None


async def get_all_active_bots() -> List[Dict[str, Any]]:
    """Fetch all bots flagged as active, used to auto-start them on boot."""
    try:
        cursor = user_bots_col.find({"is_active": True})
        return [doc async for doc in cursor]
    except PyMongoError as e:
        logger.error(f"get_all_active_bots error: {e}")
        return []


async def set_bot_active_state(user_id: int, is_active: bool) -> bool:
    """Enable/disable (start/stop) a spawned bot without deleting its config."""
    try:
        result = await user_bots_col.update_one(
            {"user_id": user_id},
            {"$set": {"is_active": is_active, "updated_at": datetime.utcnow()}},
        )
        return result.modified_count > 0
    except PyMongoError as e:
        logger.error(f"set_bot_active_state error for {user_id}: {e}")
        return False


async def delete_user_bot(user_id: int) -> bool:
    """Permanently remove a user's bot record."""
    try:
        result = await user_bots_col.delete_one({"user_id": user_id})
        return result.deleted_count > 0
    except PyMongoError as e:
        logger.error(f"delete_user_bot error for {user_id}: {e}")
        return False


# ---------------------------------------------------------------------------
# File indexing / auto-filter management
# ---------------------------------------------------------------------------
async def save_file(
    bot_id: int,
    file_id: str,
    file_name: str,
    file_size: int,
    file_type: str,
    caption: str = "",
) -> bool:
    """Index a media file. Silently skips duplicates (same bot + file_id)."""
    try:
        await files_col.insert_one(
            {
                "bot_id": bot_id,
                "file_id": file_id,
                "file_name": file_name,
                "file_name_lower": file_name.lower(),
                "file_size": file_size,
                "file_type": file_type,
                "caption": caption,
                "indexed_at": datetime.utcnow(),
            }
        )
        return True
    except DuplicateKeyError:
        logger.debug(f"Duplicate file skipped: {file_name}")
        return False
    except PyMongoError as e:
        logger.error(f"save_file error: {e}")
        return False


async def search_files(
    bot_id: int, query: str, skip: int = 0, limit: int = 10
) -> List[Dict[str, Any]]:
    """Search indexed files for a given bot using case-insensitive regex."""
    try:
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        cursor = (
            files_col.find({"bot_id": bot_id, "file_name": {"$regex": pattern}})
            .sort("indexed_at", -1)
            .skip(skip)
            .limit(limit)
        )
        return [doc async for doc in cursor]
    except PyMongoError as e:
        logger.error(f"search_files error: {e}")
        return []


async def count_search_results(bot_id: int, query: str) -> int:
    """Count total matches for a search query, used for pagination."""
    try:
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        return await files_col.count_documents(
            {"bot_id": bot_id, "file_name": {"$regex": pattern}}
        )
    except PyMongoError as e:
        logger.error(f"count_search_results error: {e}")
        return 0


async def get_files_count(bot_id: int) -> int:
    """Total indexed files for a bot (used in the settings/info panel)."""
    try:
        return await files_col.count_documents({"bot_id": bot_id})
    except PyMongoError as e:
        logger.error(f"get_files_count error: {e}")
        return 0


async def add_user(user_id: int, username: Optional[str] = None) -> None:
    """Track bot end-users for basic analytics/broadcast support."""
    try:
        await users_col.update_one(
            {"user_id": user_id},
            {
                "$set": {"username": username, "last_seen": datetime.utcnow()},
                "$setOnInsert": {"joined_at": datetime.utcnow()},
            },
            upsert=True,
        )
    except PyMongoError as e:
        logger.error(f"add_user error for {user_id}: {e}")
