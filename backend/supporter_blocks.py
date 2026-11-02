"""Personal content blocking; never changes moderation or upload permissions."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import Column, DateTime, ForeignKey, Integer, or_, CheckConstraint, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import insert
from database import SessionLocal
from identity import ResolvedIdentity, required_current_identity
from models import Base, MatchdayTip, TerracePhoto, UserProfile


class SupporterBlock(Base):
    __tablename__ = "supporter_blocks"
    block_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    blocked_user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "blocked_user_id", name="uq_supporter_block"),
                      CheckConstraint("user_id <> blocked_user_id", name="ck_supporter_block_self"))


def visible_authors(query, author_column, user_id):
    if user_id is None:
        return query
    return query.filter(or_(author_column.is_(None), ~author_column.in_(select(SupporterBlock.blocked_user_id).where(SupporterBlock.user_id == user_id))))


def has_block(db, user_id, target_id):
    return db.query(SupporterBlock.block_id).filter_by(user_id=user_id, blocked_user_id=target_id).first() is not None


def registered(identity):
    if not identity.is_registered:
        raise HTTPException(403, "Sign in to block a matchgoer")


def block_author(db, identity, kind, content_id):
    registered(identity)
    row = db.get({"photo": TerracePhoto, "tip": MatchdayTip}[kind], content_id)
    if row is None:
        raise HTTPException(404, "Content not found")
    if kind == "photo" and (row.status != "APPROVED" or row.published_at is None or row.dispute_reason is not None or row.storage_deleted_at is not None):
        raise HTTPException(404, "Content not found")
    if kind == "photo":
        from terraces_service import ready
        if not ready(db, row):
            raise HTTPException(404, "Content not found")
    if kind == "tip" and (row.status != "active" or row.author_user_id is None):
        raise HTTPException(404, "Content not found")
    target = row.owner_user_id if kind == "photo" else row.author_user_id
    if target == identity.user_id:
        raise HTTPException(400, "You cannot block yourself")
    db.execute(insert(SupporterBlock).values(user_id=identity.user_id, blocked_user_id=target,
        created_at=datetime.now(timezone.utc)).on_conflict_do_nothing(constraint="uq_supporter_block"))
    db.commit()
    return {"blocked": True}


router = APIRouter(tags=["Community safety"])


@router.post("/terraces/photos/{photo_id}/block-author")
def block_photo(photo_id: int, identity: ResolvedIdentity = Depends(required_current_identity)):
    with SessionLocal() as db:
        return block_author(db, identity, "photo", photo_id)


@router.post("/tips/{tip_id}/block-author")
def block_tip(tip_id: int, identity: ResolvedIdentity = Depends(required_current_identity)):
    with SessionLocal() as db:
        return block_author(db, identity, "tip", tip_id)


@router.get("/account/blocked-matchgoers")
def list_blocks(response: Response, identity: ResolvedIdentity = Depends(required_current_identity)):
    registered(identity)
    response.headers["Cache-Control"] = "no-store"
    with SessionLocal() as db:
        rows = db.query(SupporterBlock, UserProfile.display_name).outerjoin(UserProfile,
            UserProfile.user_id == SupporterBlock.blocked_user_id).filter(SupporterBlock.user_id == identity.user_id).all()
        return [{"block_id": row.block_id, "display_name": name or "Matchgoer"} for row, name in rows]


@router.delete("/account/blocked-matchgoers/{block_id}")
def unblock(block_id: int, identity: ResolvedIdentity = Depends(required_current_identity)):
    registered(identity)
    with SessionLocal() as db:
        row = db.query(SupporterBlock).filter_by(block_id=block_id, user_id=identity.user_id).first()
        if row is None:
            raise HTTPException(404, "Block not found")
        db.delete(row)
        db.commit()
        return {"blocked": False}
