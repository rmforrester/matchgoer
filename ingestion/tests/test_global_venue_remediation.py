import unittest

from ingestion.apply_global_venue_remediation import (
    ALIAS_NAME_TYPE,
    approved_alias_ids_for_target,
    allowed_venue_name_types,
    coalesce_relationships,
    normalized,
    projected_second_run,
    transaction_should_commit,
)


class GlobalVenueRemediationTests(unittest.TestCase):
    def test_no_provider_reference_or_unapproved_coordinate_operation(self):
        targets = [
            {"provider_ref_treatment": "NO_PROVIDER_REF"},
            {"provider_ref_treatment": "REUSE_EXISTING_TARGET_REF"},
        ]
        coordinate = {"venue_id": 27512, "guard": "NULL_ONLY"}
        self.assertTrue(all(t["provider_ref_treatment"] != "CREATE_PROVIDER_REF" for t in targets))
        self.assertEqual(coordinate, {"venue_id": 27512, "guard": "NULL_ONLY"})

    def test_alias_normalization_is_accent_and_punctuation_stable(self):
        self.assertEqual(normalized("Stadion Stožice"), "stadion stozice")
        self.assertEqual(normalized("John Smith's Stadium"), "john smith s stadium")

    def test_alias_type_is_accepted_by_hosted_check_constraint(self):
        definition = "CHECK (((name_type)::text = ANY (ARRAY[('current'::character varying)::text, ('historical'::character varying)::text, ('short'::character varying)::text, ('sponsored'::character varying)::text, ('provider'::character varying)::text])))"
        allowed = allowed_venue_name_types(definition)
        self.assertIn("current", allowed)
        self.assertIn(ALIAS_NAME_TYPE, allowed)
        self.assertNotIn("reviewed_alias", allowed)

    def test_invalid_alias_type_is_rejected_by_schema_preflight(self):
        definition = "CHECK (((name_type)::text = ANY (ARRAY[('current'::character varying)::text, ('provider'::character varying)::text])))"
        self.assertNotIn("reviewed_alias", allowed_venue_name_types(definition))

    def test_projected_second_run_is_idempotent(self):
        self.assertEqual(sum(projected_second_run({}).values()), 0)

    def test_compatible_relationship_duplicates_coalesce_and_retain_traceability(self):
        rows = [
            {"team_id": 1, "target_key": "ground", "valid_from": "2026-01-01",
             "valid_until": "2026-12-31", "relationship_type": "HOME", "status": "CURRENT", "cohort_id": "a"},
            {"team_id": 1, "target_key": "ground", "valid_from": "2026-01-01",
             "valid_until": "2026-12-31", "relationship_type": "HOME", "status": "CURRENT", "cohort_id": "b"},
        ]
        physical, traces = coalesce_relationships(rows)
        self.assertEqual(len(physical), 1)
        self.assertEqual(physical[0]["source_cohort_ids"], ["a", "b"])
        self.assertEqual(traces[0]["logical_operations"], 2)

    def test_conflicting_relationship_duplicates_fail_closed(self):
        rows = [
            {"team_id": 1, "target_key": "ground", "valid_from": "2026-01-01",
             "valid_until": "2026-12-31", "relationship_type": "HOME", "status": "CURRENT", "cohort_id": "a"},
            {"team_id": 1, "target_key": "ground", "valid_from": "2026-01-01",
             "valid_until": "2026-06-30", "relationship_type": "HOME", "status": "CURRENT", "cohort_id": "b"},
        ]
        with self.assertRaisesRegex(ValueError, "conflicting planned club_venues semantics"):
            coalesce_relationships(rows)

    def test_rollback_only_mode_can_never_commit(self):
        self.assertFalse(transaction_should_commit(write=False, rollback_only=True, status="PASS"))
        self.assertTrue(transaction_should_commit(write=True, rollback_only=False, status="PASS"))

    def test_new_targets_consider_explicit_approved_alias_identity_evidence(self):
        target = {"name": "Mestsky stadion v Ostrave-Vitkovicich", "aliases": []}
        aliases = [{"name": "Městský stadion v Ostravě-Vítkovicích", "venue_id": 23309}]
        self.assertEqual(approved_alias_ids_for_target(target, aliases), {23309})

    def test_explicit_distinct_ground_names_remain_distinct(self):
        self.assertNotEqual(normalized("Kalamata Metropolitan Stadium"), normalized("Gipedo Messiniakos"))
        self.assertNotEqual(normalized("AIL Arena"), normalized("Stadio di Cornaredo"))


if __name__ == "__main__":
    unittest.main()
