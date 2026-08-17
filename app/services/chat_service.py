import logging
from datetime import datetime

from fastapi import HTTPException, status

from app.core.enums import NotificationType
from app.models.chat import Conversation, Message
from app.repositories.business_repo import BusinessRepository
from app.repositories.campaign_repo import CampaignRepository
from app.repositories.chat_repo import ChatRepository
from app.repositories.collaboration_repo import CollaborationRepository
from app.repositories.creator_repo import CreatorRepository
from app.repositories.profile_repo import ProfileRepository
from app.services import notification_service

logger = logging.getLogger(__name__)


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


async def _resolve_participant_summary(
    profile_id: str,
    *,
    profile_repo: ProfileRepository,
    creator_repo: CreatorRepository,
    business_repo: BusinessRepository,
) -> dict:
    profile = await profile_repo.get_by_id(profile_id)
    if not profile:
        return {"id": profile_id, "name": "", "avatar_url": None}

    if profile.role.value == "creator":
        creator = await creator_repo.get_by_profile_id(profile_id)
        if creator:
            return {
                "id": profile_id,
                "name": creator.name,
                "avatar_url": creator.profile_photo_url,
                "creator_id": creator.id,
            }
    elif profile.role.value == "business":
        business = await business_repo.get_by_profile_id(profile_id)
        if business:
            # business_name is only set once onboarding-details is
            # completed (signup only captures owner_name) — fall back so a
            # not-yet-onboarded business doesn't break chat for whoever
            # they're talking to.
            return {
                "id": profile_id,
                "name": business.business_name or business.owner_name or profile.email,
                "avatar_url": business.logo_url,
                "business_id": business.id,
                "is_verified": business.is_verified,
            }

    return {"id": profile_id, "name": profile.email, "avatar_url": None}


async def _resolve_collaboration_context(
    collaboration_id: str | None,
    *,
    collab_repo: CollaborationRepository,
    campaign_repo: CampaignRepository,
) -> dict | None:
    if not collaboration_id:
        return None
    collab = await collab_repo.get_by_id(collaboration_id)
    if not collab:
        return None
    campaign = await campaign_repo.get_by_id(collab.campaign_id)
    if not campaign:
        return None
    return {
        "id": collab.id,
        "status": collab.status.value,
        "campaign_id": campaign.id,
        "campaign_title": campaign.title,
        "compensation_type": campaign.compensation_type.value if campaign.compensation_type else None,
        "cash_amount_min": campaign.cash_amount_min,
        "cash_amount_max": campaign.cash_amount_max,
        "deadline": campaign.deadline,
    }


def _message_to_response(msg: Message, *, seen: bool = False) -> dict:
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "sender_id": msg.sender_id,
        "content": msg.content,
        "created_at": msg.created_at,
        "seen": seen,
        "kind": msg.kind,
        "metadata": msg.metadata,
    }


def _is_seen_by_other(msg: Message, my_id: str, other_last_read_at) -> bool:
    """A message only shows as "seen" if it's mine and the other participant
    has read up to (or past) its timestamp — not meaningful for messages I
    received, so those always report False regardless of my own read state."""
    if msg.sender_id != my_id:
        return False
    other_read = _parse_dt(other_last_read_at)
    msg_created = _parse_dt(msg.created_at)
    if not other_read or not msg_created:
        return False
    return msg_created <= other_read


