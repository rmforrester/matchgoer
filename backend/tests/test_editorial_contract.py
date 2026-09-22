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
        return {"country_context_calibrated": True, "decide_landscape_calibrated": True, "representative_first_pass_status": FIRST_PASS_READY, "capture_review": capture, "rendered_page_reviewed": True, "human_approval": {"approved": True, "reviewed_by": "Ray", "approved_at": "2026-09-22T00:00:00Z"}}

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

    def test_regression_benchmark_is_complete_and_typed(self):
        path = Path(__file__).parents[2] / "docs" / "editorial-regression-benchmark.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["editorial_standard_version"], STANDARD_VERSION)
        self.assertGreaterEqual(len(data["cases"]), 15)
        self.assertEqual({case["expected"] for case in data["cases"]}, {"PASS", "FAIL"})
        self.assertTrue(all(case["value_route"] in {"DECISION", "UNDERSTANDING_EXPERIENCE", "PRACTICAL"} for case in data["cases"]))
        required={"fail-filler-quota","pass-contextual-lower-level-rivalry","fail-relative-only","fail-decide-neglect","fail-practical-dominance","fail-database-pass-product-fail"}
        self.assertTrue(required.issubset({case["id"] for case in data["cases"]}))


if __name__ == "__main__":
    unittest.main()
