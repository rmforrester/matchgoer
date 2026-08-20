"""Transactional new-account claiming without cross-user merge behavior."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Callable

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from identity import VerifiedProviderIdentity
from models import AnonymousSession, User, UserIdentity, UserProfile


@dataclass(frozen=True)
class AccountClaimResult:
    user_id: int
    account_status: str
    claimed: bool
    idempotent: bool
    profile_complete: bool


def _claim_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def claim_anonymous_user(
    db: Session,
    *,
    session_id: str | None,
    provider_identity: VerifiedProviderIdentity,
    failure_hook: Callable[[str], None] | None = None,
) -> AccountClaimResult:
    if not session_id:
        raise _claim_error(401, "ANONYMOUS_SESSION_REQUIRED", "An anonymous Terrace Talk session is required")

    with db.begin():
        anonymous_session = (
            db.query(AnonymousSession)
            .filter(AnonymousSession.session_id == session_id)
            .with_for_update()
            .first()
        )
        if anonymous_session is None:
            raise _claim_error(401, "ANONYMOUS_SESSION_INVALID", "The anonymous Terrace Talk session is invalid")

        user = (
            db.query(User)
            .filter(User.user_id == anonymous_session.user_id)
            .with_for_update()
            .first()
        )
        if user is None:
            raise _claim_error(401, "ANONYMOUS_SESSION_INVALID", "The anonymous Terrace Talk session is invalid")

        identity_key = json.dumps(
            [provider_identity.issuer, provider_identity.subject],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:identity_key, 0))"),
            {"identity_key": identity_key},
        )

        existing_identity = (
            db.query(UserIdentity)
            .filter(
                UserIdentity.issuer == provider_identity.issuer,
                UserIdentity.subject == provider_identity.subject,
            )
            .with_for_update()
            .first()
        )

        if existing_identity is not None:
            if existing_identity.user_id != user.user_id:
                raise _claim_error(
                    409,
                    "IDENTITY_ALREADY_LINKED",
                    "This identity belongs to an existing Terrace Talk account",
                )
            if user.account_status != "registered" or user.is_anonymous:
                raise _claim_error(
                    409,
                    "CLAIM_STATE_INVALID",
                    "This Terrace Talk identity is not in a valid claimed state",
                )
            return _result(db, user, idempotent=True)

        if user.account_status != "anonymous" or not user.is_anonymous:
            if user.account_status == "registered":
                raise _claim_error(
                    409,
                    "ACCOUNT_ALREADY_REGISTERED",
                    "Account linking is not available through the new-account claim flow",
                )
            raise _claim_error(403, "ACCOUNT_NOT_CLAIMABLE", "This Terrace Talk identity cannot be claimed")
        if anonymous_session.revoked_at is not None:
            raise _claim_error(401, "ANONYMOUS_SESSION_REVOKED", "The anonymous Terrace Talk session is no longer active")

        mapping = UserIdentity(
            user_id=user.user_id,
            issuer=provider_identity.issuer,
            subject=provider_identity.subject,
            email=provider_identity.email,
            email_verified_at=provider_identity.email_verified_at,
        )
        db.add(mapping)
        db.flush()
        if failure_hook:
            failure_hook("after_identity")

        user.account_status = "registered"
        user.is_anonymous = False
        user.registered_at = datetime.now(timezone.utc)
        db.flush()
        if failure_hook:
            failure_hook("after_user")

        anonymous_session.revoked_at = datetime.now(timezone.utc)
        db.flush()
        return _result(db, user, idempotent=False)


def _result(db: Session, user: User, *, idempotent: bool) -> AccountClaimResult:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.user_id).first()
    profile_complete = bool(
        profile
        and profile.username
        and profile.username.strip()
        and profile.display_name
        and profile.display_name.strip()
    )
    return AccountClaimResult(
        user_id=user.user_id,
        account_status=user.account_status,
        claimed=True,
        idempotent=idempotent,
        profile_complete=profile_complete,
    )
