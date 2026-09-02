BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM teams WHERE team_id = 33 AND team_name = 'Manchester United')
       OR NOT EXISTS (SELECT 1 FROM teams WHERE team_id = 40 AND team_name = 'Liverpool') THEN
        RAISE EXCEPTION 'DECIDE proof team identity mismatch';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM venues WHERE venue_id = 23100 AND name = 'Stadio Giuseppe Meazza')
       OR NOT EXISTS (SELECT 1 FROM venues WHERE venue_id = 23114 AND name = 'Stadio Giuseppe Sinigaglia')
       OR NOT EXISTS (SELECT 1 FROM venues WHERE venue_id = 582 AND name = 'Hillsborough') THEN
        RAISE EXCEPTION 'DECIDE proof venue identity mismatch';
    END IF;
END $$;

INSERT INTO decision_facts (
    subject_type, team_a_id, team_b_id, venue_id, attribute_key,
    label, explanation, publication_status, confidence, reviewed_at, reviewed_by
) VALUES (
    'TEAM_PAIR', 33, 40, NULL, 'SIGNIFICANT_RIVALRY',
    'Manchester–Liverpool rivalry',
    'One of English football’s most iconic historic fixtures, contested by fierce rivals.',
    'PUBLISHED', 'HIGH', '2026-09-02T00:00:00Z', 'Matchgoer editorial proof'
)
ON CONFLICT (team_a_id, team_b_id, attribute_key) WHERE subject_type = 'TEAM_PAIR'
DO NOTHING;

INSERT INTO decision_facts (
    subject_type, team_a_id, team_b_id, venue_id, attribute_key,
    label, explanation, publication_status, confidence, reviewed_at, reviewed_by
) VALUES
    (
        'VENUE', NULL, NULL, 23100, 'FOOTBALL_LANDMARK',
        'European football landmark',
        'Watch football at a stadium that has staged four European Cup finals and matches at the 1990 World Cup.',
        'PUBLISHED', 'HIGH', '2026-09-02T00:00:00Z', 'Matchgoer editorial proof'
    ),
    (
        'VENUE', NULL, NULL, 23114, 'UNIQUE_SETTING',
        'Lake Como setting',
        'A lakeside stadium whose setting is part of the reason to experience a match in Como.',
        'PUBLISHED', 'HIGH', '2026-09-02T00:00:00Z', 'Matchgoer editorial proof'
    ),
    (
        'VENUE', NULL, NULL, 582, 'CLASSIC_GROUND',
        'Classic English ground',
        'Sheffield Wednesday’s home since 1899, with more than a century of football history across its four distinct stands.',
        'PUBLISHED', 'MEDIUM', '2026-09-02T00:00:00Z', 'Matchgoer editorial proof'
    )
ON CONFLICT (venue_id, attribute_key) WHERE subject_type = 'VENUE'
DO NOTHING;

WITH evidence_rows(attribute_key, source_title, source_url, evidence_note) AS (
    VALUES
        (
            'SIGNIFICANT_RIVALRY',
            'Premier League — Classic matches: Liverpool v Man Utd',
            'https://www.premierleague.com/en/news/3823068',
            'The Premier League describes this as an iconic and historic fixture between fierce rivals.'
        ),
        (
            'FOOTBALL_LANDMARK',
            'UEFA — Stadio San Siro',
            'https://www.uefa.com/uefachampionsleague/news/022a-0e933b9d8fdd-98791652690d-1000--stadio-san-siro/',
            'UEFA records four European Cup finals at San Siro and its redevelopment for the 1990 FIFA World Cup.'
        ),
        (
            'UNIQUE_SETTING',
            'Como 1907 — Chi siamo',
            'https://comofootball.com/chi-siamo/',
            'Como 1907 identifies Stadio Giuseppe Sinigaglia as its home on the shores of Lake Como.'
        ),
        (
            'CLASSIC_GROUND',
            'Premier League — Hillsborough stadium information',
            'https://www.premierleague.com/en/news/693386/hillsborough-stadium-info',
            'The stadium history records Hillsborough as Sheffield Wednesday’s home since 1899 and identifies its four distinct sections.'
        )
), proof_facts AS (
    SELECT fact_id, attribute_key FROM decision_facts
    WHERE (subject_type = 'TEAM_PAIR' AND team_a_id = 33 AND team_b_id = 40 AND attribute_key = 'SIGNIFICANT_RIVALRY')
       OR (subject_type = 'VENUE' AND venue_id = 23100 AND attribute_key = 'FOOTBALL_LANDMARK')
       OR (subject_type = 'VENUE' AND venue_id = 23114 AND attribute_key = 'UNIQUE_SETTING')
       OR (subject_type = 'VENUE' AND venue_id = 582 AND attribute_key = 'CLASSIC_GROUND')
)
INSERT INTO decision_evidence (
    fact_id, source_title, source_url, evidence_note, disposition,
    retrieved_at, reviewed_at, review_status
)
SELECT
    proof_facts.fact_id, evidence_rows.source_title, evidence_rows.source_url,
    evidence_rows.evidence_note, 'SUPPORTS', '2026-09-02',
    '2026-09-02T00:00:00Z', 'ACCEPTED'
