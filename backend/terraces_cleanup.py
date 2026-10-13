"""Operator-only existing maintenance integration; no scheduler or HTTP job."""
import argparse
import sys
def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--confirm-private-cleanup',action='store_true')
    parser.add_argument('--limit',type=int,default=50,help='Maximum candidates per cleanup category (1–500)')
    args=parser.parse_args(argv)
    if not (args.execute and args.confirm_private_cleanup):
        parser.error('Both explicit cleanup confirmations are required')
    if not 1<=args.limit<=500:parser.error('Cleanup limit must be between 1 and 500')
    from database import SessionLocal
    from sqlalchemy.exc import DBAPIError
    from terraces_storage import LazyPrivatePhotoStorage,StorageUnavailable
    from terraces_service import cleanup
    try:
        with SessionLocal() as db:
            result=cleanup(db,LazyPrivatePhotoStorage(),limit=args.limit)
    except (StorageUnavailable,DBAPIError):
        print('Photo cleanup failed; review configuration and retry safely.',file=sys.stderr)
        return 1
    print('Cleaned:',result['cleaned'],'Retry pending:',result['retry_pending'])
    return 1 if result['retry_pending'] else 0
if __name__=='__main__':raise SystemExit(main())
