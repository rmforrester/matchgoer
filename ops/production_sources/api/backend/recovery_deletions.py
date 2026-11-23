"""Durable deletion suppression; feature flag enables only after reviewed rollout.

Unpublication/request recording continues on journal outage. Physical photo
purging defers through the existing retry path until suppression is durable.
No Supabase Auth mutation is introduced here.
"""
from datetime import datetime, timezone
import os


def enabled():
    return os.environ.get('RECOVERY_DELETION_CAPTURE_ENABLED', '').lower() == 'true'


def protection_required():
    return os.environ.get('RECOVERY_DELETION_PROTECTION_REQUIRED', '').lower() == 'true'


def guard_disabled_capture():
    if protection_required() and not enabled():
        from terraces_storage import StorageUnavailable
        warn()
        raise StorageUnavailable('Photograph cleanup is pending')


def stamp(value):
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def write(event):
    from ops.postgres_backup.deletion_suppression import append
    return append(event)


def warn():
    try:
        from ops.postgres_backup import backup
        backup.notify('DELETION_SUPPRESSION_NOT_DURABLE', backup.now())
    except Exception:
        pass


def before_photo_purge(db, photo):
    guard_disabled_capture()
    if not enabled():
        return
    from models import TerracePhotoEvent as Event
    from terraces_storage import StorageUnavailable
    event = db.query(Event).filter(Event.photo_id == photo.photo_id,
        Event.event_type.in_(['REMOVAL_REQUESTED', 'MODERATOR_REJECTED', 'REMOVED', 'REJECTED'])).order_by(Event.event_id).first()
    if event is None:
        warn()
        raise StorageUnavailable('Photograph cleanup is pending')
    try:
        result = write({'kind': 'photo', 'event_id': 'photo-event-' + str(event.event_id),
                        'occurred_at_utc': stamp(photo.removed_at or photo.rejected_at or event.created_at),
                        'user_id': photo.owner_user_id, 'photo_id': photo.photo_id,
                        'object_keys': [photo.display_key, photo.thumbnail_key]})
        if not result.get('durable'):
            raise ValueError()
        event.payload = {**(event.payload or {}), 'recovery_journal': {k: result[k] for k in ('key', 'sha256')}}
    except Exception:
        warn()
        raise StorageUnavailable('Photograph cleanup is pending') from None


def before_cascade_photo_purge(event):
    guard_disabled_capture()
    if not enabled():
        return
    from terraces_storage import StorageUnavailable
    payload = event.payload or {}
    try:
        result = write({'kind': 'photo', 'event_id': 'cascade-event-' + str(event.event_id),
                        'occurred_at_utc': stamp(event.created_at),
                        'object_keys': [payload['display_key'], payload['thumbnail_key']]})
        if not result.get('durable'):
            raise ValueError()
        event.payload = {**payload, 'recovery_journal': {k: result[k] for k in ('key', 'sha256')}}
    except Exception:
        warn()
        raise StorageUnavailable('Photograph cleanup is pending') from None


def capture_account_request(db, row):
    """Journal registered requests before operators may process account erasure.

Existing guest-history scopes/merge safeguards are left unchanged. An operator
must not perform an Auth/account deletion without a durable account receipt.
"""
    if row.request_type != 'account':
        return
    if not enabled():
        if protection_required():
            row.record_scope = {**(row.record_scope or {}),
                                'recovery_journal': {'durable':False, 'retry_pending':True}}
            warn()
        return
    from models import UserIdentity
    existing = row.record_scope or {}
    if existing.get('recovery_journal', {}).get('durable') is True:
        return
    identities = [{'issuer': i.issuer, 'subject': i.subject} for i in
                  db.query(UserIdentity).filter(UserIdentity.user_id == row.user_id).order_by(UserIdentity.user_identity_id)]
    try:
        result = write({'kind': 'account', 'event_id': 'account-request-' + row.request_id,
                        'phase': 'requested',
                        'occurred_at_utc': stamp(row.requested_at), 'user_id': row.user_id,
                        'identities': identities})
        if not result.get('durable'):
            raise ValueError()
        row.record_scope = {**existing, 'recovery_journal': {**{k: result[k] for k in ('key', 'sha256')}, 'durable': True}}
    except Exception:
        row.record_scope = {**existing, 'recovery_journal': {'durable': False, 'retry_pending': True}}
        warn()
