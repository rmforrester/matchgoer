"""Read-only continuity classification. Acknowledgement never repairs an identity."""
import hashlib
import json
from pathlib import Path

BASELINE_SHA256 = '3e15e0a04a83f752ae8b84ecdb74efae3519ae3c02a7232fe8ff13bceff19506'


def identity_key(issuer, subject):
    return hashlib.sha256((issuer + '\0' + subject).encode()).hexdigest()


def user_key(user_id):
    return hashlib.sha256(str(user_id).encode()).hexdigest()


def baseline():
    data = (Path(__file__).with_name('identity-continuity-baseline.json')).read_bytes()
    if hashlib.sha256(data).hexdigest() != BASELINE_SHA256:
        raise ValueError('IDENTITY_ACKNOWLEDGEMENT_INTEGRITY_FAILED')
    result = json.loads(data)
    pairs = {x['identity_key']: x['user_key'] for x in result['relationships']}
    acknowledged = result['acknowledged_orphans']
    if (result.get('version') != 1 or len(pairs) != 18 or len(acknowledged) != 4
            or len({x['identity_key'] for x in acknowledged}) != 4
            or any(pairs.get(x['identity_key']) != x['user_key']
                   or x['status'] != 'ACKNOWLEDGED_UNRESOLVED_ORPHAN' for x in acknowledged)):
        raise ValueError('IDENTITY_ACKNOWLEDGEMENT_INVALID')
    return result


def classify(identities, auth_subjects, approved):
    """Exact subjects in both directions; no email/name matching or ID disclosure."""
    auth_subjects = {str(s) for s in auth_subjects}
    expected = {x['identity_key']: x['user_key'] for x in approved['relationships']}
    known = {x['identity_key']: x['user_key'] for x in approved['acknowledged_orphans']}
    current = {}
    matched = set()
    missing = set()
    by_status = {}
    known_missing = set()
    subject_counts = {}
    invalid = 0
    for row in identities:
        subject = str(row.get('subject', ''))
        subject_counts[subject] = subject_counts.get(subject, 0) + 1
        if subject in auth_subjects:
            matched.add(subject)
        else:
            missing.add(subject)
            status = row.get('account_status')
            status = status if status in ('registered', 'anonymous', 'deleted') else 'other'
            by_status[status] = by_status.get(status, 0) + 1
        if not row.get('issuer') or not row.get('user_id') or not subject:
            invalid += 1
            continue
        key, target = identity_key(row['issuer'], subject), user_key(row['user_id'])
        current.setdefault(key, set()).add(target)
        if subject not in auth_subjects and known.get(key) == target:
            known_missing.add(subject)
    changed = sum(current.get(key) != {target} for key, target in expected.items())
    binding_failures = sum(subject_counts.get(s, 0) != 1 for s in auth_subjects)
    new_orphans = len(missing - known_missing)
    duplicate_relationships = sum(n != 1 for n in subject_counts.values())
    acknowledged_changes = len(known) - len(known_missing)
    passed = not (invalid or changed or binding_failures or new_orphans
                  or duplicate_relationships or acknowledged_changes)
    return dict(
        passed=passed,
        reason=('CURRENT_USERS_MATCH_ACKNOWLEDGED_ORPHANS_PRESERVED' if passed and known_missing
                else 'IDENTITIES_MATCH' if passed else 'SUPABASE_RAILWAY_SUBJECT_MISMATCH'),
        railway_unique_subjects=len({str(i.get('subject', '')) for i in identities}),
        matched_subjects=len(matched), missing_subjects=len(missing),
        missing_identity_rows_by_account_status=by_status,
        current_auth_users=len(auth_subjects), current_user_binding_failures=binding_failures,
        acknowledged_unresolved_orphans=len(known_missing), new_orphans=new_orphans,
        acknowledged_orphan_status_changes=acknowledged_changes,
        changed_identity_relationships=changed, malformed_relationships=invalid,
        duplicate_relationships=duplicate_relationships,
        acknowledgement_status='PRESERVED_UNRESOLVED_NOT_REPAIRED',
        baseline_sha256=BASELINE_SHA256)
