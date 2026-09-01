"""Google / Apple identity verification and user upsert."""

from __future__ import annotations

import logging
import secrets
import uuid
from typing import Any

import httpx
from fastapi import HTTPException, status
from jose import jwt
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import create_access_token, hash_password
from app.config import settings
from app.models.database import User

logger = logging.getLogger(__name__)

GOOGLE_TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
APPLE_KEYS = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"
APPLE_AUTH = "https://appleid.apple.com/auth/authorize"
APPLE_TOKEN = "https://appleid.apple.com/auth/token"


def oauth_status() -> dict[str, bool]:
    return {
        "email": True,
        "google": bool(settings.google_oauth_client_id),
        "apple": bool(settings.apple_oauth_client_id),
    }


def google_authorize_url(state: str) -> str:
    if not settings.google_oauth_client_id:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured")
    redirect = f"{settings.api_public_url.rstrip('/')}/api/v1/auth/oauth/google/callback"
    from urllib.parse import urlencode

    qs = urlencode(
        {
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
    )
    return f"{GOOGLE_AUTH}?{qs}"


async def google_exchange_code(code: str) -> dict[str, Any]:
    redirect = f"{settings.api_public_url.rstrip('/')}/api/v1/auth/oauth/google/callback"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            GOOGLE_TOKEN,
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": redirect,
                "grant_type": "authorization_code",
            },
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail=f"Google token exchange failed: {resp.text[:200]}")
        return resp.json()


async def verify_google_id_token(id_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(GOOGLE_TOKENINFO, params={"id_token": id_token})
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid Google ID token")
        data = resp.json()
    aud = data.get("aud")
    if settings.google_oauth_client_id and aud != settings.google_oauth_client_id:
        raise HTTPException(status_code=401, detail="Google token audience mismatch")
    email = data.get("email")
    sub = data.get("sub")
    if not email or not sub:
        raise HTTPException(status_code=401, detail="Google token missing email")
    return {
        "provider": "google",
        "sub": sub,
        "email": email,
        "name": data.get("name") or email.split("@")[0],
    }


def apple_client_secret() -> str:
    if not (
        settings.apple_oauth_client_id
        and settings.apple_oauth_team_id
        and settings.apple_oauth_key_id
        and settings.apple_oauth_private_key
    ):
        raise HTTPException(status_code=400, detail="Apple web OAuth is not fully configured")
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    pem = settings.apple_oauth_private_key.replace("\\n", "\n")
    return jwt.encode(
        {
            "iss": settings.apple_oauth_team_id,
            "iat": now,
            "exp": now + timedelta(minutes=15),
            "aud": APPLE_ISSUER,
            "sub": settings.apple_oauth_client_id,
        },
        pem,
        algorithm="ES256",
        headers={"kid": settings.apple_oauth_key_id},
    )


def apple_authorize_url(state: str) -> str:
    if not settings.apple_oauth_client_id:
        raise HTTPException(status_code=400, detail="Apple Sign In is not configured")
    redirect = f"{settings.api_public_url.rstrip('/')}/api/v1/auth/oauth/apple/callback"
    from urllib.parse import urlencode

    qs = urlencode(
        {
            "client_id": settings.apple_oauth_client_id,
            "redirect_uri": redirect,
            "response_type": "code",
            "response_mode": "form_post",
            "scope": "name email",
            "state": state,
        }
    )
    return f"{APPLE_AUTH}?{qs}"


async def apple_exchange_code(code: str) -> dict[str, Any]:
    redirect = f"{settings.api_public_url.rstrip('/')}/api/v1/auth/oauth/apple/callback"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            APPLE_TOKEN,
            data={
                "client_id": settings.apple_oauth_client_id,
                "client_secret": apple_client_secret(),
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect,
            },
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail=f"Apple token exchange failed: {resp.text[:200]}")
        return resp.json()


async def verify_apple_identity_token(identity_token: str) -> dict[str, Any]:
    if not settings.apple_oauth_client_id:
        raise HTTPException(status_code=400, detail="Apple Sign In is not configured")
    async with httpx.AsyncClient(timeout=15.0) as client:
        keys_resp = await client.get(APPLE_KEYS)
        keys_resp.raise_for_status()
        keys = keys_resp.json()
    header = jwt.get_unverified_header(identity_token)
    kid = header.get("kid")
    key = next((k for k in keys.get("keys", []) if k.get("kid") == kid), None)
    if not key:
        raise HTTPException(status_code=401, detail="Apple signing key not found")
    try:
        claims = jwt.decode(
            identity_token,
            key,
            algorithms=["RS256"],
            audience=settings.apple_oauth_client_id,
            issuer=APPLE_ISSUER,
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Apple token: {e}") from e
    sub = claims.get("sub")
    email = claims.get("email") or f"{sub}@privaterelay.appleid.com"
    if not sub:
        raise HTTPException(status_code=401, detail="Apple token missing subject")
    return {"provider": "apple", "sub": sub, "email": email, "name": email.split("@")[0]}


async def upsert_oauth_user(db: AsyncSession, identity: dict[str, Any]) -> User:
    provider = identity["provider"]
    sub = identity["sub"]
    email = identity["email"]
    result = await db.execute(
        select(User).where(
            or_(
                (User.auth_provider == provider) & (User.oauth_sub == sub),
                User.email == email,
            )
        )
    )
    user = result.scalars().first()
    if user:
        user.auth_provider = provider
        user.oauth_sub = sub
        if not user.email:
            user.email = email
        await db.commit()
        await db.refresh(user)
        return user

    base = (identity.get("name") or email.split("@")[0])[:40].replace(" ", "_")
    username = base
    n = 0
    while True:
        clash = await db.execute(select(User).where(User.username == username))
        if clash.scalar_one_or_none() is None:
            break
        n += 1
        username = f"{base}_{n}"

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        auth_provider=provider,
        oauth_sub=sub,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def issue_token(user: User) -> str:
    return create_access_token(user.id, user.username)


def frontend_callback_url(token: str) -> str:
    return f"{settings.frontend_url.rstrip('/')}/auth/callback?token={token}"
