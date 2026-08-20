"""Transactional new-account claiming without cross-user merge behavior."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import secrets
from typing import Callable

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from identity import VerifiedProviderIdentity
from models import AccountConversionHandoff, AnonymousSession, User, UserIdentity, UserProfile


DEFAULT_HANDOFF_MAX_AGE_SECONDS = 60 * 60 * 24


@dataclass(frozen=True)
class AccountClaimResult:
    user_id: int
    account_status: str
    claimed: bool
    idempotent: bool
    profile_complete: bool


def _claim_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _handoff_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _handoff_max_age_seconds() -> int:
    raw = os.getenv("TERRACE_ACCOUNT_HANDOFF_MAX_AGE_SECONDS", str(DEFAULT_HANDOFF_MAX_AGE_SECONDS))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_HANDOFF_MAX_AGE_SECONDS
    return value if value > 0 else DEFAULT_HANDOFF_MAX_AGE_SECONDS


def issue_account_conversion_handoff(
    db: Session,
    *,
    session_id: str | None,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    if not session_id:
        raise _claim_error(401, "ANONYMOUS_SESSION_REQUIRED", "An anonymous Terrace Talk session is required")
    issued_at = now or datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=_handoff_max_age_seconds())
    raw_token = secrets.token_urlsafe(32)
    with db.begin():
        anonymous_session = db.query(AnonymousSession).filter(
            AnonymousSession.session_id == session_id,
        ).with_for_update().first()
        if anonymous_session is None or anonymous_session.revoked_at is not None:
            raise _claim_error(401, "ANONYMOUS_SESSION_INVALID", "The anonymous Terrace Talk session is invalid")
        user = db.query(User).filter(User.user_id == anonymous_session.user_id).with_for_update().first()
        if user is None or user.account_status != "anonymous" or not user.is_anonymous:
            raise _claim_error(403, "ACCOUNT_NOT_CLAIMABLE", "This Terrace Talk identity cannot be claimed")
        db.add(AccountConversionHandoff(
            token_digest=_handoff_digest(raw_token),
            session_id=session_id,
            user_id=user.user_id,
            expires_at=expires_at,
        ))
    return raw_token, expires_at


def claim_anonymous_user(
    db: Session,
    *,
    session_id: str | None,
    handoff_token: str | None = None,
    provider_identity: VerifiedProviderIdentity,
    failure_hook: Callable[[str], None] | None = None,
    now: datetime | None = None,
) -> AccountClaimResult:
    if not session_id and not handoff_token:
        raise _claim_error(401, "ANONYMOUS_SESSION_REQUIRED", "An anonymous Terrace Talk session is required")

    claimed_at = now or datetime.now(timezone.utc)
    with db.begin():
        handoff = None
        if handoff_token:
            handoff = db.query(AccountConversionHandoff).filter(
                AccountConversionHandoff.token_digest == _handoff_digest(handoff_token),
            ).with_for_update().first()
            if handoff is None:
                raise _claim_error(401, "ACCOUNT_HANDOFF_INVALID", "Account conversion could not be verified")
            if handoff.expires_at < claimed_at:
                raise _claim_error(401, "ACCOUNT_HANDOFF_EXPIRED", "Account conversion has expired")
            if handoff.consumed_at is not None:
                if handoff.claimed_issuer == provider_identity.issuer and handoff.claimed_subject == provider_identity.subject:
                    replay_user = db.query(User).filter(User.user_id == handoff.user_id).with_for_update().first()
                    mapping = db.query(UserIdentity).filter(
                        UserIdentity.issuer == provider_identity.issuer,
                        UserIdentity.subject == provider_identity.subject,
                        UserIdentity.user_id == handoff.user_id,
                    ).first()
                    if replay_user is not None and mapping is not None and replay_user.account_status == "registered":
                        return _result(db, replay_user, idempotent=True)
                raise _claim_error(409, "ACCOUNT_HANDOFF_USED", "Account conversion has already been used")

        selected_session_id = handoff.session_id if handoff is not None else session_id
        if handoff is not None and session_id and session_id != handoff.session_id:
            raise _claim_error(409, "ACCOUNT_HANDOFF_SESSION_MISMATCH", "Account conversion does not match this browser session")
        anonymous_session = (
            db.query(AnonymousSession)
            .filter(AnonymousSession.session_id == selected_session_id)
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
        if handoff is not None and (handoff.user_id != user.user_id or handoff.session_id != anonymous_session.session_id):
            raise _claim_error(409, "ACCOUNT_HANDOFF_OWNER_MISMATCH", "Account conversion owner could not be verified")

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
        user.registered_at = claimed_at
        db.flush()
        if failure_hook:
            failure_hook("after_user")

        anonymous_session.revoked_at = claimed_at
        handoffs = db.query(AccountConversionHandoff).filter(
            AccountConversionHandoff.session_id == anonymous_session.session_id,
            AccountConversionHandoff.consumed_at.is_(None),
        ).with_for_update().all()
        for issued_handoff in handoffs:
            issued_handoff.consumed_at = claimed_at
            issued_handoff.claimed_issuer = provider_identity.issuer
            issued_handoff.claimed_subject = provider_identity.subject
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
