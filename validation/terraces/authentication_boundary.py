"""Synthetic JWT validation only; no database connection or provider request."""
from pathlib import Path
import os, sys, json
from datetime import datetime, timezone
from unittest.mock import patch
SOURCE = Path('/source')
os.environ['DATABASE_URL'] = 'postgresql://unused@127.0.0.1:1/unused'
os.environ.pop('MATCHGOER_HOSTED_DATABASE_URL', None)
sys.path[:0] = [str(SOURCE), str(SOURCE / 'backend')]
import identity
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
class Keys:
    def get_signing_key_from_jwt(self, token):
        return type('Key', (), {'key': key.public_key()})()
config = identity.SupabaseAuthConfig(True, 'https://synthetic.test/auth/v1', 'authenticated', 'https://unused.test', 1, 60)
base = int(datetime.now(timezone.utc).timestamp())
results = []
for offset, elapsed, expected in [(30, .2, 'ACCEPT'), (61, .2, 'TOKEN_NOT_ACTIVE'), (61, 1.2, 'ACCEPT'), (62, 1.2, 'TOKEN_NOT_ACTIVE')]:
    token = jwt.encode({'iss': config.issuer, 'sub': 'synthetic', 'aud': 'authenticated', 'iat': base + offset, 'exp': base + 300}, key, algorithm='RS256')
    class Clock:
        @staticmethod
        def now(tz):
            return datetime.fromtimestamp(base + elapsed, timezone.utc)
    with patch.object(identity, 'datetime', Clock):
        try:
            identity._verified_provider_claims(token, config=config, jwks_client=Keys())
            actual = 'ACCEPT'
        except HTTPException as exc:
            actual = exc.detail['code']
    assert actual == expected, (actual, expected)
    results.append({'iat_offset_seconds': offset, 'verification_elapsed_seconds': elapsed, 'expected': expected, 'actual': actual})
(Path('/output/authentication-boundary-results.json')).write_text(json.dumps({'status':'PASS', 'cases':results, 'database_connections':0, 'provider_requests':0}, indent=2)+'\n')
print('Four deterministic real-signature clock-boundary checks PASS; no database/provider access.')
