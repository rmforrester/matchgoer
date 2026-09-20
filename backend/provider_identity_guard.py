"""Lightweight verification for provider-derived canonical ownership."""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import text

ACCEPTABLE = {"IDENTITY_COMPATIBLE", "REVIEWED_SCOPED_OVERRIDE", "NEW_PROVIDER_TEAM"}
RECEIPT_FIELDS = {
    "provider", "provider_team_id", "canonical_team_id", "observed_name",
    "canonical_name", "league_id", "season", "identity_resolution",
    "approved_override_id", "resolver_version",
}


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or "").casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", value))


def validate_provider_relationship_contract(row: dict, error_type=ValueError) -> None:
    if not row.get("provider_derived", False):
        return
    receipt = row.get("identity_receipt")
    if not isinstance(receipt, dict) or not RECEIPT_FIELDS.issubset(receipt):
        raise error_type("provider-derived relationship requires a complete identity receipt")
    outcome = receipt.get("identity_resolution")
    if outcome not in ACCEPTABLE:
        raise error_type("provider-derived relationship has unacceptable identity resolution")
    for key in ("provider_team_id", "canonical_team_id", "league_id", "season"):
        if not isinstance(receipt.get(key), int):
            raise error_type(f"identity receipt requires integer {key}")
    if receipt["provider_team_id"] <= 0 or receipt["canonical_team_id"] == 0:
        raise error_type("identity receipt contains an invalid team ID")
    if receipt["canonical_team_id"] != row.get("team_id"):
        raise error_type("identity receipt canonical team mismatch")
    if not normalized(receipt.get("canonical_name")) or normalized(receipt["canonical_name"]) != normalized(row.get("team_name")):
        raise error_type("identity receipt canonical name snapshot mismatch")
    if not str(receipt.get("provider") or "").strip() or not str(receipt.get("observed_name") or "").strip() or not str(receipt.get("resolver_version") or "").strip():
        raise error_type("identity receipt text fields are incomplete")
    if outcome in {"IDENTITY_COMPATIBLE", "NEW_PROVIDER_TEAM"} and receipt["canonical_team_id"] != receipt["provider_team_id"]:
        raise error_type("ordinary provider resolution must preserve the positive provider ID")
    if outcome == "REVIEWED_SCOPED_OVERRIDE" and not isinstance(receipt.get("approved_override_id"), int):
        raise error_type("reviewed override receipt requires approved_override_id")
    if outcome != "REVIEWED_SCOPED_OVERRIDE" and receipt.get("approved_override_id") is not None:
        raise error_type("ordinary identity receipt cannot claim an override")


def verify_provider_relationship(connection, row: dict, error_type=ValueError) -> None:
    validate_provider_relationship_contract(row, error_type)
    if not row.get("provider_derived", False):
        return
    receipt = row["identity_receipt"]
    team = connection.execute(
        text("SELECT team_id, team_name FROM teams WHERE team_id=:id"),
        {"id": receipt["canonical_team_id"]},
    ).mappings().one_or_none()
    if team is None:
        raise error_type("provider-derived relationship canonical team is missing")
    if normalized(team["team_name"]) != normalized(receipt["canonical_name"]):
        raise error_type("provider-derived relationship canonical name has drifted")
    if receipt["identity_resolution"] != "REVIEWED_SCOPED_OVERRIDE":
        return
    override = connection.execute(text("""
        SELECT team_identity_override_id FROM team_identity_overrides
        WHERE team_identity_override_id=:override_id
          AND provider=:provider AND provider_team_id=:provider_team_id
          AND canonical_team_id=:canonical_team_id
          AND league_id=:league_id AND season=:season
          AND review_status='APPROVED' AND reviewed_at IS NOT NULL
    """), {
        "override_id": receipt["approved_override_id"],
        "provider": receipt["provider"],
        "provider_team_id": receipt["provider_team_id"],
        "canonical_team_id": receipt["canonical_team_id"],
        "league_id": receipt["league_id"],
        "season": receipt["season"],
    }).scalar_one_or_none()
    if override is None:
        raise error_type("reviewed scoped override is missing, unapproved, or out of scope")