FROM proof_facts
JOIN evidence_rows USING (attribute_key)
WHERE NOT EXISTS (
    SELECT 1 FROM decision_evidence existing
    WHERE existing.fact_id = proof_facts.fact_id
      AND existing.source_url = evidence_rows.source_url
      AND existing.evidence_note = evidence_rows.evidence_note
);

DO $$
DECLARE
    matching_facts INTEGER;
    proof_evidence INTEGER;
    proof_evidence_total INTEGER;
BEGIN
    SELECT count(*) INTO matching_facts
    FROM decision_facts
    WHERE
        (subject_type = 'TEAM_PAIR' AND team_a_id = 33 AND team_b_id = 40 AND venue_id IS NULL
         AND attribute_key = 'SIGNIFICANT_RIVALRY' AND label = 'Manchester–Liverpool rivalry'
         AND explanation = 'One of English football’s most iconic historic fixtures, contested by fierce rivals.'
         AND publication_status = 'PUBLISHED' AND confidence = 'HIGH')
        OR
        (subject_type = 'VENUE' AND venue_id = 23100 AND team_a_id IS NULL AND team_b_id IS NULL
         AND attribute_key = 'FOOTBALL_LANDMARK' AND label = 'European football landmark'
         AND explanation = 'Watch football at a stadium that has staged four European Cup finals and matches at the 1990 World Cup.'
         AND publication_status = 'PUBLISHED' AND confidence = 'HIGH')
        OR
        (subject_type = 'VENUE' AND venue_id = 23114 AND team_a_id IS NULL AND team_b_id IS NULL
         AND attribute_key = 'UNIQUE_SETTING' AND label = 'Lake Como setting'
         AND explanation = 'A lakeside stadium whose setting is part of the reason to experience a match in Como.'
         AND publication_status = 'PUBLISHED' AND confidence = 'HIGH')
        OR
        (subject_type = 'VENUE' AND venue_id = 582 AND team_a_id IS NULL AND team_b_id IS NULL
         AND attribute_key = 'CLASSIC_GROUND' AND label = 'Classic English ground'
         AND explanation = 'Sheffield Wednesday’s home since 1899, with more than a century of football history across its four distinct stands.'
         AND publication_status = 'PUBLISHED' AND confidence = 'MEDIUM');

    SELECT count(*) INTO proof_evidence
    FROM decision_evidence evidence
    JOIN decision_facts fact ON fact.fact_id = evidence.fact_id
    WHERE evidence.disposition = 'SUPPORTS'
      AND evidence.review_status = 'ACCEPTED'
      AND (
        (fact.subject_type = 'TEAM_PAIR' AND fact.team_a_id = 33 AND fact.team_b_id = 40
         AND fact.attribute_key = 'SIGNIFICANT_RIVALRY'
         AND evidence.source_url = 'https://www.premierleague.com/en/news/3823068')
        OR
        (fact.subject_type = 'VENUE' AND fact.venue_id = 23100
         AND fact.attribute_key = 'FOOTBALL_LANDMARK'
         AND evidence.source_url = 'https://www.uefa.com/uefachampionsleague/news/022a-0e933b9d8fdd-98791652690d-1000--stadio-san-siro/')
        OR
        (fact.subject_type = 'VENUE' AND fact.venue_id = 23114
         AND fact.attribute_key = 'UNIQUE_SETTING'
         AND evidence.source_url = 'https://comofootball.com/chi-siamo/')
        OR
        (fact.subject_type = 'VENUE' AND fact.venue_id = 582
         AND fact.attribute_key = 'CLASSIC_GROUND'
         AND evidence.source_url = 'https://www.premierleague.com/en/news/693386/hillsborough-stadium-info')
      );

    SELECT count(*) INTO proof_evidence_total
    FROM decision_evidence evidence
    JOIN decision_facts fact ON fact.fact_id = evidence.fact_id
    WHERE (fact.subject_type = 'TEAM_PAIR' AND fact.team_a_id = 33 AND fact.team_b_id = 40
           AND fact.attribute_key = 'SIGNIFICANT_RIVALRY')
       OR (fact.subject_type = 'VENUE' AND fact.venue_id = 23100 AND fact.attribute_key = 'FOOTBALL_LANDMARK')
       OR (fact.subject_type = 'VENUE' AND fact.venue_id = 23114 AND fact.attribute_key = 'UNIQUE_SETTING')
       OR (fact.subject_type = 'VENUE' AND fact.venue_id = 582 AND fact.attribute_key = 'CLASSIC_GROUND');

    IF matching_facts <> 4 OR proof_evidence <> 4 OR proof_evidence_total <> 4 THEN
        RAISE EXCEPTION 'DECIDE proof reconciliation failed: facts %, expected evidence %, total proof evidence %',
            matching_facts, proof_evidence, proof_evidence_total;
    END IF;
END $$;

COMMIT;
