import unittest
import json
from pathlib import Path

from editorial_contract import (
    FIRST_PASS_READY,
    STANDARD_VERSION,
    EditorialContractError,
    inspect_page,
    inspect_text,
    validate_bulk_country_gate,
    validate_contextual_significance,
    validate_language_strength,
    validate_ticket_copy_ownership,
    validate_voice_collection,
)


def review(**overrides):
    value = {
        "value_route": "PRACTICAL",
        "why_matchgoer_cares": "It prevents a supporter taking the wrong route.",
        "disappearance_loss": "The named station and walking route would be lost.",
        "ui_duplicate": False,
        "know_duplicate": False,
        "btm_duplicate": False,
        "decide_duplicate": False,
        "editorial_standard_version": STANDARD_VERSION,
    }
    value.update(overrides)
    return value


class EditorialContractTests(unittest.TestCase):
    def first_pass_gate(self):
        capture = {area: {"assessed": True, "outcome": "DELIBERATE_ZERO"} for area in ("club", "supporters", "matchday", "btm", "decide", "tickets", "directions")}
        return {"country_context_calibrated": True, "decide_landscape_calibrated": True, "representative_first_pass_status": FIRST_PASS_READY, "capture_review": capture, "tone_review": {"actual_supporter_copy_reviewed": True, "rendered_hierarchy_reviewed": True, "language_strength_levels": ["A", "B", "C"], "level_c_d_reviewed": True}, "rendered_page_reviewed": True, "human_approval": {"approved": True, "reviewed_by": "Ray", "approved_at": "2026-09-22T00:00:00Z"}}

    def test_specific_practical_fact_passes(self):
        page = [{"headline": "Arrival", "content": "Take PATH to Harrison; the stadium is a short signed walk from the station.", "editorial_review": review()}]
        self.assertEqual(inspect_page(page)["result"], "PASS")

    def test_missing_metadata_fails_closed(self):
        result = inspect_page([{"headline": "History", "content": "A useful story."}])
        self.assertIn("editorial_metadata", {item["code"] for item in result["failures"]})

    def test_generic_ticket_route_fails(self):
        result = inspect_text("Use the official ticketing page for current details.")
        self.assertIn("generic_ticket_routing", result["fails"])

    def test_confirm_before_travel_fails(self):
        result = inspect_text("Confirm the current venue and kickoff before travel.")
        self.assertIn("check_confirm_filler", result["fails"])

    def test_home_ground_metadata_fails(self):
        result = inspect_text("Example Stadium is the club's canonical home ground.")
        self.assertIn("venue_is_home", result["fails"])

    def test_generic_development_claim_is_human_flag(self):
        result = inspect_text("The club runs a development programme for young players.")
        self.assertIn("generic_development_claim", result["flags"])
        self.assertFalse(result["fails"])

    def test_exact_know_duplicate_fails(self):
        fact = {"headline": "Parking", "content": "Use Lot A after 5pm.", "editorial_review": review()}
        result = inspect_page([fact, dict(fact)])
        self.assertEqual(sum(x["code"] == "exact_know_duplicate" for x in result["failures"]), 2)

    def test_exact_btm_duplicate_fails(self):
        fact = {"headline": "Before the match", "content": "Meet at The Victory pub.", "editorial_review": review()}
        result = inspect_page([fact], ["Before the match Meet at The Victory pub."])
        self.assertIn("exact_btm_duplicate", {x["code"] for x in result["failures"]})

    def test_unknown_value_route_fails(self):
        fact = {"headline": "History", "content": "A distinctive story.", "editorial_review": review(value_route="TRIVIA")}
        self.assertEqual(inspect_page([fact])["result"], "FAIL")

    def test_contextual_lower_level_significance_is_permitted(self):
        validate_contextual_significance({"country":"Scotland","context_level":"REGION","context_rationale":"A rivalry with sustained regional meaning at this pyramid level.","supporter_value":"It materially changes how a visitor understands and chooses the fixture.","relative_distinction_only":False})

    def test_england_or_global_scale_is_not_required(self):
        validate_contextual_significance({"country":"Scotland","context_level":"COMPETITION_LEVEL","context_rationale":"The ground is a distinctive surviving example within this level of Scottish football.","supporter_value":"Its character materially changes the visit.","relative_distinction_only":False})

    def test_relative_significance_alone_fails(self):
        with self.assertRaises(EditorialContractError):
            validate_contextual_significance({"country":"Scotland","context_level":"REGION","context_rationale":"Largest locally.","supporter_value":"Locally larger.","relative_distinction_only":True})

    def test_bulk_gate_requires_deliberate_decide_assessment(self):
        gate=self.first_pass_gate(); gate["capture_review"]["decide"]["assessed"]=False
        with self.assertRaises(EditorialContractError): validate_bulk_country_gate(gate)

    def test_bulk_gate_cannot_auto_approve(self):
        gate=self.first_pass_gate(); gate["human_approval"]={"approved":True,"reviewed_by":"Codex","approved_at":"2026-09-22T00:00:00Z"}
        with self.assertRaises(EditorialContractError): validate_bulk_country_gate(gate)

    def test_bulk_gate_requires_explicit_human_approval(self):
        gate=self.first_pass_gate(); gate["human_approval"]["approved"]=False
        with self.assertRaises(EditorialContractError): validate_bulk_country_gate(gate)

    def test_sparse_representative_pages_can_pass(self):
        validate_bulk_country_gate(self.first_pass_gate())

    def test_practical_content_does_not_replace_club_research(self):
        gate=self.first_pass_gate(); gate["capture_review"]["club"]={"assessed":False,"outcome":"DELIBERATE_ZERO"}; gate["capture_review"]["matchday"]={"assessed":True,"outcome":"PUBLISH"}
        with self.assertRaises(EditorialContractError): validate_bulk_country_gate(gate)

    def test_rendered_page_review_is_required(self):
        gate=self.first_pass_gate(); gate["rendered_page_reviewed"]=False
        with self.assertRaises(EditorialContractError): validate_bulk_country_gate(gate)

    def test_supporter_copy_rejects_internal_rubric_language(self):
        self.assertIn("editorial_rubric_leakage", inspect_text("It plainly changes fixture choice.")["fails"])

    def test_unsupported_colour_is_flagged_for_evidence_review(self):
        self.assertIn("unsupported_colour_requires_evidence", inspect_text("Expect an electric atmosphere.")["flags"])

    def test_level_d_requires_explicit_ray_approval(self):
        with self.assertRaises(EditorialContractError): validate_language_strength("D")
        validate_language_strength("D", {"approved": True, "reviewed_by": "Ray", "approved_at": "2026-09-23T00:00:00Z"})

    def test_ticket_cta_owns_ordinary_purchase_route(self):
        with self.assertRaises(EditorialContractError):
            validate_ticket_copy_ownership({"fixture_buy_tickets_cta_present": True, "non_obvious_exception": False, "ordinary_purchase_instruction_retained": True})
        validate_ticket_copy_ownership({"fixture_buy_tickets_cta_present": True, "non_obvious_exception": True, "ordinary_purchase_instruction_retained": False})

    def test_repeated_voice_template_fails(self):
        with self.assertRaises(EditorialContractError):
            validate_voice_collection([{"copy": "Head to A."}, {"copy": "Head to B."}, {"copy": "Head to C."}])

    def test_varied_voice_collection_passes(self):
        validate_voice_collection([{"copy": "Head to A."}, {"copy": "B opens before kick-off."}, {"copy": "C is beside the ground."}])

    def test_bulk_gate_requires_tone_review(self):
        gate=self.first_pass_gate(); gate["tone_review"]["actual_supporter_copy_reviewed"]=False
        with self.assertRaises(EditorialContractError): validate_bulk_country_gate(gate)

    def test_regression_benchmark_is_complete_and_typed(self):
        path = Path(__file__).parents[2] / "docs" / "editorial-regression-benchmark.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["editorial_standard_version"], STANDARD_VERSION)
        self.assertGreaterEqual(len(data["cases"]), 15)
        self.assertEqual({case["expected"] for case in data["cases"]}, {"PASS", "FAIL"})
        self.assertTrue(all(case["value_route"] in {"DECISION", "UNDERSTANDING_EXPERIENCE", "PRACTICAL"} for case in data["cases"]))
        required={"fail-filler-quota","pass-contextual-lower-level-rivalry","fail-relative-only","fail-decide-neglect","fail-practical-dominance","fail-database-pass-product-fail","pass-tone-celtic-rangers-level-d","pass-tone-somerset-level-c","pass-tone-queens-park-club","pass-tone-clydebank-supporters","pass-tone-celtic-matchday","pass-tone-inverness-ticket-exception","pass-tone-troon-btm","pass-tone-restrained-btm","fail-tone-rubric-leakage","fail-tone-formula","fail-ticket-cta-duplication","pass-gold-bromley-trajectory","pass-gold-forres-name-discovery","fail-first-obvious-fact-stop","pass-correctly-sparse-complete-research"}
        self.assertTrue(required.issubset({case["id"] for case in data["cases"]}))

    def test_gold_standard_corpus_is_human_approved_and_complete(self):
        path = Path(__file__).parents[2] / "docs" / "editorial-gold-standard.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["standard_version"], STANDARD_VERSION)
        self.assertEqual(data["status"], "HUMAN_APPROVED_NORMATIVE_FUTURE_RESEARCH_CALIBRATION")
        self.assertEqual(data["counts"], {"GOLD_STANDARD":16,"ACCEPTABLE":4,"DO_NOT_EMULATE":6,"SPARSE_GOLD_STANDARD":4,"total":30})
        self.assertEqual(len(data["examples"]), 26)
        self.assertEqual(len(data["sparse_examples"]), 4)
        classes = {item["corpus_id"]: item["classification"] for item in data["examples"]}
        self.assertEqual(classes["KNOW-162"], "GOLD_STANDARD")
        self.assertEqual(classes["KNOW-1447"], "GOLD_STANDARD")
        self.assertEqual(classes["DECIDE-6"], "DO_NOT_EMULATE")
        self.assertEqual(classes["DECIDE-74"], "DO_NOT_EMULATE")
        self.assertTrue(all(item["exact_current_serving_copy"] for item in data["examples"]))

    def test_future_country_template_loads_gold_standard_and_process_rules(self):
        path = Path(__file__).parents[2] / "docs" / "future-country-editorial-task-template.md"
        content = path.read_text(encoding="utf-8")
        for required in (
            "docs/editorial-gold-standard.json", "Matchgoer/Copa90 test", "six-question filter",
            "contextual-significance doctrine", "research-depth standard", "source standard",
            "no-quota rule", "sparse-success rule", "CORRECTLY_SPARSE", "Level D",
            "FIRST_PASS_READY_FOR_HUMAN_REVIEW",
        ):
            self.assertIn(required, content)


if __name__ == "__main__":
    unittest.main()
