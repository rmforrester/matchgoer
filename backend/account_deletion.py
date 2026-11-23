"""Owner-initiated requests only. This module never deletes account data."""
from datetime import datetime, timedelta, timezone
import uuid
import hashlib
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, StrictBool, Field
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, JSON, text
from sqlalchemy.exc import IntegrityError

from database import SessionLocal
from identity import ResolvedIdentity, required_privacy_identity
from models import Base, User, VenueVisit, InterestedFixture, AwayDayReview, SocialEvent
from terraces import require_moderator


class AccountDeletionRequest(Base):
    __tablename__ = "account_deletion_requests"
    request_id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    request_type = Column(String(16), nullable=False)
    record_scope = Column(JSON, nullable=False, default=dict)
    transfer_lineage = Column(JSON, nullable=False, default=list)
    status = Column(String(16), nullable=False, default="pending")
    requested_at = Column(DateTime(timezone=True), nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    apple_revocation = Column(String(16), nullable=False, default="pending")
    apple_revoked_at = Column(DateTime(timezone=True), nullable=True)
    receipt_hash = Column(String(64), unique=True, nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("request_type IN ('account','guest_history')", name="ck_deletion_type"),
        CheckConstraint("status IN ('pending','processing','completed')", name="ck_deletion_status"),
        CheckConstraint("apple_revocation IN ('pending','not_required','complete')", name="ck_deletion_apple"),
        CheckConstraint("status <> 'completed' OR apple_revocation IN ('not_required','complete')", name="ck_deletion_before_completion"),
        Index("uq_account_deletion_open", "user_id", "request_type", unique=True,
        postgresql_where=text("status IN ('pending','processing')")),)


class Confirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    guest_history: StrictBool = False
    confirmed: StrictBool
    apple_authorization_code: str | None = Field(default=None, min_length=1, max_length=4096)


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


def receipt_available(row, now=None):
    if row.completed_at is None:
        return True  # Pending accountability is never hidden by expiry.
    completed = row.completed_at
    if completed.tzinfo is None: completed = completed.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) < completed + timedelta(days=90)


def issue_receipt(row):
    receipt = secrets.token_urlsafe(32)
    row.receipt_hash = hashlib.sha256(receipt.encode()).hexdigest()
    return receipt


def payload(row):
    return {"request_id": row.request_id, "status": row.status,
            "requested_at": row.requested_at, "due_at": row.due_at,
            "completed_at": row.completed_at, "apple_revocation": row.apple_revocation, "apple_revoked_at": row.apple_revoked_at, "confirmed_at": row.confirmed_at, "request_type": row.request_type,
            "manual_review_required": bool(row.transfer_lineage)}


def latest(db, user_id, request_type=None):
    query = db.query(AccountDeletionRequest).filter_by(user_id=user_id)
    if request_type: query = query.filter_by(request_type=request_type)
    return query.order_by(AccountDeletionRequest.requested_at.desc()).first()


def request_deletion(db, identity, confirmed, now=None):
    if confirmed is not True:
        raise HTTPException(422, "Confirm the account deletion request before sending it")
    # Serialise repeated submissions for this owner; caller cannot supply an owner ID.
    user = db.query(User).filter_by(user_id=identity.user_id).with_for_update().one_or_none()
    if user is None or user.account_status not in {"registered", "anonymous", "suspended"}:
        raise HTTPException(403, "This account cannot request deletion")
    request_type = "account" if identity.is_registered else "guest_history"
    row = latest(db, identity.user_id, request_type)
    if row and row.status in {"pending", "processing"}:
        return row
    now = now or datetime.now(timezone.utc)
    row = AccountDeletionRequest(request_id=str(uuid.uuid4()), user_id=identity.user_id,
        request_type=request_type, record_scope=capture_guest_scope(db, identity.user_id) if request_type == "guest_history" else {},
        transfer_lineage=[], status="pending", apple_revocation="pending", requested_at=now, due_at=now + timedelta(days=7))
    db.add(row)
    db.flush()
    return row


SCOPE_MODELS = {"visits": (VenueVisit, VenueVisit.visit_id),
                "interested": (InterestedFixture, InterestedFixture.interested_id),
                "reviews": (AwayDayReview, AwayDayReview.review_id),
                "activity": (SocialEvent, SocialEvent.event_id)}


def capture_guest_scope(db, user_id):
    # Identifiers only; no emails, session secrets or copies of personal content.
    return {key: [row[0] for row in db.query(pk).filter(model.user_id == user_id).order_by(pk).with_for_update().all()]
            for key, (model, pk) in SCOPE_MODELS.items()}


