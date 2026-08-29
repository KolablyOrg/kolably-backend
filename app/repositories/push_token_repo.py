from datetime import UTC, datetime

from app.models.push_token import PushToken
from app.repositories.base import BaseRepository


class PushTokenRepository(BaseRepository):
    async def upsert_token(self, profile_id: str, token: str, platform: str) -> PushToken:
        """Insert a new token, or reassign an existing one to this profile.

        Keyed on `expo_push_token`, not (profile_id, token) — `BaseRepository.
        upsert` has no `on_conflict` param (it conflicts on primary key only,
        which a fresh insert never has), so this is built directly, same as
        `ProfileRepository.list_deactivated_before`'s documented pattern for
        anything beyond eq/in_.
        """
        query = (await self._table("push_tokens")).upsert(
            {
                "profile_id": profile_id,
                "expo_push_token": token,
                "platform": platform,
                "last_used_at": datetime.now(UTC).isoformat(),
            },
            on_conflict="expo_push_token",
        )
        result = await self._execute(query)
        return PushToken.from_row(result.data[0])

    async def list_tokens_for_profile(self, profile_id: str) -> list[PushToken]:
        rows = await self.select("push_tokens", filters={"profile_id": profile_id})
        return [PushToken.from_row(row) for row in rows]

    async def delete_by_token(self, token: str) -> None:
        await self.delete("push_tokens", {"expo_push_token": token})
