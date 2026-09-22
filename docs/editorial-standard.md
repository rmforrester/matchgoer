# Matchgoer editorial standard

Version: `2026-09-22`

> **EDITORIAL USEFULNESS IS THE PUBLICATION CRITERION.** Architecture, evidence, reconciliation and publication safety support that criterion; they never substitute for it.
>
> **ENGLAND IS THE CALIBRATION BENCHMARK. SCALE CHANGES BATCHING, NEVER THE STANDARD. ABSENCE IS BETTER THAN FILLER.**

This is the single authoritative editorial contract for KNOW, Before the Match (BTM), and DECIDE in every country.

## Publication test

Research the matchgoer experience, not database categories. A fact may publish only if it gives a supporter at least one of:

- **DECISION:** information that could change whether or which match they attend;
- **UNDERSTANDING_EXPERIENCE:** distinctive context that changes how they understand the club, ground, or supporter experience;
- **PRACTICAL:** a specific action, restriction, route, timing, entry, ticket, or local instruction.

Every candidate must answer:

1. **Why would a matchgoer care?**
2. **If this disappeared, what specific useful information would the supporter lose?**

If neither answer is specific, omit the item. There is no category-completeness target and no minimum fact count. A sparse page is valid.

## Required review

Review the assembled supporter page, not isolated rows. Check:

- redundancy with labels, fixture data, venue cards, and other UI;
- KNOW against other KNOW on the same page;
- KNOW against BTM and DECIDE;
- venue-container facts that merely repeat the relationship or ground name;
- whether canonical content can be reused across competitions rather than recreated.

Existing content is not grandfathered. Every country closes with a survivor sweep in which every published KNOW fact re-earns its place.

## Module standards

### KNOW

- History must explain meaningful club, ground, or supporter continuity; chronology alone is insufficient.
- Supporter culture must describe a genuine evidenced practice, place, tradition, campaign, or lived identity. Naming a group alone is insufficient.
- Practical guidance must be actionable and local. “Use the official ticket route,” “consult the guide,” “check current arrangements,” and “confirm before travel” are omissions, not facts.
- A venue being a club's home is relationship metadata unless the statement adds supporter-relevant meaning.

### Before the Match

A BTM spot must be a named, recurring, evidenced physical destination or area with useful audience/location context. Do not convert a vague area, temporary event, or unsupported recommendation into a spot. If none is established, publish none.

### DECIDE

DECIDE is selective. A rivalry, classic ground, landmark, unique setting, or exceptional support signal must genuinely influence a supporter's choice. It is not a second home for ordinary history or generic praise.

## Evidence and identity

Evidence is necessary but not sufficient. Evidence proves a claim; it does not prove the claim deserves screen space. Cohort evidence can establish scope but cannot manufacture local detail. Facts must retain canonical subject ownership and pass identity reconciliation. Identity or venue ambiguity blocks publication while leaving editorial research status explicit.

## Examples

### PASS

- Luton's public-meeting origin: meaningful supporter-facing club formation context.
- Leicester's continuity with Filbert Street: explains the present ground experience through a former home.
- MetroStars to Red Bulls: meaningful identity continuity.
- Save The Crew and the Nordecke: supporter action and culture that change how a visitor understands Columbus.
- Chico Stand and the South Ward: named, evidenced supporter locations and practices.
- Philadelphia's supporter-created club story: explains why the club exists.
- Portland/Timbers lineage and the Victory Log: distinctive history and match ritual.
- A named station, route, walk, parking restriction, gate rule, or ticket mechanism that lets a supporter act.
- A real named BTM destination with current evidence and location context.

These examples calibrate value; their wording is not a template.

### FAIL

- “Use the official ticket route.”
- “Consult the A-to-Z guide.”
- “Confirm the venue before travel.”
- “Check current arrangements.”
- “This venue is the club's home.”
- “Public transport is available.”
- Generic community mission or development claims without distinctive supporter relevance.
- A supporter-group description that only says the group supports the team.
- Parking advice already communicated elsewhere on the same page.

## Candidate review metadata

Each proposed or surviving published fact must carry this artifact-level review object:

```json
{
  "value_route": "DECISION | UNDERSTANDING_EXPERIENCE | PRACTICAL",
  "why_matchgoer_cares": "specific non-empty explanation",
  "disappearance_loss": "specific non-empty loss",
  "ui_duplicate": false,
  "know_duplicate": false,
  "btm_duplicate": false,
  "decide_duplicate": false,
  "editorial_standard_version": "2026-09-22"
}
```

These fields belong in frozen candidate artifacts and validation receipts. They are publisher-required for future-country workflows, but are not database-persisted: adding columns would not improve the supporter product and would create unnecessary schema. Historical candidates remain reproducible under their original contracts; they do not authorize new publication.

## Automated and human gates

**Automated fail:** missing/invalid review metadata, known generic ticket/check/confirm/home-ground patterns, exact KNOW duplicates, deterministic exact KNOW/BTM duplication, module/subject incompatibility, or missing standard version.

**Automated flag:** generic mission/development/supporter-group prose, vague transport, near duplicates, or possible semantic overlap. A flag requires review and a recorded disposition.

**Human/LLM judgment:** usefulness, distinctiveness, evidence sufficiency, semantic duplication, supporter relevance, and whether DECIDE changes choice. Automation cannot approve prose by itself.

## Publication safety

The required sequence is: canonical target fingerprint; frozen candidate and SHA-256; expected-before binding; identity reconciliation; module/subject validation; logical dry-run; **rollback-only real SQL proof**; verified post-rollback restoration; fresh backup; atomic write; read-only reconciliation when outcome is uncertain; serving acceptance; idempotence. A logical dry-run alone never authorizes mutation.

