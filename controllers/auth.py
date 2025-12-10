from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import RedirectResponse

from common.app_settings import settings
from core import AuthServiceDependency, CurrentUserDependency
from schemas.auth import TokenResponse, RefreshTokenRequest, GoogleAuthUrl
from schemas.user import UserDto

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])


@auth_router.get("/login", response_model=GoogleAuthUrl)
async def login(request: Request, auth_service: AuthServiceDependency):
    """
    Get Google OAuth authorization URL.
    Redirect user to this URL to start the OAuth flow.
    """
    # Build callback URL from request
    redirect_uri = str(request.url_for("auth_callback"))
    authorization_url = auth_service.get_authorization_url(redirect_uri)
    return GoogleAuthUrl(authorization_url=authorization_url)


@auth_router.get("/callback")
async def auth_callback(
    request: Request,
    code: str,
    auth_service: AuthServiceDependency,
):
    """
    Handle Google OAuth callback.
    Redirects to frontend with JWT access token.
    """
    redirect_uri = str(request.url_for("auth_callback"))
    try:
        user, access_token, refresh_token = auth_service.process_google_callback(code, redirect_uri)
        # Redirect to frontend with token
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/auth/callback?token={access_token}",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        # Redirect to frontend with error
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/auth/callback?error={str(e)}",
            status_code=status.HTTP_302_FOUND
        )


@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    data: RefreshTokenRequest,
    auth_service: AuthServiceDependency,
):
    """
    Refresh access token using refresh token.
    Returns new access and refresh tokens.
    """
    new_access_token, new_refresh_token = auth_service.refresh_access_token(data.refresh_token)
    return TokenResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=3600,
    )


@auth_router.get("/me", response_model=UserDto)
async def get_current_user_info(current_user: CurrentUserDependency):
    """
    Get current authenticated user information.
    Requires valid access token.
    """
    return UserDto.from_user(current_user)


@auth_router.post("/logout")
async def logout(current_user: CurrentUserDependency):
    """
    Logout current user.
    Note: JWT tokens are stateless, so this just returns success.
    Client should discard the tokens.
    """
    return {"message": "Successfully logged out"}
