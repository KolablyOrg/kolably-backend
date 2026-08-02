from fastapi import HTTPException, status

from app.core.enums import ApplicationDirection, ApplicationStatus, CollaborationStatus, NotificationType
from app.models.application import CampaignApplication
from app.models.campaign import Campaign
from app.repositories.application_repo import ApplicationRepository
from app.repositories.business_repo import BusinessRepository
from app.repositories.campaign_repo import CampaignRepository
from app.repositories.collaboration_repo import CollaborationRepository
from app.repositories.creator_repo import CreatorRepository
from app.schemas.application import (
    ApplicationCreateRequest,
    ApplicationResponse,
    ApplicationRevisionRequest,
    ApplicationUpdateRequest,
    ApplicationWithCampaign,
    ApplicationWithCreator,
)
from app.schemas.business import BusinessSummary
from app.schemas.campaign import CampaignSummary
from app.schemas.creator import CreatorSummary
from app.services import chat_service, notification_service


async def _get_creator_id_for_user(
    profile_id: str,
    *,
    repo: CreatorRepository | None = None,
) -> str:
    repo = repo or CreatorRepository()
    creator_id = await repo.get_id_by_profile_id(profile_id)
    if not creator_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator profile not found",
        )
    return creator_id


async def _get_business_id_for_user(
    profile_id: str,
    *,
    repo: BusinessRepository | None = None,
) -> str:
    repo = repo or BusinessRepository()
    business_id = await repo.get_id_by_profile_id(profile_id)
    if not business_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found",
        )
    return business_id


def _application_to_response(app: CampaignApplication) -> ApplicationResponse:
    """Convert a CampaignApplication model to ApplicationResponse schema."""
    return ApplicationResponse(
        id=app.id,
        campaign_id=app.campaign_id,
        creator_id=app.creator_id,
        direction=app.direction,
        message=app.message,
        instagram_handle=app.instagram_handle,
        example_content_url=app.example_content_url,
        status=app.status,
        revision_reason=app.revision_reason,
        created_at=app.created_at,
    )


async def get_application(
    application_id: str,
    *,
    repo: ApplicationRepository | None = None,
) -> ApplicationResponse:
    repo = repo or ApplicationRepository()
    app = await repo.get_by_id(application_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )
    return _application_to_response(app)


