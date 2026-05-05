from fastapi import APIRouter, Request, HTTPException, status, Response
from fastapi.responses import RedirectResponse

from common.app_settings import settings
from core import AuthServiceDependency, CurrentUserDependency, UserActionLogServiceDependency, RateLimitServiceDependency



from schemas.auth import TokenResponse, RefreshTokenRequest, GoogleAuthUrl
from schemas.user import UserDto

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])


@auth_router.get("/remaining-checks")
async def get_remaining_checks(
    request: Request,
    rate_limit_service: RateLimitServiceDependency,
):
    """
    Get the number of remaining free checks for an anonymous user today.
    """
    remaining = rate_limit_service.get_remaining_checks(request)
    return {"remaining_checks": remaining}


@auth_router.get("/login", response_model=GoogleAuthUrl)
async def login(request: Request, auth_service: AuthServiceDependency):
    """
    Get Google OAuth authorization URL.
    Redirect user to this URL to start the OAuth flow.
    """
    # Build callback URL from request
    redirect_uri = str(request.url_for("auth_callback"))
    print(f"DEBUG: Generated redirect_uri for Google: {redirect_uri}")
    authorization_url = auth_service.get_authorization_url(redirect_uri)
    return GoogleAuthUrl(authorization_url=authorization_url)


@auth_router.get("/callback")
async def auth_callback(
    request: Request,
    code: str = None,
    error: str = None,
    auth_service: AuthServiceDependency = None,
    log_service: UserActionLogServiceDependency = None,
):
    """
    Handle Google OAuth callback.
    Redirects to frontend with JWT access token.
    """
    # Handle OAuth errors from Google (like scope changes)
    if error:
        error_message = "Authentication failed. Please try logging in again."
        if "scope" in error.lower():
            # Scope change detected - user needs to revoke and re-grant access
            error_message = (
                "App permissions have been updated. "
                "Please visit https://myaccount.google.com/permissions and remove 'Norma' access, "
                "then try logging in again."
            )
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/login?error={error_message}",
            status_code=status.HTTP_302_FOUND
        )
    
    if not code:
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/login?error=No authorization code received",
            status_code=status.HTTP_302_FOUND
        )
    
    redirect_uri = str(request.url_for("auth_callback"))
    try:
        user, access_token, refresh_token = auth_service.process_google_callback(code, redirect_uri)
        
        # Log the login action
        log_service.log_action(
            user_id=user.id,
            action_type="LOGIN",
            details={
                "method": "google_oauth",
                "ip_address": request.client.host if request.client else None,
            }
        )
        
        # Create redirect response with access token in URL
        response = RedirectResponse(
            url=f"{settings.FRONTEND_URL}/auth/callback?token={access_token}",
            status_code=status.HTTP_302_FOUND
        )
        
        # Set refresh token in HTTP-only cookie for security
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=True,  # Only send over HTTPS in production
            samesite="lax",
            max_age=7 * 24 * 60 * 60,  # 7 days
            path="/",
        )
        
        return response
    except Exception as e:
        # Redirect to frontend with error
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/auth/callback?error={str(e)}",
            status_code=status.HTTP_302_FOUND
        )


@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    response: Response,
    auth_service: AuthServiceDependency,
):
    """
    Refresh access token using refresh token from HTTP-only cookie.
    Returns new access token and sets new refresh token in cookie.
    """
    # Get refresh token from cookie
    refresh_token_value = request.cookies.get("refresh_token")
    
    if not refresh_token_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found",
        )
    
    new_access_token, new_refresh_token = auth_service.refresh_access_token(refresh_token_value)
    
    # Set new refresh token in HTTP-only cookie
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,  # 7 days
        path="/",
    )
    
    return TokenResponse(
        access_token=new_access_token,
        refresh_token="",  # Don't send refresh token in response body
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
async def logout(
    current_user: CurrentUserDependency,
    log_service: UserActionLogServiceDependency,
    request: Request,
    response: Response,
):
    """
    Logout current user and clear refresh token cookie.
    Client should also discard the access token.
    """
    # Log the logout action
    log_service.log_action(
        user_id=current_user.id,
        action_type="LOGOUT",
        details={
            "ip_address": request.client.host if request.client else None,
        }
    )
    
    # Clear the refresh token cookie
    response.delete_cookie(
        key="refresh_token",
        path="/",
        httponly=True,
        secure=True,
        samesite="lax",
    )
    
    return {"message": "Successfully logged out"}


@auth_router.post("/refresh-google-token", response_model=dict)
async def refresh_google_token(
    current_user: CurrentUserDependency,
    auth_service: AuthServiceDependency,
):
    """
    Refresh the user's Google access token using their stored Google refresh token.
    This is useful when the Google token expires but the app session is still valid.
    """
    new_google_token = auth_service.refresh_google_token(current_user)
    return {
        "google_access_token": new_google_token,
        "message": "Google token refreshed successfully"
    }
