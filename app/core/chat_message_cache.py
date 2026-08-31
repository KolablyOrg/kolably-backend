"""Redis-backed cache for conversation tails and last messages.

Redis is deliberately treated as a cache: every miss returns ``None`` so the
calling service can read authoritative data from PostgreSQL.
"""

from __future__ import annotations

import json
import logging
from collections import OrderedDict

from app.core.redis_client import get_redis_client
from app.models.chat import Message

logger = logging.getLogger(__name__)
MAX_TAIL = 100


class ChatMessageCache:
    def __init__(self) -> None:
        self._known_conversations: set[str] = set()
        # Development fallback when Redis_URL is intentionally unset. This is
        # never used when Redis is configured and is bounded like the old cache.
        self._fallback: OrderedDict[str, list[Message]] = OrderedDict()

    @staticmethod
    def _last_key(conversation_id: str) -> str:
        return f"chat:last:{conversation_id}"

    @staticmethod
    def _tail_key(conversation_id: str) -> str:
        return f"chat:tail:{conversation_id}"

    @staticmethod
    def _encode(message: Message) -> str:
        return json.dumps(message.to_row(), default=lambda value: value.isoformat())

    @staticmethod
    def _decode(value: str) -> Message:
        row = json.loads(value)
        return Message.from_row(row)

    async def get_last_message(self, conversation_id: str) -> Message | None:
        client = get_redis_client()
        if client is None:
            messages = self._fallback.get(conversation_id, [])
            return messages[-1] if messages else None
        try:
            value = await client.get(self._last_key(conversation_id))
            return self._decode(value) if value else None
        except Exception:
            logger.warning("Redis last-message read failed", exc_info=True)
            return None

    async def append(self, conversation_id: str, message: Message) -> None:
        client = get_redis_client()
        if client is None:
            messages = self._fallback.setdefault(conversation_id, [])
            messages[:] = (messages + [message])[-MAX_TAIL:]
            self._fallback.move_to_end(conversation_id)
            while len(self._fallback) > 200:
                self._fallback.popitem(last=False)
            return
        encoded = self._encode(message)
        try:
            async with client.pipeline(transaction=True) as pipe:
                await pipe.set(self._last_key(conversation_id), encoded)
                await pipe.rpush(self._tail_key(conversation_id), encoded)
                await pipe.ltrim(self._tail_key(conversation_id), -MAX_TAIL, -1)
                await pipe.execute()
            self._known_conversations.add(conversation_id)
        except Exception:
            logger.warning("Redis message-cache write failed", exc_info=True)

    async def hydrate_tail(self, conversation_id: str, messages: list[Message]) -> None:
        if not messages:
            return
        client = get_redis_client()
        if client is None:
            self._fallback[conversation_id] = list(messages[-MAX_TAIL:])
            return
        encoded = [self._encode(message) for message in messages[-MAX_TAIL:]]
        try:
            async with client.pipeline(transaction=True) as pipe:
                await pipe.delete(self._tail_key(conversation_id))
                await pipe.rpush(self._tail_key(conversation_id), *encoded)
                await pipe.ltrim(self._tail_key(conversation_id), -MAX_TAIL, -1)
                await pipe.set(self._last_key(conversation_id), encoded[-1])
                await pipe.execute()
            self._known_conversations.add(conversation_id)
        except Exception:
            logger.warning("Redis message-cache hydration failed", exc_info=True)

    async def list_after(self, conversation_id: str, after_id: str) -> list[Message] | None:
        client = get_redis_client()
        if client is None:
            messages = self._fallback.get(conversation_id)
            if not messages:
                return None
            for index, message in enumerate(messages):
                if message.id == after_id:
                    return messages[index + 1 :]
            return None
        try:
            values = await client.lrange(self._tail_key(conversation_id), 0, -1)
            messages = [self._decode(value) for value in values]
            for index, message in enumerate(messages):
                if message.id == after_id:
                    return messages[index + 1 :]
            return None
        except Exception:
            logger.warning("Redis message-tail read failed", exc_info=True)
            return None

    async def clear_all(self) -> None:
        """Clear keys written by this instance; primarily useful in tests."""
        client = get_redis_client()
        if client is None:
            self._known_conversations.clear()
            self._fallback.clear()
            return
        try:
            keys = [key for cid in self._known_conversations for key in (self._last_key(cid), self._tail_key(cid))]
            if keys:
                await client.delete(*keys)
        except Exception:
            logger.warning("Redis message-cache cleanup failed", exc_info=True)
        finally:
            self._known_conversations.clear()
            self._fallback.clear()


chat_message_cache = ChatMessageCache()
