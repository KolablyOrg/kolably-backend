"""
Aggregate API router — collects all domain routers under /api/v1.
"""

from fastapi import APIRouter

from app.api.routes import (
    applications,
    auth,
    businesses,
    campaigns,
    chat,
    collaborations,
    creators,
    cron,
    invoices,
    meta,
    notifications,
    presence,
    upload,
    users,
    waitlist,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(creators.router, prefix="/creators", tags=["creators"])
api_router.include_router(businesses.router, prefix="/businesses", tags=["businesses"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(applications.router, prefix="/applications", tags=["applications"])
api_router.include_router(collaborations.router, prefix="/collaborations", tags=["collaborations"])
api_router.include_router(invoices.router, prefix="/invoices", tags=["invoices"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(presence.router, prefix="/presence", tags=["presence"])
api_router.include_router(meta.router, prefix="/meta", tags=["meta"])
api_router.include_router(upload.router)
api_router.include_router(cron.router, prefix="/cron", tags=["cron"])
api_router.include_router(waitlist.router, prefix="/waitlist", tags=["waitlist"])
