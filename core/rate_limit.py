from typing import Annotated

from fastapi import Depends, HTTPException, status, Request

from crud.anonymous_check import AnonymousCheckRepository, AnonymousCheckRepositoryDependency


# Constants for anonymous user limits
ANONYMOUS_DAILY_CHECK_LIMIT = 10


class RateLimitService:
    """Service for managing rate limits for anonymous users."""
    
    def __init__(self, anonymous_check_repository: AnonymousCheckRepositoryDependency):
        self.anonymous_check_repository = anonymous_check_repository
    
    def _get_identifier(self, request: Request) -> str:
        """
        Generate a robust identifier for anonymous users.
        Uses X-Forwarded-For (for proxies), X-Fingerprint (from frontend),
        and User-Agent as a fallback.
        """
        # 1. Get real IP (handle proxies)
        ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
        
        # 2. Get fingerprint from header (provided by frontend)
        fingerprint = request.headers.get("X-Fingerprint")
        
        if fingerprint:
            # Combining IP and Fingerprint makes it harder to bypass with just a VPN
            # or just clearing local storage.
            return f"{ip}|{fingerprint}"
        
        # 3. Fallback: IP + User-Agent hash
        ua = request.headers.get("User-Agent", "unknown")
        import hashlib
        ua_hash = hashlib.md5(ua.encode()).hexdigest()[:8]
        return f"{ip}|{ua_hash}"

    def check_and_increment_anonymous_limit(self, request: Request) -> dict:
        """
        Check if anonymous user has exceeded daily limit and increment count.
        
        Returns:
            dict with remaining_checks count
            
        Raises:
            HTTPException if limit exceeded
        """
        identifier = self._get_identifier(request)
        current_count = self.anonymous_check_repository.get_check_count_today(identifier)
        
        if current_count >= ANONYMOUS_DAILY_CHECK_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Daily limit of {ANONYMOUS_DAILY_CHECK_LIMIT} free checks exceeded. Please register for unlimited checks.",
            )
        
        # Increment the count
        self.anonymous_check_repository.increment_check_count(identifier)
        
        remaining = ANONYMOUS_DAILY_CHECK_LIMIT - current_count - 1
        return {"remaining_checks": remaining}
    
    def get_remaining_checks(self, request: Request) -> int:
        """Get the number of remaining checks for an anonymous user today."""
        identifier = self._get_identifier(request)
        current_count = self.anonymous_check_repository.get_check_count_today(identifier)
        return max(0, ANONYMOUS_DAILY_CHECK_LIMIT - current_count)


RateLimitServiceDependency = Annotated[RateLimitService, Depends(RateLimitService)]
