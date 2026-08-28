from __future__ import annotations

import copy
import hashlib
import json
import os
import unittest
from pathlib import Path

from know_population import load_candidate, validate_pack
from know_review_queue import AUTO_APPROVED, HUMAN_REVIEW, NO_EVIDENCE, build_review_queue, classify


def identity(row):
    value = dict(row)
    value.pop("identity_sha256", None)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()


class ExistingCandidateCompatibilityTests(unittest.TestCase):
    def _load(self, path_variable, sha, version):
        path = os.environ.get(path_variable)
        if not path or not Path(path).is_file():
            self.skipTest(f"{path_variable} not supplied")
        return load_candidate(path, expected_sha256=sha, expected_version=version)

    def test_existing_batch_1_candidate_semantics(self):
        candidate = self._load(
            "MATCHGOER_KNOW_BATCH1_CANDIDATE",
            "57403F7ECD5162CDB9314F74CB671B9FBE2C4C50639249DD983138B4A1F2ACE7",
            "english-know-content-v1",
        )
        self.assertEqual(candidate.counts, {
            "venue_guide_facts": 15, "pre_match_spots": 13, "pre_match_spot_evidence": 30,
        })

    def test_existing_batch_2_candidate_semantics_and_dynamic_counts(self):
        candidate = self._load(
            "MATCHGOER_KNOW_BATCH2_CANDIDATE",
            "54B80A7268413FF7C7D6DD14DB22B4924B3DC758C0945685EA4926065870B2B1",
            "english-know-content-v2-publication-candidate",
        )
        self.assertEqual(candidate.counts, {
            "venue_guide_facts": 30, "pre_match_spots": 18, "pre_match_spot_evidence": 30,
        })
        self.assertEqual(candidate.mutations, 78)

        changed = copy.deepcopy(candidate.pack)
        other = changed["clubs"][1]
        changed["venue_guide_facts"][0]["team_id"] = other["team_id"]
        changed["venue_guide_facts"][0]["identity_sha256"] = identity(changed["venue_guide_facts"][0])
        with self.assertRaisesRegex(RuntimeError, "unsupported content owner"):
            validate_pack(changed, candidate.version)

        changed = copy.deepcopy(candidate.pack)
        changed.pop("publication_state")
        with self.assertRaisesRegex(RuntimeError, "publication state"):
            validate_pack(changed, candidate.version)


