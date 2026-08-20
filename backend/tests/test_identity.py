import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException, Response
from sqlalchemy.orm import Session

import identity as identity_module
from database import engine
from identity import (
    ResolvedIdentity,
    SupabaseAuthConfig,
    create_anonymous_identity,
    resolve_identity,
    verify_claim_provider_identity,
)
from models import AnonymousSession, User, UserIdentity


ISSUER = "https://phase4b.test/auth/v1"
AUDIENCE = "authenticated"


class StaticSigningKey:
    def __init__(self, key):
        self.key = key


class StaticJwksClient:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, _token):
        return StaticSigningKey(self.key)


class IdentityResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.config = SupabaseAuthConfig(True, ISSUER, AUDIENCE, "https://unused.test/jwks", 1, 60)

    def setUp(self):
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self.db = Session(bind=self.connection)
        self.anonymous = User(is_anonymous=True, account_status="anonymous")
        self.registered = User(is_anonymous=False, account_status="registered")
        self.db.add_all([self.anonymous, self.registered])
        self.db.flush()
        self.cookie = AnonymousSession(session_id=f"phase4b-cookie-{time.time_ns()}", user_id=self.anonymous.user_id)
        self.mapping = UserIdentity(user_id=self.registered.user_id, issuer=ISSUER, subject="registered-subject")
        self.db.add_all([self.cookie, self.mapping])
        self.db.flush()

    def tearDown(self):
        self.db.close()
        self.transaction.rollback()
        self.connection.close()

    def token(self, subject="registered-subject", **overrides):
        now = int(time.time())
        claims = {"iss": ISSUER, "sub": subject, "aud": AUDIENCE, "iat": now, "exp": now + 300}
        claims.update(overrides)
        return jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": "key-1"})

    def resolve_bearer(self, token, cookie=None, config=None, key=None):
        return resolve_identity(
            self.db,
            authorization=f"Bearer {token}",
            session_id=cookie,
            required=True,
            config=config or self.config,
            jwks_client=StaticJwksClient(key or self.private_key.public_key()),
        )

    def assert_error(self, expected_status, expected_code, callback):
        with self.assertRaises(HTTPException) as raised:
            callback()
        self.assertEqual(raised.exception.status_code, expected_status)
        self.assertEqual(raised.exception.detail["code"], expected_code)

    def test_valid_anonymous_cookie_resolves(self):
        resolved = resolve_identity(
            self.db, authorization=None, session_id=self.cookie.session_id, required=True
        )
        self.assertEqual(resolved, ResolvedIdentity(self.anonymous.user_id, "anonymous", False, "anonymous"))

    def test_bearer_wins_over_another_users_cookie_without_merge(self):
        resolved = self.resolve_bearer(self.token(), self.cookie.session_id)
        self.assertEqual(resolved.user_id, self.registered.user_id)
        self.assertEqual(resolved.auth_mode, "bearer")
        self.assertEqual(self.mapping.user_id, self.registered.user_id)

    def test_valid_unmapped_identity_is_forbidden(self):
        self.assert_error(403, "IDENTITY_NOT_LINKED", lambda: self.resolve_bearer(self.token("unmapped")))

    def test_expired_bad_signature_wrong_issuer_and_wrong_audience(self):
        now = int(time.time())
        self.assert_error(
            401,
            "TOKEN_EXPIRED",
            lambda: self.resolve_bearer(self.token(exp=now - 1), self.cookie.session_id),
        )
        bad_signature = jwt.encode(
            {"iss": ISSUER, "sub": "registered-subject", "aud": AUDIENCE, "exp": now + 60},
            self.other_private_key,
            algorithm="RS256",
            headers={"kid": "key-1"},
        )
        self.assert_error(401, "INVALID_SIGNATURE", lambda: self.resolve_bearer(bad_signature))
        self.assert_error(401, "INVALID_ISSUER", lambda: self.resolve_bearer(self.token(iss="https://wrong.test")))
        self.assert_error(401, "INVALID_AUDIENCE", lambda: self.resolve_bearer(self.token(aud="wrong")))

    def test_small_provider_clock_skew_is_allowed_but_larger_future_iat_is_rejected(self):
        now = int(time.time())
        resolved = self.resolve_bearer(self.token(iat=now + 30, exp=now + 300))
        self.assertEqual(resolved.user_id, self.registered.user_id)
        self.assert_error(
            401,
            "TOKEN_NOT_ACTIVE",
            lambda: self.resolve_bearer(self.token(iat=now + 61, exp=now + 300)),
        )

    def test_malformed_authorization_never_falls_back(self):
        self.assert_error(
            401,
            "INVALID_AUTHORIZATION",
            lambda: resolve_identity(
                self.db,
                authorization="Basic no",
                session_id=self.cookie.session_id,
                required=True,
            ),
        )

    def test_disabled_bearer_never_falls_back(self):
        disabled = SupabaseAuthConfig(False, None, None, None, 1, 60)
        self.assert_error(
            503,
            "BEARER_AUTH_DISABLED",
            lambda: self.resolve_bearer(self.token(), self.cookie.session_id, config=disabled),
        )

    def test_suspended_merged_and_deleted_users_are_rejected(self):
        for status, code in (
            ("suspended", "ACCOUNT_SUSPENDED"),
            ("merged", "ACCOUNT_MERGED"),
            ("deleted", "ACCOUNT_DELETED"),
        ):
            self.registered.account_status = status
            self.db.flush()
            self.assert_error(403, code, lambda: self.resolve_bearer(self.token()))

    def test_bearer_mapping_to_anonymous_user_is_rejected(self):
        self.mapping.user_id = self.anonymous.user_id
        self.db.flush()
        self.assert_error(403, "IDENTITY_NOT_REGISTERED", lambda: self.resolve_bearer(self.token()))


