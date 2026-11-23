"""Revoke an Apple grant only after a durable, owner-confirmed deletion request.

Never stores a provider code, token or private key. All remote calls are mocked
in local tests. Missing configuration leaves the request pending for follow-up.
"""
import json
import os
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import jwt
from identity import _bearer_token, _load_provider_user, SupabaseAuthConfig

APPLE = "https://appleid.apple.com"
_keys = jwt.PyJWKClient(APPLE + "/auth/keys", timeout=3)


def post_form(path, values):
    request = Request(APPLE + path, data=urlencode(values).encode(),
                      headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urlopen(request, timeout=3) as response:
        raw = response.read(65536)
        return json.loads(raw) if raw else {}


def revoke_apple(identity, authorization, code):
    if not identity.is_registered:
        return "not_required"
    try:
        token = _bearer_token(authorization)
        if not token or not identity.subject:
            return "pending"
        user = _load_provider_user(token, SupabaseAuthConfig.from_environment())
        if user.get("id") != identity.subject:
            return "pending"
        identities = user.get("identities")
        if not isinstance(identities, list):
            return "pending"
        apple = [item for item in identities if item.get("provider") == "apple"]
        if not apple:
            return "not_required"
        if len(apple) != 1 or not code:
            return "pending"
        subject = apple[0].get("identity_data", {}).get("sub")
        team, key_id, private_key = [os.getenv(name) for name in (
            "APPLE_SIGNIN_TEAM_ID", "APPLE_SIGNIN_KEY_ID", "APPLE_SIGNIN_PRIVATE_KEY")]
        if not all((subject, team, key_id, private_key)):
            return "pending"
        # App ID, never a user-controlled audience or a web Services ID.
        client = "com.matchgoer.app"
        now = int(time.time())
        secret = jwt.encode({"iss": team, "iat": now, "exp": now + 300,
                             "aud": APPLE, "sub": client}, private_key,
                            algorithm="ES256", headers={"kid": key_id})
        result = post_form("/auth/token", {"client_id": client, "client_secret": secret,
                                          "grant_type": "authorization_code", "code": code})
        id_token = result.get("id_token")
        if not id_token:
            return "pending"
        verified = jwt.decode(id_token, _keys.get_signing_key_from_jwt(id_token).key,
                              algorithms=["RS256"], audience=client, issuer=APPLE,
                              options={"require": ["exp", "iat", "sub"]})
        if verified["sub"] != subject or not result.get("refresh_token"):
            return "pending"
        revoked = post_form("/auth/revoke", {"client_id": client, "client_secret": secret,
                                 "token": result["refresh_token"], "token_type_hint": "refresh_token"})
        return "pending" if revoked.get("error") else "complete"
    except Exception:
        # Provider errors can contain sensitive response data. Never log them or
        # mark revocation complete merely because the request was recorded.
        return "pending"
