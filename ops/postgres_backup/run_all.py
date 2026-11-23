"""Independent bounded source outcomes; never skip PostgreSQL for Supabase failure."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    outcomes = {}
    for source, file in [('railway_postgresql', 'backup.py'), ('supabase', 'supabase_recovery.py')]:
        try:
            args = [sys.executable, str(ROOT / file)]
            probe = source == 'supabase' and os.environ.get('SUPABASE_RECOVERY_MODE') == 'probe'
            if probe:
                args.append('--probe')
            r = subprocess.run(args, timeout=2800)
            outcomes[source] = {'process_succeeded': r.returncode == 0, 'probe_only': probe}
        except subprocess.TimeoutExpired:
            outcomes[source] = {'process_succeeded': False, 'reason': 'SOURCE_PROCESS_TIMEOUT'}
    print(json.dumps({'event': 'INDEPENDENT_RECOVERY_SOURCE_OUTCOMES', 'sources': outcomes}), flush=True)
    return 0 if all(r['process_succeeded'] for r in outcomes.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