class AnonymousCreationTests(unittest.TestCase):
    def test_no_cookie_can_create_current_anonymous_identity(self):
        before = None
        created_user_id = None
        db = Session(bind=engine)
        try:
            before = db.query(User).count()
            response = Response()
            resolved = create_anonymous_identity(db, response)
            created_user_id = resolved.user_id
            self.assertEqual(resolved.auth_mode, "anonymous")
            self.assertIn("terrace_session=", response.headers["set-cookie"])
        finally:
            if created_user_id is not None:
                cleanup = Session(bind=engine)
                try:
                    cleanup.query(AnonymousSession).filter(AnonymousSession.user_id == created_user_id).delete()
                    cleanup.query(User).filter(User.user_id == created_user_id).delete()
                    cleanup.commit()
                finally:
                    cleanup.close()
            db.close()
        verify = Session(bind=engine)
        try:
            self.assertEqual(verify.query(User).count(), before)
        finally:
            verify.close()


class ClaimProviderVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.config = SupabaseAuthConfig(
            True,
            ISSUER,
            AUDIENCE,
            "https://unused.test/jwks",
            1,
            60,
            "publishable-test-key",
            1,
        )

    def token(self, **overrides):
        now = int(time.time())
        claims = {
            "iss": ISSUER,
            "sub": "claim-subject",
            "aud": AUDIENCE,
            "iat": now,
            "exp": now + 300,
        }
        claims.update(overrides)
        return jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": "claim-key"})

    def verify(self, provider_user, token=None):
        return verify_claim_provider_identity(
            f"Bearer {token or self.token()}",
            config=self.config,
            jwks_client=StaticJwksClient(self.private_key.public_key()),
            provider_user_loader=lambda *_args: provider_user,
        )

    def assert_error(self, status, code, callback):
        with self.assertRaises(HTTPException) as raised:
            callback()
        self.assertEqual(raised.exception.status_code, status)
        self.assertEqual(raised.exception.detail["code"], code)

    def test_confirmed_non_anonymous_provider_identity_is_accepted(self):
        verified = self.verify(
            {
                "id": "claim-subject",
                "email": "supporter@example.test",
                "is_anonymous": False,
                "email_confirmed_at": "2026-08-18T10:00:00Z",
                "app_metadata": {"provider": "email"},
            }
        )
        self.assertEqual(verified.subject, "claim-subject")
        self.assertEqual(verified.provider, "email")
        self.assertIsNotNone(verified.email_verified_at)

    def test_unconfirmed_anonymous_mismatched_and_malformed_provider_users_are_rejected(self):
        base = {"id": "claim-subject", "is_anonymous": False}
        cases = (
            base,
            {**base, "is_anonymous": True, "email_confirmed_at": "2026-08-18T10:00:00Z"},
            {**base, "id": "another-subject", "email_confirmed_at": "2026-08-18T10:00:00Z"},
            {**base, "email_confirmed_at": "not-a-date"},
        )
        for provider_user in cases:
            with self.subTest(provider_user=provider_user):
                self.assert_error(403, "IDENTITY_NOT_VERIFIED", lambda: self.verify(provider_user))

    def test_expired_bearer_is_rejected_before_provider_lookup(self):
        calls = []
        expired = self.token(exp=int(time.time()) - 1)
        with self.assertRaises(HTTPException) as raised:
            verify_claim_provider_identity(
                f"Bearer {expired}",
                config=self.config,
                jwks_client=StaticJwksClient(self.private_key.public_key()),
                provider_user_loader=lambda *_args: calls.append(True),
            )
        self.assertEqual(raised.exception.detail["code"], "TOKEN_EXPIRED")
        self.assertEqual(calls, [])


class JwksCacheTests(unittest.TestCase):
    def test_jwks_is_cached_and_unknown_kid_refreshes_for_rotation(self):
        first_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        second_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        def public_jwk(key, kid):
            value = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
            value.update({"kid": kid, "alg": "RS256", "use": "sig"})
            return value

        state = {"keys": [public_jwk(first_key, "first")], "requests": 0}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                state["requests"] += 1
                body = json.dumps({"keys": state["keys"]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/jwks"
            config = SupabaseAuthConfig(True, ISSUER, AUDIENCE, url, 1, 60)
            identity_module._jwks_clients.clear()
            now = int(time.time())
            base = {"iss": ISSUER, "sub": "subject", "aud": AUDIENCE, "exp": now + 60}
            first = jwt.encode(base, first_key, algorithm="RS256", headers={"kid": "first"})
            identity_module._verified_provider_identity(first, config)
            identity_module._verified_provider_identity(first, config)
            self.assertEqual(state["requests"], 1)

            state["keys"] = [public_jwk(first_key, "first"), public_jwk(second_key, "second")]
            second = jwt.encode(base, second_key, algorithm="RS256", headers={"kid": "second"})
            identity_module._verified_provider_identity(second, config)
            self.assertGreaterEqual(state["requests"], 2)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
