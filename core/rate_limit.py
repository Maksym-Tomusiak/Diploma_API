from typing import Annotated

from fastapi import Depends, HTTPException, status, Request

from crud.anonymous_check import AnonymousCheckRepository, AnonymousCheckRepositoryDependency


# Constants for anonymous user limits
ANONYMOUS_DAILY_CHECK_LIMIT = 10


class RateLimitService:
    """Service for managing rate limits for anonymous users."""
    
    def __init__(self, anonymous_check_repository: AnonymousCheckRepositoryDependency):
        self.anonymous_check_repository = anonymous_check_repository
    
    def check_and_increment_anonymous_limit(self, ip_address: str) -> dict:
        """
        Check if anonymous user has exceeded daily limit and increment count.
        
        Returns:
            dict with remaining_checks count
            
        Raises:
            HTTPException if limit exceeded
        """
        current_count = self.anonymous_check_repository.get_check_count_today(ip_address)
        
        if current_count >= ANONYMOUS_DAILY_CHECK_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Daily limit of {ANONYMOUS_DAILY_CHECK_LIMIT} free checks exceeded. Please register for unlimited checks.",
            )
        
        # Increment the count
        self.anonymous_check_repository.increment_check_count(ip_address)
        
        remaining = ANONYMOUS_DAILY_CHECK_LIMIT - current_count - 1
        return {"remaining_checks": remaining}
    
    def get_remaining_checks(self, ip_address: str) -> int:
        """Get the number of remaining checks for an anonymous user today."""
        current_count = self.anonymous_check_repository.get_check_count_today(ip_address)
        return max(0, ANONYMOUS_DAILY_CHECK_LIMIT - current_count)


RateLimitServiceDependency = Annotated[RateLimitService, Depends(RateLimitService)]