async def list_my_applications(
    profile_id: str,
    page: int = 1,
    page_size: int = 20,
    *,
    creator_repo: CreatorRepository | None = None,
    app_repo: ApplicationRepository | None = None,
) -> dict:
    creator_id = await _get_creator_id_for_user(profile_id, repo=creator_repo)

    app_repo = app_repo or ApplicationRepository()
    applications, total = await app_repo.list_by_creator(
        creator_id=creator_id,
        page=page,
        page_size=page_size,
    )

    items = []
    for app in applications:
        campaign_data = app.campaign or {}
        business_data = app.business or campaign_data.get("businesses") or {}

        campaign_summary = CampaignSummary(
            id=campaign_data.get("id", ""),
            business_id=campaign_data.get("business_id", ""),
            title=campaign_data.get("title", ""),
            cover_image_url=campaign_data.get("cover_image_url"),
            objective=campaign_data.get("objective", ""),
            compensation_type=campaign_data.get("compensation_type", ""),
            cash_amount_min=campaign_data.get("cash_amount_min"),
            cash_amount_max=campaign_data.get("cash_amount_max"),
            creator_category=campaign_data.get("creator_category", ""),
            location=campaign_data.get("location", ""),
            deadline=campaign_data.get("deadline"),
            status=campaign_data.get("status", ""),
            created_at=campaign_data.get("created_at", ""),
        )

        business_summary = BusinessSummary(
            id=business_data.get("id", ""),
            business_name=business_data.get("business_name", ""),
            logo_url=business_data.get("logo_url"),
        )

        items.append(
            ApplicationWithCampaign(
                id=app.id,
                campaign_id=app.campaign_id,
                creator_id=app.creator_id,
                direction=app.direction,
                message=app.message,
                instagram_handle=app.instagram_handle,
                example_content_url=app.example_content_url,
                status=app.status,
                revision_reason=app.revision_reason,
                created_at=app.created_at,
                campaign=campaign_summary,
                business=business_summary,
            )
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def list_business_applications(
    profile_id: str,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    *,
    business_repo: BusinessRepository | None = None,
    app_repo: ApplicationRepository | None = None,
) -> dict:
    business_id = await _get_business_id_for_user(profile_id, repo=business_repo)

    app_repo = app_repo or ApplicationRepository()
    applications, total = await app_repo.list_by_business(
        business_id=business_id,
        status=status,
        page=page,
        page_size=page_size,
    )

    items = []
    for app in applications:
        creator_data = app.creator or {}

        creator_summary = CreatorSummary(
            id=creator_data.get("id", ""),
            name=creator_data.get("name", ""),
            profile_photo_url=creator_data.get("profile_photo_url"),
            follower_count=creator_data.get("follower_count"),
            niche=creator_data.get("niche"),
        )

        items.append(
            ApplicationWithCreator(
                id=app.id,
                campaign_id=app.campaign_id,
                creator_id=app.creator_id,
                direction=app.direction,
                message=app.message,
                instagram_handle=app.instagram_handle,
                example_content_url=app.example_content_url,
                status=app.status,
                revision_reason=app.revision_reason,
                created_at=app.created_at,
                creator=creator_summary,
            )
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def apply_to_campaign(
    profile_id: str,
    data: ApplicationCreateRequest,
    *,
    creator_repo: CreatorRepository | None = None,
    campaign_repo: CampaignRepository | None = None,
    business_repo: BusinessRepository | None = None,
    app_repo: ApplicationRepository | None = None,
) -> ApplicationResponse:
    creator_id = await _get_creator_id_for_user(profile_id, repo=creator_repo)

    campaign_repo = campaign_repo or CampaignRepository()
    campaign = await campaign_repo.get_by_id(data.campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )
    if campaign.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This campaign is not open for applications",
        )

    app_repo = app_repo or ApplicationRepository()
    existing = await app_repo.get_existing(data.campaign_id, creator_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You've already applied to this campaign",
        )

    application = await app_repo.insert_application({
        "campaign_id": data.campaign_id,
        "creator_id": creator_id,
        "direction": ApplicationDirection.CREATOR_APPLIED.value,
        "message": data.message,
        "instagram_handle": data.instagram_handle,
        "example_content_url": data.example_content_url,
        "status": ApplicationStatus.PENDING.value,
    })
    if not application:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit application",
        )

    business_repo = business_repo or BusinessRepository()
    business = await business_repo.get_by_id(campaign.business_id)
    if business:
        await notification_service.create_notification(
            profile_id=business.profile_id,
            type=NotificationType.APPLICATION_RECEIVED,
            title="New application",
            body=f'A creator applied to your campaign "{campaign.title}".',
            related_id=application.id,
        )

    return _application_to_response(application)


async def withdraw_application(
    application_id: str,
    profile_id: str,
    *,
    creator_repo: CreatorRepository | None = None,
    app_repo: ApplicationRepository | None = None,
) -> dict:
    creator_id = await _get_creator_id_for_user(profile_id, repo=creator_repo)

    app_repo = app_repo or ApplicationRepository()
    application = await app_repo.get_by_id(application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )
    if (
        application.direction != ApplicationDirection.CREATOR_APPLIED
        or application.creator_id != creator_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only withdraw your own applications",
        )
    if application.status != ApplicationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending applications can be withdrawn",
        )

    await app_repo.delete_application(application_id)
    return {"message": "Application withdrawn"}