def record_guest_transfer(db, source_user_id, target_user_id, kind):
    # Caller holds the source owner lock in the existing claim transaction.
    rows = db.query(AccountDeletionRequest).filter_by(user_id=source_user_id, request_type="guest_history").filter(
        AccountDeletionRequest.status.in_(["pending", "processing"])).with_for_update().all()
    for row in rows:
        entry = {"target_user_id": target_user_id, "kind": kind}
        if entry not in row.transfer_lineage:
            row.transfer_lineage = [*row.transfer_lineage, entry]
    # Keep original owner, request scope and deadline. Never reassign to target.


def guarded_guest_scope(db, row):
    """Read-only operator preflight; never expands or executes deletion."""
    user = db.get(User, row.user_id) if row.user_id else None
    if row.request_type != "guest_history" or row.transfer_lineage or not user or user.account_status != "anonymous":
        raise HTTPException(409, "Protected manual scope review required; do not delete account history")
    if set(row.record_scope) != set(SCOPE_MODELS):
        raise HTTPException(409, "Deletion scope is incomplete; protected manual review required")
    for key, (model, pk) in SCOPE_MODELS.items():
        ids = row.record_scope[key]
        if not isinstance(ids, list) or any(type(value) is not int or value <= 0 for value in ids) or len(set(ids)) != len(ids):
            raise HTTPException(409, "Invalid scope; protected manual review required")
        actual = {item[0] for item in db.query(pk).filter(pk.in_(ids), model.user_id == row.user_id).all()}
        if actual != set(ids):
            raise HTTPException(409, "Changed ownership or missing records; protected manual review required")
    return {key: list(ids) for key, ids in row.record_scope.items()}


router = APIRouter(prefix="/account", tags=["Account privacy"])


@router.post("/deletion-receipt")
def receipt_status(data: Receipt, response: Response):
    # Capability permits only this anonymous status receipt, not account access.
    # It is sent in a body, never in a URL or an analytics event.
    response.headers["Cache-Control"] = "no-store"
    digest = hashlib.sha256(data.receipt.encode()).hexdigest()
    with SessionLocal() as db:
        row = db.query(AccountDeletionRequest).filter_by(receipt_hash=digest).first()
        if row is None or not receipt_available(row):
            raise HTTPException(404, "Deletion receipt not found")
        return {"request_id": row.request_id, "status": row.status,
                "due_at": row.due_at, "completed_at": row.completed_at}


@router.get("/deletion-request")
def get_request(response: Response, identity: ResolvedIdentity = Depends(required_privacy_identity)):
    response.headers["Cache-Control"] = "no-store"
    with SessionLocal() as db:
        row = latest(db, identity.user_id, "account" if identity.is_registered else "guest_history")
        return payload(row) if row else None


@router.post("/deletion-request")
def create_request(data: Confirmation, response: Response,
                   identity: ResolvedIdentity = Depends(required_privacy_identity),
                   authorization: str | None = Header(default=None)):
    response.headers["Cache-Control"] = "no-store"
    if data.guest_history != (not identity.is_registered):
        raise HTTPException(409, "Your identity changed. Reopen the deletion request for your current history.")
    with SessionLocal() as db:
        try:
            row = request_deletion(db, identity, data.confirmed)
            receipt = issue_receipt(row)
            db.commit()  # The request survives provider outages or cancellation.
            if data.apple_authorization_code or row.apple_revocation != "complete":
                from apple_deletion import revoke_apple
                row.apple_revocation = revoke_apple(identity, authorization, data.apple_authorization_code)
                row.apple_revoked_at = datetime.now(timezone.utc) if row.apple_revocation == "complete" else None
                db.commit()
            return {**payload(row), "receipt": receipt}
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "A request is already being recorded. Refresh its status.") from None


@router.get("/moderator/deletion-requests")
def pending_requests(response: Response, authorization: str | None = Header(default=None)):
    response.headers["Cache-Control"] = "no-store"
    with SessionLocal() as db:
        require_moderator(db, authorization)
        rows = db.query(AccountDeletionRequest).filter(
            AccountDeletionRequest.status.in_(["pending", "processing"])).order_by(
                AccountDeletionRequest.due_at, AccountDeletionRequest.request_id).all()
        return [{**payload(row), "user_id": row.user_id, "record_scope": row.record_scope, "transfer_lineage": row.transfer_lineage} for row in rows]
