"""Foundation only: caller owns the transaction; no storage calls or API routes."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import or_

from identity import verify_claim_provider_identity
from models import User, UserIdentity, VenueVisit, Fixture, TerracePhoto, TerracePhotoEvent
from terraces_images import SanitisedPhoto

CONSENT_VERSION = "terraces-public-v1"
ACTIVE_STATES = ("PENDING", "APPROVED")


@dataclass(frozen=True)
class PhotoActor:
    user_id: int


def require_verified_account(db, authorization: str | None) -> PhotoActor:
    provider = verify_claim_provider_identity(authorization)
    mapping = db.query(UserIdentity).filter(
        UserIdentity.issuer == provider.issuer, UserIdentity.subject == provider.subject,
    ).first()
    user = db.get(User, mapping.user_id) if mapping else None
    if not user or user.account_status != "registered" or user.is_anonymous or user.merged_into_user_id is not None:
        raise HTTPException(403, "An active verified registered account is required")
    return PhotoActor(user.user_id)


def require_moderator(db, authorization: str | None, *, moderator_user_id: int | None) -> PhotoActor:
    actor = require_verified_account(db, authorization)
    if type(moderator_user_id) is not int or moderator_user_id < 1 or actor.user_id != moderator_user_id:
        raise HTTPException(403, "Moderator permission is required")
    return actor


def reserve_photo(db, authorization: str | None, *, visit_id: int, photo: SanitisedPhoto,
                  submission_key: str, consent_version: str, public_consent: bool,
                  rights_acknowledged: bool, caption: str | None = None) -> TerracePhoto:
    """Reserve one private slot after sanitisation. Never commit or upload.

    Three live (pending/approved) submissions per owned attendance. Rejected and
    removed submissions remain auditable but do not consume public/pending slots.
    """
    actor = require_verified_account(db, authorization)
    if public_consent is not True or rights_acknowledged is not True or consent_version != CONSENT_VERSION:
        raise HTTPException(422, "Public sharing and image rights must be acknowledged")
    if caption is not None and (not isinstance(caption, str) or len(caption) > 200):
        raise HTTPException(422, "Captions must be no longer than 200 characters")
    try:
        submission_key = str(UUID(submission_key))
    except (ValueError, TypeError, AttributeError) as error:
        raise HTTPException(422, "A valid submission retry key is required") from error
    visit = db.query(VenueVisit).filter(VenueVisit.visit_id == visit_id, VenueVisit.user_id == actor.user_id).with_for_update().first()
    if not visit:
        raise HTTPException(404, "Owned recorded attendance was not found")
    if visit.fixture_id is not None:
        fixture = db.get(Fixture, visit.fixture_id)
        if not fixture or fixture.venue_id != visit.venue_id:
            raise HTTPException(409, "Attendance fixture/venue identity requires review")
    existing = db.query(TerracePhoto).filter(TerracePhoto.owner_user_id == actor.user_id, TerracePhoto.submission_key == submission_key).first()
    if existing:
        if (existing.visit_id, existing.source_sha256, existing.caption, existing.consent_version) != (visit_id, photo.source_sha256, caption, consent_version):
            raise HTTPException(409, "The retry key belongs to a different submission")
        return existing
    if db.query(TerracePhoto).filter(TerracePhoto.visit_id == visit_id, TerracePhoto.source_sha256 == photo.source_sha256).first():
        raise HTTPException(409, "This photograph was already submitted for this matchday")
    if db.query(TerracePhoto).filter(TerracePhoto.visit_id == visit_id, TerracePhoto.status.in_(ACTIVE_STATES)).count() >= 3:
        raise HTTPException(409, "A matchday can have no more than three photographs")
    key = uuid4().hex
    result = TerracePhoto(
        owner_user_id=actor.user_id, visit_id=visit.visit_id, venue_id=visit.venue_id,
        fixture_id=visit.fixture_id, caption=caption, submission_key=submission_key,
        source_sha256=photo.source_sha256, original_bytes=photo.source_bytes,
        display_key=f"photos/{key}/display.jpg", thumbnail_key=f"photos/{key}/thumbnail.jpg",
        width=photo.display.width, height=photo.display.height,
        thumbnail_width=photo.thumbnail.width, thumbnail_height=photo.thumbnail.height,
        content_type="image/jpeg", status="PENDING", consent_version=consent_version,
    )
    db.add(result)
    db.flush()
    return result


def storage_deletion_candidates(db, *, now: datetime | None = None):
    """SELECT only. No deletion executor or scheduler is introduced in Phase A."""
    now = now or datetime.now(timezone.utc)
    return db.query(TerracePhoto).filter(
        TerracePhoto.storage_deleted_at.is_(None),
        or_(TerracePhoto.status == "REMOVED", (TerracePhoto.status == "REJECTED") &
            (TerracePhoto.rejected_at <= now - timedelta(days=7)) & TerracePhoto.dispute_reason.is_(None)),
    ).all()


def storage_deletion_receipts(db):
    """Opaque keys survive account/row deletion until a future executor confirms purge."""
    return db.query(TerracePhotoEvent).filter(
        TerracePhotoEvent.event_type == "STORAGE_DELETE_REQUIRED",
        TerracePhotoEvent.completed_at.is_(None),
    ).all()


def may_read_photo(photo: TerracePhoto, actor: PhotoActor | None = None, *, moderator_user_id: int | None = None) -> bool:
    """Authorisation policy only; no URL creation, endpoint or publication enabled.

    An actor must come from require_verified_account, never from a client field.
    Anonymous public reads may only receive sanitised approved/published variants.
    """
    if photo.storage_deleted_at is not None or photo.status == "REMOVED":
        return False
    if photo.status == "APPROVED" and photo.approved_at is not None and photo.published_at is not None:
        return True
    if actor is None:
        return False
    return actor.user_id == photo.owner_user_id or (
        type(moderator_user_id) is int and moderator_user_id > 0 and actor.user_id == moderator_user_id
    )