class BusinessStatusContractTests(unittest.TestCase):
    def candidate(
        self,
        business_status="OPEN",
        audience="HOME",
        display_order=1,
        **evidence_changes,
    ):
        spot = {
            "team_id": 1, "venue_id": 2, "club_venue_id": 3,
            "display_name": "Test Fan Zone", "classification": "CLUB_MATCHDAY_VENUE",
            "audience": audience, "supporting_line": "Open before home matches.",
            "maps_destination": "Test Fan Zone", "confidence": "HIGH", "status": "CURRENT",
            "business_status": business_status, "reviewed_at": "2026-08-29",
            "review_after": "2027-02-28", "display_order": display_order,
            "approved_at": "2026-08-29T12:00:00+00:00", "approved_by": "Test",
        }
        spot["identity_sha256"] = identity(spot)
        evidence = {
            "spot_identity_sha256": spot["identity_sha256"], "source_type": "OFFICIAL",
            "source_url": "https://example.com/matchday", "source_date": "2026-08-29",
            "disposition": "SUPPORTS", "evidence_note": "Official matchday guide.",
            "review_status": "ACCEPTED",
        }
        evidence.update(evidence_changes)
        evidence["identity_sha256"] = identity(evidence)
        return {
            "artifact_version": "test-candidate", "publication_state": "PUBLICATION_CANDIDATE",
            "clubs": [{"team_id": 1, "venue_id": 2, "club_venue_id": 3}],
            "venue_guide_facts": [], "pre_match_spots": [spot],
            "pre_match_spot_evidence": [evidence],
        }

    def test_database_business_status_vocabulary_is_the_candidate_contract(self):
        for value in ("OPEN", "UNKNOWN", "CLOSED", "NOT_APPLICABLE"):
            with self.subTest(value=value):
                validate_pack(self.candidate(value), "test-candidate")

        with self.assertRaisesRegex(RuntimeError, "unpublishable/unapproved pre-match spot"):
            validate_pack(self.candidate("OPERATIONAL"), "test-candidate")

    def test_england_75_candidate_generation_boundary_cannot_emit_operational(self):
        with self.assertRaisesRegex(RuntimeError, "unpublishable/unapproved pre-match spot"):
            validate_pack(self.candidate("OPERATIONAL"), "test-candidate")

    def test_audience_uses_hosted_vocabulary_and_length(self):
        validate_pack(self.candidate(audience="MIXED"), "test-candidate")
        for value in ("MATCH_TICKET_HOLDERS", "HOME_FAMILY"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RuntimeError, "unpublishable/unapproved pre-match spot"):
                    validate_pack(self.candidate(audience=value), "test-candidate")

    def test_spot_display_order_uses_hosted_range(self):
        for value in (1, 2, 3):
            with self.subTest(value=value):
                validate_pack(self.candidate(display_order=value), "test-candidate")
        for value in (0, 4):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RuntimeError, "unpublishable/unapproved pre-match spot"):
                    validate_pack(self.candidate(display_order=value), "test-candidate")

    def test_evidence_uses_hosted_vocabulary(self):
        validate_pack(self.candidate(source_type="OFFICIAL", review_status="ACCEPTED"), "test-candidate")
        for changes in ({"source_type": "official"}, {"review_status": "APPROVED"}):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(RuntimeError, "unpublishable pre-match spot evidence"):
                    validate_pack(self.candidate(**changes), "test-candidate")


class ReviewQueueTests(unittest.TestCase):
    def proposal(self, **changes):
        value = {
            "club": "Example FC", "content_type": "pre_match_spot", "candidate": "Example Arms",
            "classification": "SUPPORTER_SPOT", "supporter_wording": "A home-supporter pre-match pub.",
            "best_evidence": "Current independent supporter evidence.", "evidence_strength": "STRONG",
            "publication_eligible": True, "review_reason": "Only one useful source was found.",
        }
        value.update(changes)
        return value

    def test_three_way_classification_and_compact_exception_queue(self):
        automatic = self.proposal()
        review = self.proposal(evidence_strength="PLAUSIBLE", publication_eligible=False)
        empty = self.proposal(candidate=None, supporter_wording=None, best_evidence=None)
        self.assertEqual(classify(automatic), AUTO_APPROVED)
        self.assertEqual(classify(review), HUMAN_REVIEW)
        self.assertEqual(classify(empty), NO_EVIDENCE)
        groups, queue = build_review_queue([automatic, review, empty])
        self.assertEqual({key: len(value) for key, value in groups.items()}, {
            AUTO_APPROVED: 1, HUMAN_REVIEW: 1, NO_EVIDENCE: 1,
        })
        self.assertEqual(queue, [{
            "club": "Example FC",
            "candidate": "Example Arms",
            "proposed_classification": "SUPPORTER_SPOT",
            "proposed_supporter_wording": "A home-supporter pre-match pub.",
            "why_not_auto_approved": "Only one useful source was found.",
            "best_supporting_evidence": "Current independent supporter evidence.",
            "decision": "APPROVE / REJECT / AMEND",
        }])

    def test_club_matchday_venue_can_auto_approve_without_supporter_popularity_claim(self):
        proposal = self.proposal(
            classification="CLUB_MATCHDAY_VENUE",
            supporter_wording="The official fan zone offers food and drink before home matches.",
            best_evidence="Current official club matchday guide.",
        )
        self.assertEqual(classify(proposal), AUTO_APPROVED)


if __name__ == "__main__":
    unittest.main()
