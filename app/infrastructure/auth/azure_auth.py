"""Microsoft Azure AD authentication and JWT validation."""
from functools import lru_cache
from typing import Optional, Dict, Any
import requests
from jose import jwt, JWTError
from fastapi import HTTPException, status
from pydantic import BaseModel


class AzureUser(BaseModel):
    """Azure AD user information."""
    email: str
    name: Optional[str] = None
    oid: str  # Object ID (unique user identifier)
    preferred_username: Optional[str] = None
    tenant_id: str


class AzureAuthService:
    """Service for validating Microsoft Azure AD JWT tokens."""
    
    def __init__(self, tenant_id: str, client_id: str):
        """
        Initialize Azure Auth Service.
        
        Args:
            tenant_id: Azure AD Tenant ID
            client_id: Application (client) ID from Azure portal
        """
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
        self.issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
    
    @lru_cache(maxsize=1)
    def _get_jwks(self) -> Dict[str, Any]:
        """
        Fetch and cache JWKS (JSON Web Key Set) from Azure.
        
        Returns:
            JWKS containing public keys for token verification
        """
        try:
            response = requests.get(self.jwks_url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to fetch Azure JWKS: {str(e)}"
            )
    
    def _get_signing_key(self, token_header: Dict[str, str]) -> Dict[str, Any]:
        """
        Get the signing key from JWKS that matches the token's key ID.
        
        Args:
            token_header: Unverified JWT header containing 'kid'
            
        Returns:
            Signing key for verification
        """
        jwks = self._get_jwks()
        kid = token_header.get("kid")
        
        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token header missing 'kid'"
            )
        
        try:
            key = next(k for k in jwks["keys"] if k["kid"] == kid)
            return key
        except StopIteration:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Signing key not found in JWKS"
            )
    
    def verify_token(self, token: str) -> AzureUser:
        """
        Verify and decode Azure AD JWT token.
        
        Args:
            token: JWT access token from Azure AD
            
        Returns:
            AzureUser with user information from token claims
            
        Raises:
            HTTPException: If token is invalid, expired, or malformed
        """
        try:
            # Get unverified header to find the correct signing key
            header = jwt.get_unverified_header(token)
            
            # Get the signing key from JWKS
            key = self._get_signing_key(header)
            
            # Decode and verify the token
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=self.issuer,
                options={
                    "verify_signature": True,
                    "verify_aud": True,
                    "verify_iss": True,
                    "verify_exp": True,
                }
            )
            
            # Extract user information from claims
            user = AzureUser(
                email=payload.get("email") or payload.get("preferred_username", ""),
                name=payload.get("name"),
                oid=payload["oid"],
                preferred_username=payload.get("preferred_username"),
                tenant_id=payload["tid"]
            )
            
            return user
            
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}"
            )
        except KeyError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token missing required claim: {str(e)}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token verification failed: {str(e)}"
            )
    
    def clear_cache(self):
        """Clear the JWKS cache (useful for key rotation)."""
        self._get_jwks.cache_clear()
