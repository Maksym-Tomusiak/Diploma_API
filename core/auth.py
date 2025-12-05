from datetime import datetime, timedelta
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from common.app_settings import settings
from crud import UserRepository, UserRepositoryDependency
from models import User


# JWT Configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # 1 hour
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Google OAuth Configuration
GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/documents.readonly",
]

security = HTTPBearer()


class AuthService:
    def __init__(self, user_repository: UserRepositoryDependency):
        self.user_repository = user_repository

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token."""
        to_encode = data.copy()
        expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
        to_encode.update({"exp": expire, "type": "access"})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)

    def create_refresh_token(self, data: dict) -> str:
        """Create a JWT refresh token with longer expiration."""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)

    def verify_token(self, token: str, token_type: str = "access") -> dict:
        """Verify and decode a JWT token."""
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
            if payload.get("type") != token_type:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid token type. Expected {token_type}",
                )
            return payload
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def get_google_auth_flow(self, redirect_uri: str) -> Flow:
        """Create Google OAuth flow."""
        client_config = {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        }
        flow = Flow.from_client_config(client_config, scopes=GOOGLE_SCOPES)
        flow.redirect_uri = redirect_uri
        return flow

    def get_authorization_url(self, redirect_uri: str) -> str:
        """Generate Google OAuth authorization URL."""
        flow = self.get_google_auth_flow(redirect_uri)
        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return authorization_url

    def process_google_callback(self, code: str, redirect_uri: str) -> tuple[User, str, str]:
        """
        Process Google OAuth callback.
        Returns: (user, access_token, refresh_token)
        """
        flow = self.get_google_auth_flow(redirect_uri)
        flow.fetch_token(code=code)

        credentials = flow.credentials

        # Get user info from Google
        service = build("oauth2", "v2", credentials=credentials)
        user_info = service.userinfo().get().execute()

        email = user_info.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not retrieve email from Google",
            )

        # Find or create user
        user = self.user_repository.get_user_by_email(email)
        if not user:
            user = User(email=email)
            user = self.user_repository.create_user(user)

        # Store Google tokens
        user.google_token = credentials.token
        if credentials.refresh_token:
            user.google_refresh_token = credentials.refresh_token
        self.user_repository.update_user(user)

        # Generate JWT tokens
        token_data = {"sub": str(user.id), "email": user.email}
        access_token = self.create_access_token(token_data)
        refresh_token = self.create_refresh_token(token_data)

        return user, access_token, refresh_token

    def refresh_access_token(self, refresh_token: str) -> tuple[str, str]:
        """
        Refresh the access token using a refresh token.
        Returns: (new_access_token, new_refresh_token)
        """
        payload = self.verify_token(refresh_token, token_type="refresh")

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        user = self.user_repository.get_user_by_id(int(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        # Generate new tokens
        token_data = {"sub": str(user.id), "email": user.email}
        new_access_token = self.create_access_token(token_data)
        new_refresh_token = self.create_refresh_token(token_data)

        return new_access_token, new_refresh_token

    def get_current_user_from_token(self, token: str) -> User:
        """Get the current user from a JWT token."""
        payload = self.verify_token(token, token_type="access")

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        user = self.user_repository.get_user_by_id(int(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        return user


AuthServiceDependency = Annotated[AuthService, Depends(AuthService)]


# Dependency to get current user from request
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthServiceDependency = None,
) -> User:
    """FastAPI dependency to get the current authenticated user."""
    return auth_service.get_current_user_from_token(credentials.credentials)


CurrentUserDependency = Annotated[User, Depends(get_current_user)]


# Dependency to require admin role
async def require_admin(current_user: CurrentUserDependency) -> User:
    """FastAPI dependency that requires admin role."""
    from models.user import UserRole
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


AdminUserDependency = Annotated[User, Depends(require_admin)]
