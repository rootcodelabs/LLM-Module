"""Redis-backed session store for the API Tool Calling agentic loop."""

from typing import Any, Optional

from loguru import logger

from src.models.session_models import APIToolSession
from src.utils.redis_client import get_redis_client

_SESSION_KEY_PREFIX = "session:"
_SESSION_TTL_SECONDS = 1800  # 30 minutes, sliding


def _key(chat_id: str) -> str:
    return f"{_SESSION_KEY_PREFIX}{chat_id}"


class APIToolSessionStore:
    """CRUD store for API tool agentic-loop sessions backed by Redis.

    All operations are async and safe to call from FastAPI handlers.
    The TTL is reset (sliding expiry) on every save() and update().
    """

    async def get(self, chat_id: str) -> Optional[APIToolSession]:
        """Retrieve a session by chat_id.

        Returns:
            The deserialized session, or None if not found / Redis unavailable.
        """
        client = get_redis_client()
        if client is None:
            logger.warning(
                "[SessionStore] Redis unavailable - get({}) skipped", chat_id
            )
            return None

        try:
            raw = await client.get(_key(chat_id))
            if raw is None:
                return None
            return APIToolSession.model_validate_json(raw)
        except Exception as exc:
            logger.error("[SessionStore] get({}) failed: {}", chat_id, exc)
            return None

    async def save(self, session: APIToolSession) -> None:
        """Persist a session (full replace) and reset the TTL.

        Args:
            session: The session object to persist.
        """
        client = get_redis_client()
        if client is None:
            logger.warning(
                "[SessionStore] Redis unavailable - save({}) skipped", session.chat_id
            )
            return

        try:
            await client.set(
                _key(session.chat_id),
                session.model_dump_json(),
                ex=_SESSION_TTL_SECONDS,
            )
            logger.debug("[SessionStore] Session saved for chat_id={}", session.chat_id)
        except Exception as exc:
            logger.error("[SessionStore] save({}) failed: {}", session.chat_id, exc)

    async def update(self, chat_id: str, **fields: Any) -> Optional[APIToolSession]:
        """Partially update a session and reset the TTL.

        Fetches the current session, merges the provided fields, then saves it back.

        Args:
            chat_id: The conversation to update.
            **fields: Field names and new values to merge into the session.

        Returns:
            The updated session, or None if the session does not exist or Redis is unavailable.
        """
        session = await self.get(chat_id)
        if session is None:
            logger.warning(
                "[SessionStore] update({}) - session not found, skipping", chat_id
            )
            return None

        updated = session.model_copy(update=fields)
        await self.save(updated)
        return updated

    async def delete(self, chat_id: str) -> None:
        """Remove a session from Redis.

        Args:
            chat_id: The conversation whose session should be deleted.
        """
        client = get_redis_client()
        if client is None:
            logger.warning(
                "[SessionStore] Redis unavailable - delete({}) skipped", chat_id
            )
            return

        try:
            await client.delete(_key(chat_id))
            logger.debug("[SessionStore] Session deleted for chat_id={}", chat_id)
        except Exception as exc:
            logger.error("[SessionStore] delete({}) failed: {}", chat_id, exc)

    async def exists(self, chat_id: str) -> bool:
        """Check whether a session exists for the given chat_id.

        Returns:
            True if the session key exists in Redis, False otherwise.
        """
        client = get_redis_client()
        if client is None:
            return False

        try:
            return bool(await client.exists(_key(chat_id)))
        except Exception as exc:
            logger.error("[SessionStore] exists({}) failed: {}", chat_id, exc)
            return False
