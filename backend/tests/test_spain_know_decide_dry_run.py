import copy
import unittest
import contextlib
import io
from collections import Counter
from unittest.mock import patch

from backend.spain_know_decide_dry_run import (
    ANDORRA_FIXTURES, CATEGORIES, ENTRY_TEAMS, EXPECTED_ARTIFACTS, GREAT_SUPPORT,
    REMEDIATION, SafetyError, approved, identity, rows, sha, validate,
)
from backend.spain_know_decide_publication import (
    audit, evidence_values, guide_values, html_plan, physical_diff,
    spot_values, verify_changed_columns, main, schema_violations,
)
import backend.spain_know_decide_publication as publication


class SpainContractTests(unittest.TestCase):
    def setUp(self):
        self.know,self.decide,self.facts=approved()

    def test_reviewed_hashes_population_categories_and_dormant_are_exact(self):
        self.assertTrue(all(sha(p)==h for p,h in EXPECTED_ARTIFACTS.items()))
        self.assertEqual(len(self.know),42)
        self.assertEqual(Counter(r['competition'] for r in self.know),{'La Liga':20,'Segunda':22})
        self.assertEqual(Counter(r['category'] for r in self.decide),CATEGORIES)
        self.assertEqual(len(self.facts),51)
        self.assertNotIn('Cádiz — Xerez',{r['subject'] for r in self.facts})
        self.assertEqual({r['team_id'] for r in self.facts if r['subject_type']=='TEAM'},GREAT_SUPPORT)

    def test_null_partition_rejects_residual_fields(self):
        self.assertEqual(Counter(r['intentional_null'] for r in self.know),{'False':18,'True':24})
        next(r for r in self.know if r['intentional_null']=='True')['maps_destination']='unreviewed'
        with self.assertRaisesRegex(SafetyError,'residual NULL'):
            validate(self.know,self.decide,rows(REMEDIATION))

    def test_entry_maps_all_five_reviewed_rows_without_rewriting(self):
        entries=[r for r in self.know if r['entry_description']]
        self.assertEqual({int(r['canonical_team_id']) for r in entries},ENTRY_TEAMS)
        for r in entries:
            v=guide_values(r,True)
            self.assertEqual(v['section'],r['entry_section'])
            self.assertEqual(v['topic'],'Entry')
            self.assertEqual(v['content'],r['entry_description'])
            self.assertEqual(v['source_url'],r['entry_evidence_url'])
            self.assertEqual(v['source_type'],r['entry_source_type'])

    def test_btm_copy_directions_and_metadata_are_preserved(self):
        for r in self.know:
            if r['intentional_null']=='True':
                continue
            v=spot_values(r)
            for key in ('display_name','supporting_line','maps_destination','classification','audience','business_status'):
                self.assertEqual(v[key],r[key])
            self.assertEqual(v['status'],r['pre_match_status'])
            self.assertEqual(v['confidence'],r['pre_match_confidence'])
            self.assertEqual(v['display_order'],int(r['display_order']))
            self.assertEqual(evidence_values(r)['source_url'],r['btm_evidence_url'] or None)

    def test_venue_categories_do_not_deduplicate_each_other(self):
        keys=[identity(f) for f in self.facts]
        self.assertEqual(len(keys),len(set(keys)))
        for vid in (23263,23554,23276):
            self.assertEqual(sum(f['venue_id']==vid for f in self.facts),2)

    def test_html_collision_blocks_and_diff_detects_same_count_update(self):
        source=[dict(venue_id=1,name='Ground',city='d&apos;Ascq',address=None,country='France'),
                dict(venue_id=2,name='Ground',city="d'Ascq",address=None,country='France')]
        with self.assertRaisesRegex(SafetyError,'collisions'):
            html_plan(source)
        diff=physical_diff({'fixtures':{1:'before'}},{'fixtures':{1:'after'}})
        self.assertEqual(diff['fixtures'],{'INSERT':[],'DELETE':[],'UPDATE':[1]})
        with self.assertRaisesRegex(SafetyError,'unrelated table'):
            physical_diff({'users':'before'},{'users':'after'})

    def test_changed_row_other_columns_cannot_be_swept_up(self):
        before={'fixtures':[dict(fixture_id=1570340,venue_id=23238,home_team_id=541)]}
        after={'fixtures':[dict(fixture_id=1570340,venue_id=23269,home_team_id=529)]}
        with self.assertRaisesRegex(SafetyError,'physical columns'):
            verify_changed_columns(before,after,{'fixture_updates':[dict(fixture_id=1570340,after=23269)]},24000)

    def hosted_fixture(self):
        teams={int(r['canonical_team_id']):dict(team_id=int(r['canonical_team_id']),team_name=r['canonical_team_name'],venue_id=int(r['canonical_venue_id']) if r['canonical_venue_id'] else 23567) for r in self.know}
        teams.update({5262:dict(team_id=5262,team_name='FC Cartagena'),5275:dict(team_id=5275,team_name='Real Murcia')})
        venues={int(r['canonical_venue_id']):dict(venue_id=int(r['canonical_venue_id']),name=r['canonical_venue_name'],city='City',address=None,country='Spain',provider_venue_id=int(r['provider_venue_id'])) for r in self.know if r['canonical_venue_id']}
        refs=[dict(venue_id=v['venue_id'],provider='api_football',provider_venue_id=v['provider_venue_id'],is_primary=True) for v in venues.values()]
        for f in self.facts:
            for field in ('team_a_id','team_b_id','team_id'):
                if f[field]: teams.setdefault(f[field],dict(team_id=f[field],team_name='Fixture team'))
            if f['venue_id']: venues.setdefault(f['venue_id'],dict(venue_id=f['venue_id'],name='Fixture ground',city='City',address=None,country='Spain'))
        venues[23567]=dict(venue_id=23567,name='Estadi Nacional',city='Andorra la Vella',address=None,country='Spain',provider_venue_id=2618)
        refs.append(dict(venue_id=23567,provider='api_football',provider_venue_id=2618,is_primary=True))
        andorra=[dict(fixture_id=fid,season=2026,league_id=141,venue_name='Estadi de la FAF',venue_city='Encamp',venue_id=23567) for fid in ANDORRA_FIXTURES]
        madrid=[dict(fixture_id=1570340,away_team_id=548,venue_id=23238)]+[dict(fixture_id=i,away_team_id=1,venue_id=23269) for i in range(18)]
        data={'teams':list(teams.values()),'venues':list(venues.values()),'venue_provider_refs':refs,'club_venues':[],
              'venue_guide_facts':[],'pre_match_spots':[],'pre_match_spot_evidence':[],'decision_facts':[],
              'andorra':andorra,'madrid':madrid}
        def fake_query(c,sql,**params):
            if 'FROM fixtures' in sql: return data['andorra' if '8157' in sql else 'madrid']
            table=sql.split('FROM ')[1].split()[0]
            return copy.deepcopy(data[table])
        return data,fake_query

    def test_final_reconciliation_includes_rivalry_teams_outside_know_without_country_column(self):
        data,fake=self.hosted_fixture()
        data['venues'].append(dict(venue_id=24000,**publication.NEW_VENUE))
        data['venues'].append(dict(venue_id=90000,name='Lille',city="Villeneuve d'Ascq",address=None,country='France'))
        for f in data['andorra']: f['venue_id']=24000
        for f in data['madrid']: f['venue_id']=23269
        for cv,r in enumerate(self.know,1):
            data['club_venues'].append(dict(club_venue_id=cv,team_id=int(r['canonical_team_id']),venue_id=int(r['canonical_venue_id']) if r['canonical_venue_id'] else 24000,relationship_type='HOME',status='CURRENT'))
            data['venue_guide_facts'].append(dict(club_venue_id=cv,**guide_values(r)))
            if r['entry_description']:
                data['venue_guide_facts'].append(dict(club_venue_id=cv,**guide_values(r,True)))
            if r['intentional_null']=='False':
                data['pre_match_spots'].append(dict(pre_match_spot_id=cv,club_venue_id=cv,**spot_values(r)))
                data['pre_match_spot_evidence'].append(dict(pre_match_spot_id=cv,**evidence_values(r)))
        data['decision_facts']=[dict(f,publication_status='PUBLISHED') for f in self.facts]
        with patch('backend.spain_know_decide_publication.query',side_effect=fake):
            result=audit(None,self.know,self.decide,self.facts,final=True)
        self.assertEqual(result['decide']['present'],51)
        self.assertTrue(all(not any(counts.values()) for counts in result['proposed_mutations'].values()))

    def test_hosted_dry_run_exact_plan_and_existing_home_is_reused(self):
        data,fake=self.hosted_fixture()
        data['club_venues']=[dict(team_id=531,venue_id=23262,club_venue_id=100,relationship_type='HOME',status='CURRENT')]
        with patch('backend.spain_know_decide_publication.query',side_effect=fake):
            plan=audit(None,self.know,self.decide,self.facts)
        self.assertEqual(len(plan['relationships_missing']),41)
        self.assertEqual(len(plan['guide_missing']),47)
        self.assertEqual(len(plan['spot_missing']),18)
        self.assertEqual({f['fixture_id'] for f in plan['fixture_updates']},set(ANDORRA_FIXTURES)|{1570340})
        self.assertEqual(plan['proposed_mutations']['teams'],{'INSERT':0,'UPDATE':0,'DELETE':0})
        self.assertEqual(plan['proposed_mutations']['venue_provider_refs'],{'INSERT':0,'UPDATE':0,'DELETE':0})

    def test_identity_drift_duplicate_home_and_fixture_expansion_block(self):
        for scenario in ('murcia','duplicate','fixture'):
            with self.subTest(scenario=scenario):
                data,fake=self.hosted_fixture()
                if scenario=='murcia': next(t for t in data['teams'] if t['team_id']==5275)['team_name']='Wrong club'
                elif scenario=='duplicate': data['club_venues']=[dict(team_id=531,venue_id=23262,club_venue_id=100,relationship_type='HOME')]*2
                else: data['andorra'].append(dict(data['andorra'][0],fixture_id=9999999))
                with patch('backend.spain_know_decide_publication.query',side_effect=fake),self.assertRaises(SafetyError):
                    audit(None,self.know,self.decide,self.facts)

    def test_cli_hash_confirmation_and_remote_guards_precede_database_access(self):
        base=['publisher','--database-url','postgresql://example.invalid/review',
              '--expected-script-sha256',sha(publication.__file__)]
        for flags in ([],['--write'],['--confirm-write'],['--write','--confirm-write'],
                      ['--allow-remote-audit','--expected-script-sha256','bad']):
            with self.subTest(flags=flags),patch('sys.argv',base+flags),patch.object(publication,'run') as run:
                with self.assertRaises(SafetyError): main()
                run.assert_not_called()
        with patch('sys.argv',base+['--allow-remote-audit']),patch.object(publication,'run',return_value={}) as run,contextlib.redirect_stdout(io.StringIO()):
            main()
            self.assertFalse(run.call_args.args[1])

    def test_missing_or_changed_artifact_fails_closed(self):
        with patch('backend.spain_know_decide_dry_run.EXPECTED_ARTIFACTS',{REMEDIATION:'wrong'}):
            with self.assertRaisesRegex(SafetyError,'ARTIFACT MISSING OR HASH MISMATCH'):
                approved()

    def test_all_eight_overlength_reviewed_rows_block_without_truncation(self):
        before=copy.deepcopy(self.know)
        limits=[dict(table_name='pre_match_spots',column_name='supporting_line',character_maximum_length=180)]
        found=schema_violations(self.know,self.facts,limits)
        self.assertEqual({v['subject']:v['length'] for v in found},{
            'Athletic Club':214,'Málaga CF':221,'RC Deportivo':213,'Cádiz CF':200,
            'CD Leganés':211,'CD Tenerife':202,'Granada CF':190,'Real Valladolid CF':194})
        self.assertEqual(self.know,before)

    def test_approved_255_capacity_fits_all_reviewed_text_exactly(self):
        from backend.models import PreMatchSpot
        before=copy.deepcopy(self.know)
        limits=[dict(table_name='pre_match_spots',column_name='supporting_line',character_maximum_length=255)]
        self.assertEqual(schema_violations(self.know,self.facts,limits),[])
        self.assertEqual(max(len(r['supporting_line']) for r in self.know),221)
        self.assertEqual(PreMatchSpot.__table__.c.supporting_line.type.length,255)
        self.assertEqual(self.know,before)


if __name__=='__main__':
    unittest.main()
