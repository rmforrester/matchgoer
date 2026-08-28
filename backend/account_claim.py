"""Transactional account conversion for new and existing Matchgoer identities."""

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
from models import (
    AccountConversionHandoff,
    AccountMergeAudit,
    AnonymousSession,
    InterestedFixture,
    User,
    UserIdentity,
    UserProfile,
)


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
        raise _claim_error(401, "ANONYMOUS_SESSION_REQUIRED", "An anonymous Matchgoer session is required")
    issued_at = now or datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=_handoff_max_age_seconds())
    raw_token = secrets.token_urlsafe(32)
    with db.begin():
        anonymous_session = db.query(AnonymousSession).filter(
            AnonymousSession.session_id == session_id,
        ).with_for_update().first()
        if anonymous_session is None or anonymous_session.revoked_at is not None:
            raise _claim_error(401, "ANONYMOUS_SESSION_INVALID", "The anonymous Matchgoer session is invalid")
        user = db.query(User).filter(User.user_id == anonymous_session.user_id).with_for_update().first()
        if user is None or user.account_status != "anonymous" or not user.is_anonymous:
            raise _claim_error(403, "ACCOUNT_NOT_CLAIMABLE", "This Matchgoer identity cannot be claimed")
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
        raise _claim_error(401, "ANONYMOUS_SESSION_REQUIRED", "An anonymous Matchgoer session is required")

    claimed_at = now or datetime.now(timezone.utc)
    with db.begin():
        handoff = None
        if handoff_token:
            handoff = db.query(AccountConversionHandoff).filter(
                AccountConversionHandoff.token_digest == _handoff_digest(handoff_token),
            ).with_for_update().first()
            if handoff is None:
                raise _claim_error(401, "ACCOUNT_HANDOFF_INVALID", "Account conversion could not be verified")
            if handoff.consumed_at is not None:
                if (
                    handoff.claimed_issuer == provider_identity.issuer
                    and handoff.claimed_subject == provider_identity.subject
                ):
                    audit = db.query(AccountMergeAudit).filter(
                        AccountMergeAudit.source_user_id == handoff.user_id,
                    ).first()
                    replay_user_id = audit.target_user_id if audit is not None else handoff.user_id
                    replay_user = db.query(User).filter(User.user_id == replay_user_id).with_for_update().first()
                    mapping = db.query(UserIdentity).filter(
                        UserIdentity.issuer == provider_identity.issuer,
                        UserIdentity.subject == provider_identity.subject,
                        UserIdentity.user_id == replay_user_id,
                    ).first()
                    if replay_user is not None and mapping is not None and replay_user.account_status == "registered":
                        return _result(db, replay_user, idempotent=True)
                raise _claim_error(409, "ACCOUNT_HANDOFF_USED", "Account conversion has already been used")
            if handoff.expires_at < claimed_at:
                raise _claim_error(401, "ACCOUNT_HANDOFF_EXPIRED", "Account conversion has expired")

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
            raise _claim_error(401, "ANONYMOUS_SESSION_INVALID", "The anonymous Matchgoer session is invalid")

        user = (
            db.query(User)
            .filter(User.user_id == anonymous_session.user_id)
            .with_for_update()
            .first()
        )
        if user is None:
            raise _claim_error(401, "ANONYMOUS_SESSION_INVALID", "The anonymous Matchgoer session is invalid")
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
                return _merge_into_existing_account(
                    db,
                    source_user=user,
                    source_session=anonymous_session,
                    target_user_id=existing_identity.user_id,
                    provider_identity=provider_identity,
                    claimed_at=claimed_at,
                    failure_hook=failure_hook,
                )
            if user.account_status != "registered" or user.is_anonymous:
                raise _claim_error(
                    409,
                    "CLAIM_STATE_INVALID",
                    "This Matchgoer identity is not in a valid claimed state",
                )
            return _result(db, user, idempotent=True)

        if user.account_status != "anonymous" or not user.is_anonymous:
            if user.account_status == "registered":
                raise _claim_error(
                    409,
                    "ACCOUNT_ALREADY_REGISTERED",
                    "Account linking is not available through the new-account claim flow",
                )
            raise _claim_error(403, "ACCOUNT_NOT_CLAIMABLE", "This Matchgoer identity cannot be claimed")
        if anonymous_session.revoked_at is not None:
            raise _claim_error(401, "ANONYMOUS_SESSION_REVOKED", "The anonymous Matchgoer session is no longer active")

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


def _merge_into_existing_account(
    db: Session,
    *,
    source_user: User,
    source_session: AnonymousSession,
    target_user_id: int,
    provider_identity: VerifiedProviderIdentity,
    claimed_at: datetime,
    failure_hook: Callable[[str], None] | None,
) -> AccountClaimResult:
    """Merge only anonymous-owned state supported by the product today.

    InterestedFixture collision policy: retain the target row, delete the source
    duplicate, then transfer every remaining source row. FixtureMeetingIntent and
    all profile-backed social state cannot be created anonymously and are not
    transferred. SocialEvent remains historical telemetry under the source user.
    """
    target_user = db.query(User).filter(User.user_id == target_user_id).with_for_update().first()
    if target_user is None or target_user.account_status != "registered" or target_user.is_anonymous:
        raise _claim_error(409, "CLAIM_TARGET_INVALID", "The registered Matchgoer account is not available")
    if source_user.account_status != "anonymous" or not source_user.is_anonymous:
        raise _claim_error(409, "CLAIM_SOURCE_INVALID", "The anonymous Matchgoer identity is not claimable")
    if source_session.revoked_at is not None:
        raise _claim_error(401, "ANONYMOUS_SESSION_REVOKED", "The anonymous Matchgoer session is no longer active")

    source_interests = db.query(InterestedFixture).filter(
        InterestedFixture.user_id == source_user.user_id,
    ).with_for_update().all()
    fixture_ids = [row.fixture_id for row in source_interests]
    target_fixture_ids = set()
    if fixture_ids:
        target_fixture_ids = {
            row.fixture_id for row in db.query(InterestedFixture).filter(
                InterestedFixture.user_id == target_user.user_id,
                InterestedFixture.fixture_id.in_(fixture_ids),
            ).with_for_update().all()
        }
    for interest in source_interests:
        if interest.fixture_id in target_fixture_ids:
            db.delete(interest)
        else:
            interest.user_id = target_user.user_id
    db.flush()
    if failure_hook:
        failure_hook("after_interest_merge")

    db.add(AccountMergeAudit(
        source_user_id=source_user.user_id,
        target_user_id=target_user.user_id,
        merge_source="account_conversion",
        reason="Authenticated provider identity already belonged to the target account",
        merged_at=claimed_at,
    ))
    source_user.account_status = "merged"
    source_user.is_anonymous = False
    source_user.merged_into_user_id = target_user.user_id
    if failure_hook:
        failure_hook("after_merge_audit")

    source_sessions = db.query(AnonymousSession).filter(
        AnonymousSession.user_id == source_user.user_id,
    ).with_for_update().all()
    for session in source_sessions:
        session.revoked_at = session.revoked_at or claimed_at
    handoffs = db.query(AccountConversionHandoff).filter(
        AccountConversionHandoff.user_id == source_user.user_id,
        AccountConversionHandoff.consumed_at.is_(None),
    ).with_for_update().all()
    for handoff in handoffs:
        handoff.consumed_at = claimed_at
        handoff.claimed_issuer = provider_identity.issuer
        handoff.claimed_subject = provider_identity.subject
    db.flush()
    if failure_hook:
        failure_hook("after_source_revocation")
    return _result(db, target_user, idempotent=False)


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
