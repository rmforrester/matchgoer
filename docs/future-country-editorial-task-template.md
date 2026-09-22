# Future country editorial task template

1. Load `docs/editorial-standard.md` and `docs/know-btm-decide-country-runbook.md`; report both SHA-256 values.
2. Freeze `[country]`, `[competitions]`, and `[season]`. Do not expand scope implicitly.
3. Complete and version the mandatory COUNTRY CONTEXT CALIBRATION. Judge significance through country -> football culture/pyramid -> region -> competition/level -> club/ground/supporter experience. Never use England or global scale as the threshold.
4. Complete the DECIDE LANDSCAPE CALIBRATION for all five canonical categories. Record researched candidates and adjudicated zeroes.
5. Reconcile identity/venue ownership and fail unresolved relationships closed.
6. Run an approximately five-relationship representative calibration across relevant levels/types. Research complete assembled experiences, including CLUB, SUPPORTERS, MATCHDAY, BTM, practical actions and relevant DECIDE. Do not use quotas or minimum fact counts.
7. Inspect actual rendered beta pages or equivalent real-page output. Record capture review and display review, including intentional sparse cases.
8. Set status to `FIRST_PASS_READY_FOR_HUMAN_REVIEW` and STOP. Codex must not approve this gate.
9. Require explicit Ray approval before any bulk country research or publication.
10. After approval, for every proposed/surviving fact record value route, why-care, disappearance loss, four duplication booleans, and editorial-standard version.
11. Self-adjudicate under the canonical standard. Omit filler. Validate deterministic gates, evidence, identity, ownership, candidate hash and expected-before state.
12. Prove exact writes with logical dry-run and rollback-only real SQL; back up immediately before an authorized atomic write. Reconcile, test serving and prove idempotence.
13. Complete residual reconciliation, then the country-wide survivor/completeness audit, then closeout.

## Hard gate

```text
COUNTRY CONTEXT CALIBRATION
        ↓
DECIDE LANDSCAPE CALIBRATION
        ↓
FIVE-RELATIONSHIP CALIBRATION
        ↓
FIRST_PASS_READY_FOR_HUMAN_REVIEW
        ↓
[EXPLICIT RAY APPROVAL REQUIRED]
        ↓
BULK COUNTRY ROLLOUT
```

If the first pass exposes a methodological failure, repair the general process and rerun the representative calibration. Do not patch only the sample pages.

No new country research begins while a prior country's closure gate is incomplete.

Scotland exposed the missing country-context and human product-review gates. Its next bounded action is `SCOTLAND CLUB/SUPPORTERS + DECIDE COMPLETENESS AUDIT` under Scotland's own context. Do not start that audit from this template update. Previously completed countries may later receive separately authorized regression audits; this process change does not reopen them automatically.