async def _authorize_decision(
    application: CampaignApplication,
    profile_id: str,
    role: str,
    *,
    campaign: Campaign,
    creator_repo: CreatorRepository,
    business_repo: BusinessRepository,
) -> None:
    """Only the party who did NOT initiate the application may decide on it:
    a business decides on applications creators sent in; a creator decides
    on invites a business sent out."""
    if application.direction == ApplicationDirection.CREATOR_APPLIED:
        if role != "business":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the business can decide on this application",
            )
        business_id = await business_repo.get_id_by_profile_id(profile_id)
        if campaign.business_id != business_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not own this campaign",
            )
    else:
        if role != "creator":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the invited creator can decide on this invite",
            )
        creator_id = await creator_repo.get_id_by_profile_id(profile_id)
        if application.creator_id != creator_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This invite is not addressed to you",
            )


async def _other_party_profile_id(
    application: CampaignApplication,
    campaign: Campaign,
    *,
    creator_repo: CreatorRepository,
    business_repo: BusinessRepository,
) -> str | None:
    """The profile to notify — whichever side did not make the accept/reject decision."""
    if application.direction == ApplicationDirection.CREATOR_APPLIED:
        creator = await creator_repo.get_by_id(application.creator_id)
        return creator.profile_id if creator else None
    business = await business_repo.get_by_id(campaign.business_id)
    return business.profile_id if business else None


async def _load_application_and_campaign(
    application_id: str,
    *,
    app_repo: ApplicationRepository,
    campaign_repo: CampaignRepository,
) -> tuple[CampaignApplication, Campaign]:
    application = await app_repo.get_by_id(application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )
    if application.status != ApplicationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This application has already been decided",
        )

    campaign = await campaign_repo.get_by_id(application.campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )
    return application, campaign


async def accept_application(
    application_id: str,
    profile_id: str,
    role: str,
    *,
    app_repo: ApplicationRepository | None = None,
    campaign_repo: CampaignRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    business_repo: BusinessRepository | None = None,
    collab_repo: CollaborationRepository | None = None,
) -> ApplicationResponse:
    app_repo = app_repo or ApplicationRepository()
    campaign_repo = campaign_repo or CampaignRepository()
    creator_repo = creator_repo or CreatorRepository()
    business_repo = business_repo or BusinessRepository()
    collab_repo = collab_repo or CollaborationRepository()

    application, campaign = await _load_application_and_campaign(
        application_id, app_repo=app_repo, campaign_repo=campaign_repo
    )
    await _authorize_decision(
        application, profile_id, role,
        campaign=campaign, creator_repo=creator_repo, business_repo=business_repo,
    )

    counts = await campaign_repo.fetch_application_counts([campaign.id])
    accepted_count = counts.get(campaign.id, {}).get("accepted_count", 0)
    if accepted_count >= campaign.max_creators:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This campaign has reached its maximum number of creators",
        )

    updated = await app_repo.update_status(application_id, ApplicationStatus.ACCEPTED.value)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to accept application",
        )

    collaboration = await collab_repo.insert_collaboration({
        "application_id": application.id,
        "campaign_id": application.campaign_id,
        "creator_id": application.creator_id,
        "business_id": campaign.business_id,
        "status": CollaborationStatus.ACTIVE.value,
    })

    if collaboration:
        creator = await creator_repo.get_by_id(application.creator_id)
        business = await business_repo.get_by_id(campaign.business_id)
        if creator and business:
            await chat_service.get_or_create_conversation(
                creator.profile_id, business.profile_id, collaboration.id,
            )

    notify_profile_id = await _other_party_profile_id(
        application, campaign, creator_repo=creator_repo, business_repo=business_repo
    )
    if notify_profile_id:
        await notification_service.create_notification(
            profile_id=notify_profile_id,
            type=NotificationType.APPLICATION_ACCEPTED,
            title="Application accepted!",
            body=f'Your application for "{campaign.title}" was accepted.',
            related_id=collaboration.id if collaboration else application.id,
        )

    return _application_to_response(updated)


