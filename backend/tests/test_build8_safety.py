import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from pydantic import ValidationError

import apple_deletion
import supporter_blocks as blocks
from identity import ResolvedIdentity
from models import MatchBoardPost, MatchdayTip, TerracePhoto


class BlockingTests(unittest.TestCase):
    def setUp(self):
        self.identity = ResolvedIdentity(11, "registered", True, "bearer")
        self.db = MagicMock()

    def test_guest_cannot_block(self):
        with self.assertRaises(HTTPException) as error:
            blocks.block_author(self.db, ResolvedIdentity(11, "anonymous", False, "cookie"), "tip", 1)
        self.assertEqual(error.exception.status_code, 403)
        self.db.get.assert_not_called()

    def test_cannot_block_self(self):
        self.db.get.return_value = MatchdayTip(author_user_id=11, status="active")
        with self.assertRaises(HTTPException):
            blocks.block_author(self.db, self.identity, "tip", 3)
        self.db.execute.assert_not_called()

    def test_target_is_derived_from_content_and_insert_is_idempotent(self):
        self.db.get.return_value = MatchdayTip(author_user_id=22, status="active")
        self.assertEqual(blocks.block_author(self.db, self.identity, "tip", 3), {"blocked": True})
        statement = self.db.execute.call_args.args[0].compile(dialect=postgresql.dialect())
        self.assertEqual(statement.params["user_id"], 11)
        self.assertEqual(statement.params["blocked_user_id"], 22)
        self.assertIn("ON CONFLICT ON CONSTRAINT uq_supporter_block DO NOTHING", str(statement))

    def test_private_or_removed_photo_cannot_be_used_to_identify_owner(self):
        self.db.get.return_value = TerracePhoto(owner_user_id=22, status="PENDING")
        with self.assertRaises(HTTPException) as error:
            blocks.block_author(self.db, self.identity, "photo", 3)
        self.assertEqual(error.exception.status_code, 404)
        self.db.execute.assert_not_called()

    def test_unpublished_tip_cannot_be_used_to_discover_an_author(self):
        self.db.get.return_value = MatchdayTip(author_user_id=22, status="pending")
        with self.assertRaises(HTTPException) as error:
            blocks.block_author(self.db, self.identity, "tip", 3)
        self.assertEqual(error.exception.status_code, 404)
        self.db.execute.assert_not_called()

    def test_guest_visibility_is_unchanged(self):
        query = MagicMock()
        self.assertIs(blocks.visible_authors(query, MatchBoardPost.author_user_id, None), query)
        query.filter.assert_not_called()

    def test_personal_visibility_is_owner_scoped_in_sql(self):
        query = blocks.visible_authors(select(MatchBoardPost), MatchBoardPost.author_user_id, 11)
        statement = query.compile(dialect=postgresql.dialect())
        self.assertIn("supporter_blocks.user_id", str(statement))
        self.assertIn(11, statement.params.values())
        self.assertNotIn("DELETE", str(statement))

    def test_deferred_board_endpoints_are_not_registered(self):
        paths = {route.path for route in blocks.router.routes}
        self.assertFalse(any("/board" in path for path in paths))


class AppleRevocationTests(unittest.TestCase):
    def setUp(self):
        self.identity = ResolvedIdentity(11, "registered", True, "bearer", "issuer", "subject")
        self.user = {"id": "subject", "identities": [{"provider": "apple", "identity_data": {"sub": "apple-owner"}}]}
        loader = patch.object(apple_deletion, "_load_provider_user", return_value=self.user)
        self.loader = loader.start(); self.addCleanup(loader.stop)
        env = patch.dict("os.environ", {"APPLE_SIGNIN_TEAM_ID": "synthetic-team", "APPLE_SIGNIN_KEY_ID": "synthetic-key", "APPLE_SIGNIN_PRIVATE_KEY": "synthetic-placeholder-not-a-key"})
        env.start(); self.addCleanup(env.stop)

    def test_missing_code_leaves_followup_pending_without_remote_apple_call(self):
        with patch.object(apple_deletion, "post_form") as remote:
            self.assertEqual(apple_deletion.revoke_apple(self.identity, "Bearer synthetic", None), "pending")
        remote.assert_not_called()

    def test_no_apple_identity_does_not_need_revocation(self):
        self.user["identities"] = [{"provider": "email"}]
        self.assertEqual(apple_deletion.revoke_apple(self.identity, "Bearer synthetic", None), "not_required")

    def test_provider_identity_mismatch_stops_before_exchange(self):
        self.user["id"] = "someone-else"
        with patch.object(apple_deletion, "post_form") as remote:
            self.assertEqual(apple_deletion.revoke_apple(self.identity, "Bearer synthetic", "synthetic-code"), "pending")
        remote.assert_not_called()

    def test_revoke_only_after_verified_apple_subject_matches(self):
        for subject, expected, calls in [("apple-owner", "complete", 2), ("wrong-owner", "pending", 1)]:
            with self.subTest(subject=subject), patch.object(apple_deletion.jwt, "encode", return_value="synthetic-client-secret"), patch.object(apple_deletion.jwt, "decode", return_value={"sub": subject}) as verify, patch.object(apple_deletion._keys, "get_signing_key_from_jwt"), patch.object(apple_deletion, "post_form", side_effect=[{"id_token": "synthetic-id", "refresh_token": "synthetic-refresh"}, {}]) as remote:
                self.assertEqual(apple_deletion.revoke_apple(self.identity, "Bearer synthetic", "synthetic-code"), expected)
                self.assertEqual(remote.call_count, calls)
                self.assertEqual(verify.call_args.kwargs["audience"], "com.matchgoer.app")
                self.assertEqual(verify.call_args.kwargs["issuer"], "https://appleid.apple.com")

    def test_provider_failure_is_not_reported_as_success(self):
        self.loader.side_effect = RuntimeError("synthetic failure")
        self.assertEqual(apple_deletion.revoke_apple(self.identity, "Bearer synthetic", "synthetic-code"), "pending")


if __name__ == "__main__":
    unittest.main()
