"""Central Matchgoer identity resolution for anonymous and future bearer clients."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
from threading import Lock
import urllib.error
import urllib.request

import jwt
from fastapi import Cookie, Header, HTTPException, Response
from jwt import PyJWKClient
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    ImmatureSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    InvalidTokenError,
    MissingRequiredClaimError,
    PyJWKClientError,
)
from sqlalchemy.orm import Session

from database import SessionLocal
from models import AnonymousSession, User, UserIdentity


logger = logging.getLogger("terrace_talk.auth")

ACTIVE_ACCOUNT_STATUSES = {"anonymous", "registered"}
BLOCKED_ACCOUNT_CODES = {
    "suspended": "ACCOUNT_SUSPENDED",
    "merged": "ACCOUNT_MERGED",
    "deleted": "ACCOUNT_DELETED",
}
ALLOWED_JWT_ALGORITHMS = ("ES256", "RS256")


@dataclass(frozen=True)
class ResolvedIdentity:
    user_id: int
    account_status: str
    is_registered: bool
    auth_mode: str
    issuer: str | None = None
    subject: str | None = None


@dataclass(frozen=True)
class SupabaseAuthConfig:
    enabled: bool
    issuer: str | None
    audience: str | None
    jwks_url: str | None
    jwks_timeout_seconds: float
    jwks_cache_seconds: float
    publishable_key: str | None = None
    provider_user_timeout_seconds: float = 3.0
    jwt_leeway_seconds: float = 60.0

    @classmethod
    def from_environment(cls) -> "SupabaseAuthConfig":
        return cls(
            enabled=os.getenv("SUPABASE_AUTH_ENABLED", "false").strip().lower()
            in {"1", "true", "yes", "on"},
            issuer=_clean_env("SUPABASE_JWT_ISSUER"),
            audience=_clean_env("SUPABASE_JWT_AUDIENCE"),
            jwks_url=_clean_env("SUPABASE_JWKS_URL"),
            jwks_timeout_seconds=_positive_float_env("SUPABASE_JWKS_TIMEOUT_SECONDS", 3.0),
            jwks_cache_seconds=_positive_float_env("SUPABASE_JWKS_CACHE_SECONDS", 300.0),
            publishable_key=_clean_env("SUPABASE_PUBLISHABLE_KEY"),
            provider_user_timeout_seconds=_positive_float_env(
                "SUPABASE_PROVIDER_USER_TIMEOUT_SECONDS", 3.0
            ),
            jwt_leeway_seconds=_positive_float_env("SUPABASE_JWT_LEEWAY_SECONDS", 60.0),
        )

    def require_complete(self) -> None:
        if not self.enabled:
            raise _auth_error(503, "BEARER_AUTH_DISABLED", "Bearer authentication is not enabled")
        if not self.issuer or not self.audience or not self.jwks_url:
            logger.error("Bearer authentication enabled with incomplete Supabase configuration")
            raise _auth_error(503, "AUTH_NOT_CONFIGURED", "Bearer authentication is not configured")

    def require_claim_verification(self) -> None:
        self.require_complete()
        if not self.publishable_key:
            logger.error("Account claiming enabled without a Supabase publishable key")
            raise _auth_error(
                503,
                "CLAIM_VERIFICATION_NOT_CONFIGURED",
                "Account claim verification is not configured",
            )


@dataclass(frozen=True)
class VerifiedProviderIdentity:
    issuer: str
    subject: str
    email: str | None
    email_verified_at: datetime | None
    provider: str | None


def anonymous_cookie_options() -> dict:
    production = os.getenv("TERRACE_ENV", "development").strip().lower() == "production"
    secure = os.getenv(
        "TERRACE_COOKIE_SECURE",
        "true" if production else "false",
    ).strip().lower() in {"1", "true", "yes", "on"}
    same_site = os.getenv("TERRACE_COOKIE_SAMESITE", "lax").strip().lower()
    if same_site not in {"lax", "strict", "none"}:
        raise RuntimeError("TERRACE_COOKIE_SAMESITE must be lax, strict, or none")
    if same_site == "none" and not secure:
        raise RuntimeError("TERRACE_COOKIE_SAMESITE=none requires TERRACE_COOKIE_SECURE=true")
    return {
        "httponly": True,
        "samesite": same_site,
        "secure": secure,
        "path": "/",
    }


def _clean_env(name: str) -> str | None:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else None


def _positive_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.error("Invalid numeric authentication configuration: %s", name)
        return default
    return value if value > 0 else default


def _auth_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


_jwks_clients: dict[tuple[str, float, float], PyJWKClient] = {}
_jwks_clients_lock = Lock()


def _jwks_client(config: SupabaseAuthConfig) -> PyJWKClient:
    assert config.jwks_url is not None
    cache_key = (config.jwks_url, config.jwks_timeout_seconds, config.jwks_cache_seconds)
    with _jwks_clients_lock:
        client = _jwks_clients.get(cache_key)
        if client is None:
            client = PyJWKClient(
                config.jwks_url,
                cache_keys=True,
                max_cached_keys=16,
                cache_jwk_set=True,
                lifespan=config.jwks_cache_seconds,
                timeout=config.jwks_timeout_seconds,
            )
            _jwks_clients[cache_key] = client
        return client


def _bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        logger.info("Bearer authentication rejected: malformed authorization header")
        raise _auth_error(401, "INVALID_AUTHORIZATION", "Invalid Authorization header")
    return parts[1]


def _verified_provider_claims(
    token: str,
    config: SupabaseAuthConfig,
    jwks_client: PyJWKClient | None = None,
) -> dict:
    config.require_complete()
    try:
        signing_key = (jwks_client or _jwks_client(config)).get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=list(ALLOWED_JWT_ALGORITHMS),
            issuer=config.issuer,
            audience=config.audience,
            options={
                "require": ["exp", "iss", "sub", "aud"],
                "verify_iat": False,
                "verify_nbf": False,
            },
        )
        now = datetime.now(timezone.utc).timestamp()
        for claim_name in ("iat", "nbf"):
            claim_value = payload.get(claim_name)
            if claim_value is None:
                continue
            if not isinstance(claim_value, (int, float)):
                raise DecodeError(f"{claim_name} must be numeric")
            if claim_value > now + config.jwt_leeway_seconds:
                raise ImmatureSignatureError(f"{claim_name} is in the future")
    except ExpiredSignatureError as exc:
        logger.info("Bearer authentication rejected: expired token")
        raise _auth_error(401, "TOKEN_EXPIRED", "Authentication token has expired") from exc
    except InvalidIssuerError as exc:
        logger.info("Bearer authentication rejected: wrong issuer")
        raise _auth_error(401, "INVALID_ISSUER", "Authentication token issuer is invalid") from exc
    except InvalidAudienceError as exc:
        logger.info("Bearer authentication rejected: wrong audience")
        raise _auth_error(401, "INVALID_AUDIENCE", "Authentication token audience is invalid") from exc
    except InvalidSignatureError as exc:
        logger.info("Bearer authentication rejected: invalid signature")
        raise _auth_error(401, "INVALID_SIGNATURE", "Authentication token signature is invalid") from exc
    except PyJWKClientError as exc:
        logger.info("Bearer authentication rejected: signing key unavailable")
        raise _auth_error(401, "TOKEN_KEY_UNAVAILABLE", "Authentication signing key is unavailable") from exc
    except ImmatureSignatureError as exc:
        logger.info("Bearer authentication rejected: token is not active yet")
        raise _auth_error(401, "TOKEN_NOT_ACTIVE", "Authentication token is not active yet") from exc
    except DecodeError as exc:
        logger.info("Bearer authentication rejected: malformed token")
        raise _auth_error(401, "INVALID_TOKEN_FORMAT", "Authentication token format is invalid") from exc
    except (MissingRequiredClaimError, InvalidTokenError) as exc:
        logger.info("Bearer authentication rejected: token validation failed (%s)", type(exc).__name__)
        raise _auth_error(401, "INVALID_TOKEN", "Authentication token is invalid") from exc

    issuer = payload.get("iss")
    subject = payload.get("sub")
    if not isinstance(issuer, str) or not issuer or not isinstance(subject, str) or not subject:
        raise _auth_error(401, "INVALID_TOKEN", "Authentication token is missing required identity claims")
    return payload


def _verified_provider_identity(
    token: str,
    config: SupabaseAuthConfig,
    jwks_client: PyJWKClient | None = None,
) -> tuple[str, str]:
    payload = _verified_provider_claims(token, config, jwks_client)
    return payload["iss"], payload["sub"]


def _load_provider_user(token: str, config: SupabaseAuthConfig) -> dict:
    config.require_claim_verification()
    assert config.issuer is not None and config.publishable_key is not None
    request = urllib.request.Request(
        f"{config.issuer.rstrip('/')}/user",
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": config.publishable_key,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=config.provider_user_timeout_seconds
        ) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            logger.info("Account claim rejected: provider did not confirm identity")
            raise _auth_error(
                403,
                "IDENTITY_NOT_VERIFIED",
                "The authentication provider did not confirm this identity",
            ) from exc
        logger.warning("Account claim provider verification failed with HTTP status=%s", exc.code)
        raise _auth_error(
            503,
            "PROVIDER_VERIFICATION_UNAVAILABLE",
            "The authentication provider could not be reached",
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Account claim provider verification unavailable (%s)", type(exc).__name__)
        raise _auth_error(
            503,
            "PROVIDER_VERIFICATION_UNAVAILABLE",
            "The authentication provider could not be reached",
        ) from exc


def verify_claim_provider_identity(
    authorization: str | None,
    *,
    config: SupabaseAuthConfig | None = None,
    jwks_client: PyJWKClient | None = None,
    provider_user_loader=None,
) -> VerifiedProviderIdentity:
    token = _bearer_token(authorization)
    if token is None:
        raise _auth_error(401, "BEARER_REQUIRED", "A verified bearer identity is required")
    active_config = config or SupabaseAuthConfig.from_environment()
    payload = _verified_provider_claims(token, active_config, jwks_client)
    loader = provider_user_loader or _load_provider_user
    provider_user = loader(token, active_config)
    if not isinstance(provider_user, dict) or provider_user.get("id") != payload["sub"]:
        logger.info("Account claim rejected: provider user did not match token subject")
        raise _auth_error(403, "IDENTITY_NOT_VERIFIED", "The provider identity could not be verified")
    if provider_user.get("is_anonymous") is not False:
        logger.info("Account claim rejected: provider identity is anonymous")
        raise _auth_error(403, "IDENTITY_NOT_VERIFIED", "A verified permanent identity is required")
    confirmed_at = provider_user.get("email_confirmed_at") or provider_user.get("confirmed_at")
    if not isinstance(confirmed_at, str) or not confirmed_at.strip():
        logger.info("Account claim rejected: provider identity is not confirmed")
        raise _auth_error(403, "IDENTITY_NOT_VERIFIED", "Confirm your identity before claiming an account")
    app_metadata = provider_user.get("app_metadata")
    provider = app_metadata.get("provider") if isinstance(app_metadata, dict) else None
    email = provider_user.get("email")
    email_verified_at = _parse_provider_datetime(confirmed_at)
    if email_verified_at is None:
        logger.info("Account claim rejected: provider confirmation timestamp is invalid")
        raise _auth_error(403, "IDENTITY_NOT_VERIFIED", "The provider identity could not be verified")
    return VerifiedProviderIdentity(
        issuer=payload["iss"],
        subject=payload["sub"],
        email=email if isinstance(email, str) and email else None,
        email_verified_at=email_verified_at,
        provider=provider if isinstance(provider, str) else None,
    )


def _parse_provider_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _resolved_user(user: User, auth_mode: str, issuer: str | None = None, subject: str | None = None) -> ResolvedIdentity:
    status = user.account_status
    expected_legacy_anonymous = status == "anonymous"
    if user.is_anonymous != expected_legacy_anonymous and status in {"anonymous", "registered"}:
        logger.warning("Identity compatibility flag drift for internal user_id=%s", user.user_id)
    blocked_code = BLOCKED_ACCOUNT_CODES.get(status)
    if blocked_code:
        logger.info("Identity rejected by account status=%s user_id=%s", status, user.user_id)
        raise _auth_error(403, blocked_code, "This Matchgoer account is not active")
    if status not in ACTIVE_ACCOUNT_STATUSES:
        logger.warning("Identity rejected with unknown account status user_id=%s", user.user_id)
        raise _auth_error(403, "ACCOUNT_INACTIVE", "This Matchgoer account is not active")
    if auth_mode == "bearer" and status != "registered":
        logger.info("Mapped bearer identity is not registered user_id=%s", user.user_id)
        raise _auth_error(403, "IDENTITY_NOT_REGISTERED", "This identity is not linked to a registered account")
    return ResolvedIdentity(
        user_id=user.user_id,
        account_status=status,
        is_registered=status == "registered",
        auth_mode=auth_mode,
        issuer=issuer,
        subject=subject,
    )


def resolve_identity(
    db: Session,
    *,
    authorization: str | None,
    session_id: str | None,
    required: bool,
    config: SupabaseAuthConfig | None = None,
    jwks_client: PyJWKClient | None = None,
) -> ResolvedIdentity | None:
    token = _bearer_token(authorization)
    if token is not None:
        issuer, subject = _verified_provider_identity(
            token,
            config or SupabaseAuthConfig.from_environment(),
            jwks_client,
        )
        mapping = db.query(UserIdentity).filter(
            UserIdentity.issuer == issuer,
            UserIdentity.subject == subject,
        ).first()
        if mapping is None:
            logger.info("Valid bearer identity is not linked")
            raise _auth_error(403, "IDENTITY_NOT_LINKED", "This identity is not linked to a Matchgoer account")
        user = db.query(User).filter(User.user_id == mapping.user_id).first()
        if user is None:
            logger.error("Identity mapping references a missing internal user")
            raise _auth_error(403, "IDENTITY_NOT_LINKED", "This identity is not linked to a Matchgoer account")
        identity = _resolved_user(user, "bearer", issuer, subject)
        logger.info("Identity resolved mode=bearer user_id=%s", identity.user_id)
        return identity

    if session_id:
        session = db.query(AnonymousSession).filter(AnonymousSession.session_id == session_id).first()
        if session is not None and session.revoked_at is None:
            user = db.query(User).filter(User.user_id == session.user_id).first()
            if user is not None:
                identity = _resolved_user(user, "anonymous")
                logger.info("Identity resolved mode=anonymous user_id=%s", identity.user_id)
                return identity

    if required:
        raise _auth_error(401, "NO_ACTIVE_IDENTITY", "No active Matchgoer identity")
    return None


def create_anonymous_identity(db: Session, response: Response) -> ResolvedIdentity:
    import secrets

    user = User(is_anonymous=True, account_status="anonymous")
    db.add(user)
    db.flush()
    session_id = secrets.token_urlsafe(32)
    db.add(AnonymousSession(session_id=session_id, user_id=user.user_id))
    db.commit()
    response.set_cookie(
        key="terrace_session",
        value=session_id,
        max_age=int(os.getenv("TERRACE_ANONYMOUS_SESSION_MAX_AGE_SECONDS", str(60 * 60 * 24 * 365))),
        **anonymous_cookie_options(),
    )
    logger.info("Identity created mode=anonymous user_id=%s", user.user_id)
    return _resolved_user(user, "anonymous")


def _dependency_identity(
    *,
    authorization: str | None,
    session_id: str | None,
    required: bool,
) -> ResolvedIdentity | None:
    db = SessionLocal()
    try:
        return resolve_identity(
            db,
            authorization=authorization,
            session_id=session_id,
            required=required,
        )
    finally:
        db.close()


def optional_current_identity(
    authorization: str | None = Header(default=None),
    session_id: str | None = Cookie(default=None, alias="terrace_session"),
) -> ResolvedIdentity | None:
    return _dependency_identity(authorization=authorization, session_id=session_id, required=False)


def required_current_identity(
    authorization: str | None = Header(default=None),
    session_id: str | None = Cookie(default=None, alias="terrace_session"),
) -> ResolvedIdentity:
    identity = _dependency_identity(authorization=authorization, session_id=session_id, required=True)
    assert identity is not None
    return identity


def current_or_new_anonymous_identity(
    response: Response,
    authorization: str | None = Header(default=None),
    session_id: str | None = Cookie(default=None, alias="terrace_session"),
) -> ResolvedIdentity:
    db = SessionLocal()
    try:
        identity = resolve_identity(
            db,
            authorization=authorization,
            session_id=session_id,
            required=False,
        )
        return identity if identity is not None else create_anonymous_identity(db, response)
    finally:
        db.close()