async def _conversation_to_response(
    conv: Conversation,
    profile_id: str,
    *,
    repo: ChatRepository,
    profile_repo: ProfileRepository,
    creator_repo: CreatorRepository,
    business_repo: BusinessRepository,
    collab_repo: CollaborationRepository,
    campaign_repo: CampaignRepository,
) -> dict:
    participant_ids = await repo.get_participant_ids(conv.id)
    other_id = next((pid for pid in participant_ids if pid != profile_id), None)
    other_participant = (
        await _resolve_participant_summary(
            other_id, profile_repo=profile_repo, creator_repo=creator_repo, business_repo=business_repo
        )
        if other_id
        else {"id": "", "name": "", "avatar_url": None}
    )

    last_message = await repo.get_last_message(conv.id)
    unread_count = await repo.count_unread(conv.id, profile_id)
    collaboration = await _resolve_collaboration_context(
        conv.collaboration_id, collab_repo=collab_repo, campaign_repo=campaign_repo
    )

    return {
        "id": conv.id,
        "participant_ids": participant_ids,
        "other_participant": other_participant,
        "collaboration_id": conv.collaboration_id,
        "collaboration": collaboration,
        "last_message": last_message.content if last_message else None,
        "last_message_at": last_message.created_at if last_message else None,
        "last_message_sender_id": last_message.sender_id if last_message else None,
        "unread_count": unread_count,
        "created_at": conv.created_at,
    }


async def list_conversations(
    profile_id: str,
    *,
    repo: ChatRepository | None = None,
    profile_repo: ProfileRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    business_repo: BusinessRepository | None = None,
    collab_repo: CollaborationRepository | None = None,
    campaign_repo: CampaignRepository | None = None,
) -> list[dict]:
    repo = repo or ChatRepository()
    profile_repo = profile_repo or ProfileRepository()
    creator_repo = creator_repo or CreatorRepository()
    business_repo = business_repo or BusinessRepository()
    collab_repo = collab_repo or CollaborationRepository()
    campaign_repo = campaign_repo or CampaignRepository()

    conversation_ids = await repo.list_conversation_ids_for_profile(profile_id)
    conversations = await repo.get_conversations_by_ids(conversation_ids)

    items = [
        await _conversation_to_response(
            c, profile_id, repo=repo, profile_repo=profile_repo,
            creator_repo=creator_repo, business_repo=business_repo,
            collab_repo=collab_repo, campaign_repo=campaign_repo,
        )
        for c in conversations
    ]
    items.sort(key=lambda c: c["last_message_at"] or c["created_at"], reverse=True)
    return items


async def get_conversation(
    conversation_id: str,
    profile_id: str,
    *,
    repo: ChatRepository | None = None,
    profile_repo: ProfileRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    business_repo: BusinessRepository | None = None,
    collab_repo: CollaborationRepository | None = None,
    campaign_repo: CampaignRepository | None = None,
) -> dict:
    repo = repo or ChatRepository()
    profile_repo = profile_repo or ProfileRepository()
    creator_repo = creator_repo or CreatorRepository()
    business_repo = business_repo or BusinessRepository()
    collab_repo = collab_repo or CollaborationRepository()
    campaign_repo = campaign_repo or CampaignRepository()

    conversation = await repo.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    participant_ids = await repo.get_participant_ids(conversation_id)
    if profile_id not in participant_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation",
        )

    messages = await repo.list_messages(conversation_id)
    await repo.upsert_read(conversation_id, profile_id)

    other_id = next((pid for pid in participant_ids if pid != profile_id), None)
    other_last_read_at = await repo.get_last_read_at(conversation_id, other_id) if other_id else None

    resp = await _conversation_to_response(
        conversation, profile_id, repo=repo, profile_repo=profile_repo,
        creator_repo=creator_repo, business_repo=business_repo,
        collab_repo=collab_repo, campaign_repo=campaign_repo,
    )
    resp["messages"] = [
        _message_to_response(m, seen=_is_seen_by_other(m, profile_id, other_last_read_at))
        for m in messages
    ]
    return resp


async def send_message(
    conversation_id: str,
    sender_id: str,
    content: str,
    *,
    repo: ChatRepository | None = None,
) -> dict:
    repo = repo or ChatRepository()

    conversation = await repo.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    participant_ids = await repo.get_participant_ids(conversation_id)
    if sender_id not in participant_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation",
        )

    message = await repo.insert_message({
        "conversation_id": conversation_id,
        "sender_id": sender_id,
        "content": content,
    })
    if not message:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send message",
        )

    # Sending a message counts as having read up to this point, for the sender.
    await repo.upsert_read(conversation_id, sender_id)

    for recipient_id in participant_ids:
        if recipient_id == sender_id:
            continue
        await notification_service.create_notification(
            profile_id=recipient_id,
            type=NotificationType.NEW_MESSAGE,
            title="New message",
            body=content[:120],
            related_id=conversation_id,
        )

    return _message_to_response(message)


