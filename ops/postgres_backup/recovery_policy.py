"""Founder-approved recovery eligibility. Object presence never grants eligibility."""
from datetime import datetime, timedelta, timezone

MAX_POINT_DAYS = 100
JOURNAL_DAYS = 120
SAFETY_DAYS = 20


class PolicyError(ValueError):
    pass


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            raise ValueError()
        return result
    except (ValueError, TypeError, AttributeError):
        raise PolicyError('RECOVERY_TIMESTAMP_INVALID') from None


def eligible(snapshot, coverage, observed=None):
    """Run before decryption/restore, with independently verified journal coverage.

    Coverage is produced by the recovery operator after validating capture
    deployment, uninterrupted journal receipts and all encrypted suppression
    records. A backup receipt alone cannot certify its own coverage.
    """
    observed = observed or datetime.now(timezone.utc)
    snapshot = timestamp(snapshot)
    if snapshot > observed + timedelta(minutes=5):
        raise PolicyError('RECOVERY_POINT_IN_FUTURE')
    if observed - snapshot > timedelta(days=MAX_POINT_DAYS):
        raise PolicyError('RECOVERY_POINT_EXPIRED')
    if not isinstance(coverage, dict) or coverage.get('verified') is not True:
        raise PolicyError('DELETION_COVERAGE_NOT_VERIFIED')
    required = ('capture_continuous', 'journal_complete', 'suppression_applied',
                'all_restore_sources_catalogued', 'legacy_copies_excluded')
    if not all(coverage.get(k) is True for k in required):
        raise PolicyError('DELETION_COVERAGE_INCOMPLETE')
    if timestamp(coverage.get('from_utc')) > snapshot:
        raise PolicyError('DELETION_COVERAGE_STARTS_AFTER_SNAPSHOT')
    through = timestamp(coverage.get('through_utc'))
    if through < observed or through > observed + timedelta(minutes=5):
        raise PolicyError('DELETION_COVERAGE_NOT_CURRENT')
    return True


def expired(snapshot, observed):
    return observed - timestamp(snapshot) > timedelta(days=MAX_POINT_DAYS)
