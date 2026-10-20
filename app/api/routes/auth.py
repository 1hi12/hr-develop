"""Authentication routes and dependencies."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional

from app.infrastructure.auth.azure_auth import AzureAuthService, AzureUser
from app.config.settings import get_settings


router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()


def get_azure_auth_service() -> AzureAuthService:
    """Get Azure Auth Service instance."""
    settings = get_settings()
    return AzureAuthService(
        tenant_id=settings.azure_tenant_id,
        client_id=settings.azure_client_id
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    azure_service: AzureAuthService = Depends(get_azure_auth_service)
) -> AzureUser:
    """
    Dependency to extract and validate current user from JWT token.
    
    Usage:
        @app.get("/protected")
        async def protected_route(user: AzureUser = Depends(get_current_user)):
            return {"message": f"Hello {user.name}"}
    """
    token = credentials.credentials
    user = azure_service.verify_token(token)
    return user


class TokenVerifyRequest(BaseModel):
    """Request model for token verification."""
    access_token: str


class TokenVerifyResponse(BaseModel):
    """Response model for token verification."""
    valid: bool
    user: Optional[AzureUser] = None
    error: Optional[str] = None


class UserInfoResponse(BaseModel):
    """Response model for user info."""
    email: str
    name: Optional[str]
    oid: str
    message: str


@router.post("/verify", response_model=TokenVerifyResponse)
async def verify_token(
    request: TokenVerifyRequest,
    azure_service: AzureAuthService = Depends(get_azure_auth_service)
):
    """
    Verify an Azure AD access token.
    
    This endpoint can be used by the frontend to validate tokens
    without accessing protected resources.
    """
    try:
        user = azure_service.verify_token(request.access_token)
        return TokenVerifyResponse(valid=True, user=user)
    except HTTPException as e:
        return TokenVerifyResponse(
            valid=False,
            error=e.detail
        )


@router.get("/me", response_model=UserInfoResponse)
async def get_user_info(user: AzureUser = Depends(get_current_user)):
    """
    Get current authenticated user information.
    
    This is a protected endpoint that requires a valid JWT token.
    """
    return UserInfoResponse(
        email=user.email,
        name=user.name,
        oid=user.oid,
        message=f"Authenticated as {user.email}"
    )


@router.get("/protected")
async def protected_example(user: AzureUser = Depends(get_current_user)):
    """
    Example protected endpoint.
    
    Any route that uses `Depends(get_current_user)` will automatically
    require a valid Azure AD JWT token.
    """
    return {
        "message": "This is a protected endpoint",
        "user": user.email,
        "user_id": user.oid
    }


@router.post("/refresh-keys")
async def refresh_jwks_cache(
    user: AzureUser = Depends(get_current_user),
    azure_service: AzureAuthService = Depends(get_azure_auth_service)
):
    """
    Refresh the JWKS cache.
    
    Useful when Azure rotates signing keys.
    Requires authentication.
    """
    azure_service.clear_cache()
    return {"message": "JWKS cache cleared successfully"}