async def reject_application(
    application_id: str,
    profile_id: str,
    role: str,
    *,
    app_repo: ApplicationRepository | None = None,
    campaign_repo: CampaignRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    business_repo: BusinessRepository | None = None,
) -> ApplicationResponse:
    app_repo = app_repo or ApplicationRepository()
    campaign_repo = campaign_repo or CampaignRepository()
    creator_repo = creator_repo or CreatorRepository()
    business_repo = business_repo or BusinessRepository()

    application, campaign = await _load_application_and_campaign(
        application_id, app_repo=app_repo, campaign_repo=campaign_repo
    )
    await _authorize_decision(
        application, profile_id, role,
        campaign=campaign, creator_repo=creator_repo, business_repo=business_repo,
    )

    updated = await app_repo.update_status(application_id, ApplicationStatus.REJECTED.value)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reject application",
        )

    notify_profile_id = await _other_party_profile_id(
        application, campaign, creator_repo=creator_repo, business_repo=business_repo
    )
    if notify_profile_id:
        await notification_service.create_notification(
            profile_id=notify_profile_id,
            type=NotificationType.APPLICATION_REJECTED,
            title="Application update",
            body=f'Your application for "{campaign.title}" was not accepted.',
            related_id=application.id,
        )

    return _application_to_response(updated)


async def request_revision(
    application_id: str,
    profile_id: str,
    role: str,
    data: ApplicationRevisionRequest,
    *,
    app_repo: ApplicationRepository | None = None,
    campaign_repo: CampaignRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    business_repo: BusinessRepository | None = None,
) -> ApplicationResponse:
    """Request revision — same direction-based auth as accept/reject."""
    app_repo = app_repo or ApplicationRepository()
    campaign_repo = campaign_repo or CampaignRepository()
    creator_repo = creator_repo or CreatorRepository()
    business_repo = business_repo or BusinessRepository()

    application, campaign = await _load_application_and_campaign(
        application_id, app_repo=app_repo, campaign_repo=campaign_repo
    )
    await _authorize_decision(
        application, profile_id, role,
        campaign=campaign, creator_repo=creator_repo, business_repo=business_repo,
    )

    updated = await app_repo.update_application(
        application_id,
        {
            "status": ApplicationStatus.REVISION_REQUESTED.value,
            "revision_reason": data.reason,
        },
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to request revision",
        )

    notify_profile_id = await _other_party_profile_id(
        application, campaign, creator_repo=creator_repo, business_repo=business_repo
    )
    if notify_profile_id:
        await notification_service.create_notification(
            profile_id=notify_profile_id,
            type=NotificationType.REVISION_REQUESTED,
            title="Revision requested",
            body=f'Revision was requested for your application to "{campaign.title}".',
            related_id=application.id,
        )

    return _application_to_response(updated)


async def resubmit_application(
    application_id: str,
    profile_id: str,
    data: ApplicationUpdateRequest,
    *,
    creator_repo: CreatorRepository | None = None,
    business_repo: BusinessRepository | None = None,
    campaign_repo: CampaignRepository | None = None,
    app_repo: ApplicationRepository | None = None,
) -> ApplicationResponse:
    """Creator resubmits after a revision request — resets status to pending."""
    creator_id = await _get_creator_id_for_user(profile_id, repo=creator_repo)

    app_repo = app_repo or ApplicationRepository()
    application = await app_repo.get_by_id(application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )
    if application.creator_id != creator_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only resubmit your own applications",
        )
    if application.status != ApplicationStatus.REVISION_REQUESTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only applications with a revision request can be resubmitted",
        )

    update_data = {
        "status": ApplicationStatus.PENDING.value,
        "revision_reason": None,
        **data.model_dump(exclude_none=True),
    }

    updated = await app_repo.update_application(application_id, update_data)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resubmit application",
        )

    campaign_repo = campaign_repo or CampaignRepository()
    business_repo = business_repo or BusinessRepository()
    campaign = await campaign_repo.get_by_id(application.campaign_id)
    if campaign:
        business = await business_repo.get_by_id(campaign.business_id)
        if business:
            await notification_service.create_notification(
                profile_id=business.profile_id,
                type=NotificationType.APPLICATION_RESUBMITTED,
                title="Application resubmitted",
                body=f'A creator resubmitted their application for "{campaign.title}".',
                related_id=application.id,
            )

    return _application_to_response(updated)
