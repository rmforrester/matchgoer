import unittest,copy,json,sys,importlib.util
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
PROFILES=json.loads((ROOT/'ops/production_sources.json').read_text())['services']
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
mon=load('live_monitor',ROOT/PROFILES['monitor']['files']['backend/fixture_integrity_email_monitor.py']['source'])
pres=load('live_presentation',ROOT/PROFILES['monitor']['files']['backend/fixture_integrity_email_presentation.py']['source'])
old=load('prior_monitor',ROOT/PROFILES['writer']['files']['backend/fixture_integrity_email_monitor.py']['source'])
NOW=datetime(2026,11,21,18,tzinfo=timezone.utc)
def row(**kw):
 r=dict(fixture_id=1,kickoff='2026-11-24T15:00:00+00:00',status='NS',superseded_by=None,canonical_ground_id=9,ground_locality='Goteborg',canonical_names=['Arena'],approved_localities=[],policy_state='DISPUTED',latitude=57,longitude=12,venue_country='Sweden',country='Sweden',home_team='Home',away_team='Away',league_id=1,season=2026,home_team_id=1,away_team_id=2,observed_provider_venue=dict(id=50,name='Arena',city='Gothenburg'));r.update(kw);return r
def detail(i=1):return dict(fixture_id=i,policy_reason='VENUE_DISPUTED',diagnostic_subreason='VENUE_LOCALITY_CONFLICT',bound_ground_id=9,bound_ground_locality='Goteborg',provider_venue_id=50,provider_venue_name='Arena',observed_provider_locality='Gothenburg',provider_venue_identity_missing=False)
def receipt(cases):return dict(report=dict(venue_reconciliation=dict(unresolved_or_conflicting=[dict(fixture_id=x['fixture_id'],venue_diagnostic=x)for x in cases])),exception_report=dict(exceptions=[]))
class Semantics(unittest.TestCase):
 def test_verified_language_equivalence(self):self.assertEqual(mon.diagnostic_review(detail(),row(approved_localities=['Goteborg','Gothenburg']),NOW),'VERIFIED_SCOPED_EQUIVALENT')
 def test_unapproved_variation_still_requires_review(self):self.assertEqual(mon.diagnostic_review(detail(),row(),NOW),'MATERIAL_LOCALITY_REVIEW')
 def test_incomplete_unbound(self):self.assertEqual(mon.diagnostic_review(detail(),row(canonical_ground_id=None,ground_locality=None,observed_provider_venue={}),NOW),'INCOMPLETE_COMPARISON')
 def test_material_difference(self):self.assertEqual(mon.diagnostic_review(detail(),row(ground_locality='Paris',observed_provider_venue=dict(city='Versailles')),NOW),'MATERIAL_LOCALITY_REVIEW')
 def test_identity_name_separate(self):self.assertEqual(mon.diagnostic_review(detail(),row(observed_provider_venue=dict(id=50,name='Other Stadium',city='Goteborg')),NOW),'PROVIDER_CANONICAL_IDENTITY_REVIEW')
 def test_reference_identity_separate_even_if_locality_approved(self):self.assertEqual(mon.diagnostic_review(detail(),row(observed_provider_ground_id=10,approved_localities=['Goteborg','Gothenburg']),NOW),'PROVIDER_CANONICAL_IDENTITY_REVIEW')
 def test_verified_policy_resolved(self):
  r=row(policy_state='OFFICIAL_VERIFIED',policy_venue_id=9);r['policy_identity']={k:r[k]for k in('fixture_id','league_id','season','home_team_id','away_team_id')};self.assertEqual(mon.diagnostic_review(detail(),r,NOW),'RESOLVED_CURRENT_POLICY')
 def test_wrong_verified_identity_not_hidden(self):self.assertNotEqual(mon.diagnostic_review(detail(),row(policy_state='OFFICIAL_VERIFIED',policy_venue_id=9,policy_identity={}),NOW),'RESOLVED_CURRENT_POLICY')
 def test_provider_assigned_not_sufficient_to_suppress(self):self.assertEqual(mon.diagnostic_review(detail(),row(policy_state='PROVIDER_ASSIGNED'),NOW),'MATERIAL_LOCALITY_REVIEW')
 def test_elapsed_excluded(self):self.assertEqual(mon.diagnostic_review(detail(),row(kickoff='2026-11-20T00:00:00+00:00'),NOW),'INACTIVE_OR_UNAVAILABLE')
 def test_missing_provider_identity_does_not_invent_identity_conflict(self):self.assertEqual(mon.diagnostic_review(detail(),row(observed_provider_venue=dict(id=0,city='Versailles'),ground_locality='Paris'),NOW),'MATERIAL_LOCALITY_REVIEW')
 def test_raw_diagnostics_unchanged(self):
  raw=receipt([detail()]);original=copy.deepcopy(raw);s=mon.material(raw,NOW,{1:row(approved_localities=['Goteborg','Gothenburg'])});self.assertEqual(raw,original);self.assertEqual(s['locality_conflicts'][0],detail());self.assertEqual(s['raw_locality_diagnostic_count'],1);self.assertEqual(s['locality_conflict_count'],0)
 def test_detail_uncapped_and_both_email_lists_max_three(self):
  cases=[detail(i)for i in range(1,106)];current={i:row(fixture_id=i,ground_locality='Paris',observed_provider_venue=dict(name='Other Stadium'if i>100 else'Arena',city='Versailles'))for i in range(1,106)};s=mon.material(receipt(cases),NOW,current);s['current_facts_rechecked']=True;s['run_id']='test';d=mon.technical_summary(dict(passed=True),s,NOW);self.assertEqual(len(d['locality_conflicts']),105);self.assertEqual(len(d['provider_identity_conflicts']),5)
  email=pres.render(dict(passed=True),s,NOW)['text'];self.assertIn('Venue locality conflicts requiring review: 100',email);self.assertIn('Provider/canonical identity conflicts requiring review: 5',email);self.assertIn('101 ',email);self.assertNotIn('104 ',email)
 def test_zero_concise(self):
  email=pres.render(dict(passed=True),dict(current_facts_rechecked=True),NOW)['text'];self.assertIn('Venue locality conflicts requiring review: 0',email);self.assertIn('Provider/canonical identity conflicts requiring review: 0',email)
 def test_status_warning_counts_coverage_and_requests_unchanged(self):
  raw=receipt([detail()]);raw['exception_report']['exceptions']=[dict(fixture_id=1,reason='VENUE_DISPUTED')];a=old.material(raw,NOW,{1:row()});b=mon.material(raw,NOW,{1:row()})
  for k in ['urgent','critical_count','warning_count','groups','excluded','deferred_scopes','coverage_entries']:self.assertEqual(a[k],b[k])
  for coverage in [dict(status='CHECKED',primary_period='FULL_SEASON',totals=dict(Worldwide=dict(FULL_SEASON=dict(visible=1,eligible=1,missing=0)))),dict()]:
   a['league_coverage']=b['league_coverage']=coverage
   self.assertEqual(pres.render(dict(passed=True),a,NOW)['subject'],pres.render(dict(passed=True),b,NOW)['subject'])
 def test_green_stays_green(self):
  s=dict(current_facts_rechecked=True,league_coverage=dict(status='CHECKED',primary_period='FULL_SEASON',totals=dict(Worldwide=dict(FULL_SEASON=dict(visible=1,eligible=1,missing=0)))))
  self.assertIn('[GREEN]',pres.render(dict(passed=True),s,NOW)['subject'])
if __name__=='__main__':unittest.main(verbosity=2)
