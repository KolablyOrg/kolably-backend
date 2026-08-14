from app.models.creator import Creator
from app.schemas.business import ShortlistUpdateRequest
from app.services import business_service

CREATOR_ROW = {
    "id": "creator-1",
    "profile_id": "profile-creator-1",
    "name": "Ananya Rao",
    "city": "Delhi",
    "niche": "Food",
    "follower_count": 24100,
    "engagement_rate": 5.8,
    "profile_photo_url": None,
    "created_at": "2026-01-01T00:00:00+00:00",
}


class FakeBusinessRepo:
    async def get_id_by_profile_id(self, profile_id: str) -> str:
        return "business-1"


class FakeCreatorRepo:
    def __init__(self, creator: Creator | None):
        self.creator = creator

    async def get_by_id(self, creator_id: str):
        return self.creator if self.creator and self.creator.id == creator_id else None


class FakeShortlistRepo:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.upserted = None
        self.deleted = None

    async def list_by_business(self, business_id: str):
        return self.rows

    async def upsert(self, data: dict):
        self.upserted = data
        return {
            "id": "shortlist-1",
            "business_id": data["business_id"],
            "creator_id": data["creator_id"],
            "tags": data["tags"],
            "note": data["note"],
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }

    async def delete_for_creator(self, business_id: str, creator_id: str):
        self.deleted = (business_id, creator_id)


async def test_update_shortlist_trims_tags_and_note():
    shortlist_repo = FakeShortlistRepo()
    creator_repo = FakeCreatorRepo(Creator.from_row(CREATOR_ROW))

    result = await business_service.update_shortlist(
        profile_id="profile-business-1",
        creator_id="creator-1",
        data=ShortlistUpdateRequest(tags=[" Food ", "", "Repeat creator"], note="  Strong fit  "),
        repo=FakeBusinessRepo(),
        shortlist_repo=shortlist_repo,
        creator_repo=creator_repo,
    )

    assert shortlist_repo.upserted == {
        "business_id": "business-1",
        "creator_id": "creator-1",
        "tags": ["Food", "Repeat creator"],
        "note": "Strong fit",
        "updated_at": shortlist_repo.upserted["updated_at"],
    }
    assert result.creator is not None
    assert result.creator.name == "Ananya Rao"


async def test_remove_shortlist_uses_callers_business():
    shortlist_repo = FakeShortlistRepo()

    await business_service.remove_from_shortlist(
        profile_id="profile-business-1",
        creator_id="creator-1",
        repo=FakeBusinessRepo(),
        shortlist_repo=shortlist_repo,
    )

    assert shortlist_repo.deleted == ("business-1", "creator-1")
