"""JWT authentication helpers for the TrustIQ API.

Provides a token-issuing helper and a FastAPI dependency that validates the
``Authorization: Bearer <token>`` header. For demo convenience a static
``/api/token`` endpoint issues tokens; in production this would integrate with
the bank's IdP.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from config import get_settings

logger = logging.getLogger("trustiq.auth")

_bearer = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def create_access_token(subject: str) -> str:
    """Create a signed JWT access token.

    Args:
        subject: The principal (e.g. analyst username) the token represents.

    Returns:
        An encoded JWT string.
    """
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """FastAPI dependency that validates a bearer token.

    Args:
        credentials: The parsed Authorization header credentials.

    Returns:
        The token subject on success.

    Raises:
        HTTPException: 401 if the token is missing or invalid.
    """
    settings = get_settings()
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload.get("sub", "unknown")
    except JWTError as exc:
        logger.warning("Token validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_api_key(
    api_key: Optional[str] = Depends(_api_key_header),
) -> str:
    """FastAPI dependency that validates the integration ``X-API-Key`` header.

    Channels that submit events for scoring (e.g. the Bank of Baroda core
    simulator) must present the shared integration API key. This keeps the
    public scoring endpoint from being called by unauthorised clients.

    Args:
        api_key: The value of the ``X-API-Key`` request header.

    Returns:
        The validated API key on success.

    Raises:
        HTTPException: 401 if the key is missing or does not match.
    """
    settings = get_settings()
    if not api_key or api_key != settings.trustiq_api_key:
        logger.warning("Rejected trust-evaluate call with missing/invalid API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-API-Key",
        )
    return api_key