async def post_collaboration_event(
    collaboration_id: str,
    actor_profile_id: str,
    event_type: str,
    content: str,
    *,
    extra: dict | None = None,
    repo: ChatRepository | None = None,
) -> dict | None:
    """Drop a system entry into the collaboration's chat thread.

    This is what makes the thread a full record of the campaign rather than
    just typed messages: drafts, review requests, revision notes, invoices
    and payment confirmations all land here in order, so neither side has to
    reconstruct "what happened when" from separate screens.

    Deliberately best-effort — returns None instead of raising if there's no
    conversation yet, or if the insert fails. These calls sit inside the
    submit/review/invoice flows, and a chat-logging problem must never fail
    the actual business action the user asked for.

    Unlike `send_message` this doesn't notify: the callers already raise
    their own, more specific notifications ("Draft submitted", "Changes
    requested"), and a second generic "New message" for the same event would
    just be noise.
    """
    repo = repo or ChatRepository()

    try:
        conversation = await repo.find_conversation_by_collaboration(collaboration_id)
        if not conversation:
            # Chat is created lazily when someone first opens it, so an event
            # can legitimately fire before any conversation exists.
            return None

        message = await repo.insert_message({
            "conversation_id": conversation.id,
            # NOT NULL, and genuinely meaningful: whoever's action triggered
            # this. Clients key rendering off `kind`, not the sender, so an
            # event never renders as that person's chat bubble.
            "sender_id": actor_profile_id,
            "content": content,
            "kind": "event",
            "metadata": {
                "event_type": event_type,
                "collaboration_id": collaboration_id,
                **(extra or {}),
            },
        })
        return _message_to_response(message) if message else None
    except Exception:
        # Logging an event is never worth failing the caller's real work,
        # but the failure still needs to be visible server-side.
        logger.exception(
            "post_collaboration_event failed for collaboration_id=%s event_type=%s",
            collaboration_id,
            event_type,
        )
        return None


async def get_or_create_conversation(
    profile_id: str,
    other_profile_id: str,
    collaboration_id: str | None,
    *,
    repo: ChatRepository | None = None,
    profile_repo: ProfileRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    business_repo: BusinessRepository | None = None,
    collab_repo: CollaborationRepository | None = None,
    campaign_repo: CampaignRepository | None = None,
) -> tuple[dict, bool]:
    """Returns (conversation_response, created)."""
    repo = repo or ChatRepository()
    profile_repo = profile_repo or ProfileRepository()
    creator_repo = creator_repo or CreatorRepository()
    business_repo = business_repo or BusinessRepository()
    collab_repo = collab_repo or CollaborationRepository()
    campaign_repo = campaign_repo or CampaignRepository()

    if other_profile_id == profile_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot start a conversation with yourself",
        )

    other_profile = await profile_repo.get_by_id(other_profile_id)
    if not other_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The other participant was not found",
        )

    created = False
    conversation = None
    if collaboration_id:
        conversation = await repo.find_conversation_by_collaboration(collaboration_id)
    else:
        conversation = await repo.find_shared_conversation_without_collaboration(
            profile_id, other_profile_id
        )

    if not conversation:
        conversation = await repo.insert_conversation(collaboration_id)
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create conversation",
            )
        created = True

    await repo.add_participants(conversation.id, [profile_id, other_profile_id])

    resp = await _conversation_to_response(
        conversation, profile_id, repo=repo, profile_repo=profile_repo,
        creator_repo=creator_repo, business_repo=business_repo,
        collab_repo=collab_repo, campaign_repo=campaign_repo,
    )
    return resp, created


async def get_unread_count(
    profile_id: str,
    *,
    repo: ChatRepository | None = None,
) -> dict:
    repo = repo or ChatRepository()
    total = await repo.get_total_unread(profile_id)
    return {"unread_count": total}
