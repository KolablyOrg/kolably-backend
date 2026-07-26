from fastapi import HTTPException, status
from supabase_auth.errors import AuthApiError

from app.core.supabase import get_supabase_client
from app.repositories.business_repo import BusinessRepository
from app.repositories.creator_repo import CreatorRepository
from app.repositories.profile_repo import ProfileRepository
from app.schemas.auth import (
    BusinessSignupRequest,
    CreatorSignupRequest,
    LoginRequest,
    UpdateProfileRequest,
)


async def signup_creator(data: CreatorSignupRequest) -> dict:
    supabase = get_supabase_client()

    try:
        auth_response = supabase.auth.sign_up(
            {
                "email": data.email,
                "password": data.password,
                "options": {
                    "data": {"role": "creator"},
                },
            }
        )
    except AuthApiError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if not auth_response.user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signup failed — user not created",
        )

    auth_id = str(auth_response.user.id)

    profile_repo = ProfileRepository()
    profile = await profile_repo.get_by_auth_id(auth_id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Profile creation trigger failed",
        )

    profile_id = profile["id"]

    creator_repo = CreatorRepository()
    await creator_repo.insert_creator({
        "profile_id": profile_id,
        "name": data.name,
        "username": data.username,
        "city": data.city,
        "niche": data.niche,
        "follower_count": data.follower_count,
        "instagram_handle": data.instagram_handle,
        "profile_photo_url": data.profile_photo_url,
    })

    session = auth_response.session
    return {
        "access_token": session.access_token if session else None,
        "refresh_token": session.refresh_token if session else None,
        "token_type": "bearer",
        "user": {
            "id": profile_id,
            "email": data.email,
            "role": "creator",
            "creator": {
                "name": data.name,
                "username": data.username,
                "city": data.city,
                "niche": data.niche,
            },
        },
    }


async def signup_business(data: BusinessSignupRequest) -> dict:
    supabase = get_supabase_client()

    try:
        auth_response = supabase.auth.sign_up(
            {
                "email": data.email,
                "password": data.password,
                "options": {
                    "data": {"role": "business"},
                },
            }
        )
    except AuthApiError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if not auth_response.user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signup failed — user not created",
        )

    auth_id = str(auth_response.user.id)

    profile_repo = ProfileRepository()
    profile = await profile_repo.get_by_auth_id(auth_id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Profile creation trigger failed",
        )

    profile_id = profile["id"]

    business_repo = BusinessRepository()
    await business_repo.insert_business({
        "profile_id": profile_id,
        "business_name": data.business_name,
        "owner_name": data.owner_name,
        "category": data.business_category,
        "city": data.city,
        "address": data.address,
        "description": data.business_description,
    })

    session = auth_response.session
    return {
        "access_token": session.access_token if session else None,
        "refresh_token": session.refresh_token if session else None,
        "token_type": "bearer",
        "user": {
            "id": profile_id,
            "email": data.email,
            "role": "business",
            "business": {
                "business_name": data.business_name,
                "owner_name": data.owner_name,
                "city": data.city,
                "category": data.business_category,
            },
        },
    }


async def login(data: LoginRequest) -> dict:
    supabase = get_supabase_client()

    try:
        auth_response = supabase.auth.sign_in_with_password(
            {
                "email": data.email,
                "password": data.password,
            }
        )
    except AuthApiError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )

    if not auth_response.user or not auth_response.session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not auth_response.user.email_confirmed_at:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please check your inbox.",
        )

    auth_id = str(auth_response.user.id)
    profile_repo = ProfileRepository()
    profile = await profile_repo.get_by_auth_id(auth_id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found",
        )

    if not profile.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    session = auth_response.session
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": "bearer",
        "user": {
            "id": profile["id"],
            "email": profile["email"],
            "role": profile["role"],
            "is_active": profile["is_active"],
        },
    }


async def refresh_session(refresh_token: str) -> dict:
    supabase = get_supabase_client()

    try:
        auth_response = supabase.auth.refresh_session(refresh_token)
    except AuthApiError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )

    if not auth_response.session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to refresh session",
        )

    session = auth_response.session
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": "bearer",
    }


async def logout(access_token: str) -> dict:
    supabase = get_supabase_client()

    try:
        supabase.auth.sign_out(access_token)
    except AuthApiError:
        pass

    return {"message": "Logged out successfully"}


async def forgot_password(email: str) -> dict:
    supabase = get_supabase_client()

    try:
        supabase.auth.reset_password_email(email)
    except AuthApiError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return {"message": "Password reset link sent to your email"}


async def reset_password(access_token: str, new_password: str) -> dict:
    supabase = get_supabase_client()

    try:
        supabase.auth.set_session(access_token, "")
        supabase.auth.update_user({"password": new_password})
    except AuthApiError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return {"message": "Password updated successfully"}


async def get_user_profile(auth_id: str) -> dict:
    profile_repo = ProfileRepository()
    profile = await profile_repo.get_by_auth_id(auth_id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    response = {**profile}

    if profile["role"] in ("creator", "superadmin"):
        creator_repo = CreatorRepository()
        creator = await creator_repo.get_by_profile_id(profile["id"])
        if creator:
            response["creator"] = creator

    if profile["role"] in ("business", "superadmin"):
        business_repo = BusinessRepository()
        business = await business_repo.get_by_profile_id(profile["id"])
        if business:
            response["business"] = business

    return response


async def update_user_profile(
    profile_id: str, auth_id: str, role: str, data: UpdateProfileRequest
) -> dict:
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        return await get_user_profile(auth_id)

    if role == "creator":
        repo = CreatorRepository()
        valid_fields = {
            "name",
            "username",
            "city",
            "instagram_handle",
            "niche",
            "follower_count",
            "profile_photo_url",
        }
    elif role == "business":
        repo = BusinessRepository()
        valid_fields = {
            "business_name",
            "owner_name",
            "business_category",
            "city",
            "address",
            "business_description",
        }
    elif role == "superadmin":
        return await get_user_profile(auth_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Updates for role '{role}' not supported yet",
        )

    final_update = {}
    for k, v in update_data.items():
        if k in valid_fields:
            if k == "business_category":
                final_update["category"] = v
            elif k == "business_description":
                final_update["description"] = v
            else:
                final_update[k] = v

    if not final_update:
        return await get_user_profile(auth_id)

    if role == "creator":
        result = await repo.update_by_profile_id(profile_id, final_update)
    else:
        result = await repo.update_by_profile_id(profile_id, final_update)

    if not result:
        table_name = "creators" if role == "creator" else "businesses"
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not find {table_name} record to update",
        )

    return await get_user_profile(auth_id)
