"""
In-process chat message cache (single worker).

Caches the last message per conversation for fast inbox listing, and a short
tail of recent messages for delta `?after=` reads on hot threads. Dies on
process restart; not shared across workers. Postgres remains source of truth.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field

from app.models.chat import Message

MAX_CONVERSATIONS = 200
MAX_TAIL = 100


@dataclass
class _ConversationEntry:
    last_message: Message | None = None
    tail: list[Message] = field(default_factory=list)


class ChatMessageCache:
    def __init__(self) -> None:
        self._entries: OrderedDict[str, _ConversationEntry] = OrderedDict()
        self._lock = asyncio.Lock()

    def _touch(self, conversation_id: str) -> _ConversationEntry:
        entry = self._entries.pop(conversation_id, None)
        if entry is None:
            entry = _ConversationEntry()
        self._entries[conversation_id] = entry
        while len(self._entries) > MAX_CONVERSATIONS:
            self._entries.popitem(last=False)
        return entry

    async def get_last_message(self, conversation_id: str) -> Message | None:
        async with self._lock:
            entry = self._entries.get(conversation_id)
            return entry.last_message if entry else None

    async def append(self, conversation_id: str, message: Message) -> None:
        async with self._lock:
            entry = self._touch(conversation_id)
            entry.last_message = message
            if entry.tail and entry.tail[-1].id == message.id:
                return
            entry.tail.append(message)
            if len(entry.tail) > MAX_TAIL:
                entry.tail = entry.tail[-MAX_TAIL:]

    async def hydrate_tail(self, conversation_id: str, messages: list[Message]) -> None:
        if not messages:
            return
        async with self._lock:
            entry = self._touch(conversation_id)
            entry.last_message = messages[-1]
            entry.tail = list(messages[-MAX_TAIL:])

    async def list_after(self, conversation_id: str, after_id: str) -> list[Message] | None:
        """Return messages strictly after `after_id` if the cursor is in the hot tail."""
        async with self._lock:
            entry = self._entries.get(conversation_id)
            if not entry or not entry.tail:
                return None

            cursor_idx = next((i for i, m in enumerate(entry.tail) if m.id == after_id), None)
            if cursor_idx is None:
                return None
            return list(entry.tail[cursor_idx + 1 :])

    async def clear_all(self) -> None:
        async with self._lock:
            self._entries.clear()


chat_message_cache = ChatMessageCache()
