BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM teams WHERE team_id = 1321 AND team_name = 'Hansa Rostock')
       OR NOT EXISTS (SELECT 1 FROM teams WHERE team_id = 4259 AND team_name = 'Alemannia Aachen')
       OR NOT EXISTS (SELECT 1 FROM teams WHERE team_id = 187 AND team_name = 'MSV Duisburg')
       OR NOT EXISTS (SELECT 1 FROM teams WHERE team_id = 1621 AND team_name = 'Rot-Weiss Essen') THEN
        RAISE EXCEPTION 'DECIDE exceptional-support canonical team identity mismatch';
    END IF;
END $$;

WITH approved(team_id, explanation) AS (
    VALUES
        (1321, '2025/26 average home attendance 24,948, around 2.38× the 3. Liga average.'),
        (4259, '2025/26 average home attendance 23,098, around 2.21× the 3. Liga average.'),
        (187, '2025/26 average home attendance 22,949, around 2.19× the 3. Liga average.'),
        (1621, '2025/26 average home attendance 17,361, around 1.66× the 3. Liga average.')
)
INSERT INTO decision_facts (
    subject_type, team_a_id, team_b_id, venue_id, team_id, attribute_key,
    label, explanation, publication_status, confidence, lead_priority,
    reviewed_at, reviewed_by
)
SELECT
    'TEAM', NULL, NULL, NULL, team_id, 'EXCEPTIONAL_SUPPORT',
    'Exceptional support', explanation, 'PUBLISHED', 'HIGH', 'LEAD',
    '2026-09-03T00:00:00Z', 'Matchgoer five-country editorial inventory v0.1'
FROM approved
ON CONFLICT (team_id, attribute_key) WHERE subject_type = 'TEAM'
DO NOTHING;

INSERT INTO decision_evidence (
    fact_id, source_title, source_url, evidence_note, disposition,
    retrieved_at, reviewed_at, review_status
)
SELECT
    fact.fact_id,
    'DFB — 3. Liga 2025/26 highlight facts',
    'https://www.dfb.de/news/rekorde-talente-fans-die-highlightfakten-der-3-liga',
    'Completed 2025/26 season. DFB league average: 10,470; the approved fact explanation records the club average and ratio.',
    'SUPPORTS', '2026-09-03', '2026-09-03T00:00:00Z', 'ACCEPTED'
FROM decision_facts fact
WHERE fact.subject_type = 'TEAM'
  AND fact.attribute_key = 'EXCEPTIONAL_SUPPORT'
  AND fact.team_id IN (1321, 4259, 187, 1621)
  AND NOT EXISTS (
      SELECT 1 FROM decision_evidence evidence
      WHERE evidence.fact_id = fact.fact_id
        AND evidence.source_url = 'https://www.dfb.de/news/rekorde-talente-fans-die-highlightfakten-der-3-liga'
        AND evidence.review_status = 'ACCEPTED'
  );

DO $$
DECLARE
    exact_facts INTEGER;
    exact_evidence INTEGER;
BEGIN
    SELECT count(*) INTO exact_facts
    FROM decision_facts
    WHERE subject_type = 'TEAM'
      AND attribute_key = 'EXCEPTIONAL_SUPPORT'
      AND team_id IN (1321, 4259, 187, 1621)
      AND label = 'Exceptional support'
      AND publication_status = 'PUBLISHED'
      AND confidence = 'HIGH'
      AND lead_priority = 'LEAD';

    SELECT count(*) INTO exact_evidence
    FROM decision_evidence evidence
    JOIN decision_facts fact USING (fact_id)
    WHERE fact.subject_type = 'TEAM'
      AND fact.attribute_key = 'EXCEPTIONAL_SUPPORT'
      AND fact.team_id IN (1321, 4259, 187, 1621)
      AND evidence.source_url = 'https://www.dfb.de/news/rekorde-talente-fans-die-highlightfakten-der-3-liga'
      AND evidence.disposition = 'SUPPORTS'
      AND evidence.review_status = 'ACCEPTED';

    IF exact_facts <> 4 OR exact_evidence <> 4 THEN
        RAISE EXCEPTION 'DECIDE five-country publication reconciliation failed: facts %, evidence %', exact_facts, exact_evidence;
    END IF;
END $$;

COMMIT;
