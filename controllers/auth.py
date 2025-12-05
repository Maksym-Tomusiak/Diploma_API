from fastapi import APIRouter, Request, HTTPException, status

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


@auth_router.get("/callback", response_model=TokenResponse)
async def auth_callback(
    request: Request,
    code: str,
    auth_service: AuthServiceDependency,
):
    """
    Handle Google OAuth callback.
    Returns JWT access and refresh tokens.
    """
    redirect_uri = str(request.url_for("auth_callback"))
    try:
        user, access_token, refresh_token = auth_service.process_google_callback(code, redirect_uri)
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=3600,  # 1 hour in seconds
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth callback failed: {str(e)}",
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
