import copy
import unittest

from know_v1_legacy_inventory import classify
from know_v1_publication import identity_sha256, validate_manifest


def row(value):
    value["identity_sha256"] = identity_sha256(value)
    return value


def manifest(sensitive=False):
    fact = row({
        "editorial_key": "club:10:identity", "team_id": 10, "club_venue_id": None,
        "venue_id": None, "fixture_id": None, "module": "CLUB", "headline": None,
        "content": "A distinctive, evidence-backed club identity.", "display_order": 1,
        "publication_status": "PUBLISHED", "confidence": "HIGH",
        "claim_sensitivity": "SENSITIVE" if sensitive else "STANDARD",
        "reviewed_at": "2026-09-10", "review_after": "2027-09-10", "expires_at": None,
        "approved_at": "2026-09-10T12:00:00+00:00", "approved_by": "Editorial",
    })
    sources = [row({
        "fact_editorial_key": fact["editorial_key"], "source_type": "OFFICIAL",
        "source_title": "Official history", "source_url": "https://example.test/one",
        "source_date": "2026-09-10", "evidence_note": "Supports the published claim.",
        "disposition": "SUPPORTS", "review_status": "ACCEPTED", "contributor_user_id": None,
    })]
    if sensitive:
        sources.append(row({**{key: value for key, value in sources[0].items() if key != "identity_sha256"},
                            "source_type": "LOCAL_MEDIA", "source_title": "Independent history",
                            "source_url": "https://example.test/two"}))
    return {"artifact_version": "matchgoer-know-v1-publication",
            "publication_state": "FROZEN_PUBLICATION_CANDIDATE", "facts": [fact], "evidence": sources}


class KnowManifestTests(unittest.TestCase):
    def test_standard_and_sensitive_manifests_validate(self):
        validate_manifest(manifest())
        validate_manifest(manifest(sensitive=True))

    def test_exactly_one_subject_and_module_ownership_are_enforced(self):
        pack = manifest(); fact = pack["facts"][0]; fact["venue_id"] = 20; fact["identity_sha256"] = identity_sha256(fact)
        with self.assertRaisesRegex(RuntimeError, "exactly one subject"): validate_manifest(pack)
        pack = manifest(); fact = pack["facts"][0]; fact["team_id"] = None; fact["venue_id"] = 20; fact["identity_sha256"] = identity_sha256(fact)
        with self.assertRaisesRegex(RuntimeError, "team-owned"): validate_manifest(pack)

    def test_sensitive_claim_cannot_publish_with_one_source(self):
        pack = manifest(); pack["facts"][0]["claim_sensitivity"] = "SENSITIVE"; pack["facts"][0]["identity_sha256"] = identity_sha256(pack["facts"][0])
        with self.assertRaisesRegex(RuntimeError, "evidence policy failed"): validate_manifest(pack)

    def test_identity_hash_prevents_manifest_drift(self):
        pack = copy.deepcopy(manifest()); pack["facts"][0]["content"] = "Changed"
        with self.assertRaisesRegex(RuntimeError, "identity hash mismatch"): validate_manifest(pack)

    def test_legacy_inventory_never_auto_promotes_subjective_content(self):
        ticket = {"section": "tickets_entry", "topic": "official_ticket_portal"}
        culture = {"section": "at_ground", "topic": "Atmosphere"}
        before = {"section": "before_match", "topic": "Pre-match"}
        self.assertEqual(classify(ticket)[0], "KEEP_AS_UTILITY")
        self.assertEqual(classify(culture)[0], "KEEP_AS_UTILITY")
        self.assertEqual(classify(before)[0], "IDENTITY_BLOCKER")


if __name__ == "__main__": unittest.main()
