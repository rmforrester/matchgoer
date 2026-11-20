"""Missing identity must not confirm a conflicting retained locality."""
import copy,json,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from refresh_fixture_states import resolve_venue
from backend.fixture_integrity import identity

S=json.loads(Path('/work/versailles-release/../versailles-investigation/production-readonly-evidence.json').read_text())
G=S['grounds'];REFS=S['provider_refs'];NAMES=S['aliases']
F=next(f for f in S['fixtures']if f['fixture_id']==1574794)
def item(f=F,city='Saint-Germain-en-Laye',pid=None,name=None):
 return dict(fixture=dict(id=f['fixture_id'],date=f['fixture_date'],status=dict(short=f['status']),venue=dict(id=pid,name=name,city=city)),league=dict(id=f['league_id'],season=f['season'],country=f['country'],round=f['round']),teams=dict(home=dict(id=f['home_team_id'],name=f['home_team']),away=dict(id=f['away_team_id'],name=f['away_team'])),goals=dict(home=None,away=None))
class StaleLocality(unittest.TestCase):
 def resolve(self,f=F,raw=None,context=None,grounds=G):return resolve_venue(NS(**f),raw or item(f),grounds,REFS,NAMES,context)
 def test_missing_identity_conflicting_locality_disputes_existing_binding(self):
  for pid in (None,0):self.assertEqual(self.resolve(raw=item(pid=pid)),(23298,'DISPUTED'))
 def test_locality_cannot_select_a_replacement(self):self.assertEqual(self.resolve(f={**F,'venue_id':None}),(None,'MISSING'))
 def test_missing_locality_retains_binding(self):self.assertEqual(self.resolve(raw=item(city=None)),(23298,'MISSING'))
 def test_matching_locality_retains_binding(self):self.assertEqual(self.resolve(raw=item(city='Paris')),(23298,'MISSING'))
 def test_approved_scoped_locality_remains_compatible(self):
  self.assertEqual(self.resolve(context=dict(venue_reviews=[dict(venue_id=23298,localities=['Paris','Saint-Germain-en-Laye'],source='https://example.test/approved')])),(23298,'MISSING'))
 def test_both_verified_fixture_policies_outrank_missing_stale_evidence(self):
  for fid in (1574794,1574811):
   f=next(f for f in S['fixtures']if f['fixture_id']==fid);p=dict(identity=identity(f),state='OFFICIAL_VERIFIED',venue_id=27840)
   self.assertEqual(self.resolve(f,item(f),dict(fixture_verifications={fid:p})),(27840,'MATCHED_VERIFIED_OVERRIDE'))
 def test_no_matching_policy_for_reversed_identity(self):
  p=dict(identity=identity(F),state='OFFICIAL_VERIFIED',venue_id=27840);f={**F,'home_team_id':F['away_team_id'],'away_team_id':F['home_team_id']}
  with self.assertRaisesRegex(ValueError,'VENUE_VERIFICATION_IDENTITY_CONFLICT'):self.resolve(f,item(f),dict(fixture_verifications={F['fixture_id']:p}))
 def test_paris_fc_stays_at_jean_bouin(self):
  f={**F,'fixture_id':1552825,'home_team_id':114};self.assertEqual(self.resolve(f,item(f,city='Paris')),(23298,'MISSING'))
 def test_nonzero_provider_venue_still_resolves(self):self.assertEqual(self.resolve(raw=item(city='Paris',pid=18861,name='Stade Jean Bouin')),(23298,'MATCHED'))
 def test_verified_neutral_or_temporary_fixture_remains_protected(self):
  p=dict(identity=identity(F),state='OFFICIAL_VERIFIED',venue_id=27840)
  self.assertEqual(self.resolve(context=dict(fixture_verifications={1574794:p})),(27840,'MATCHED_VERIFIED_OVERRIDE'))
 def test_missing_existing_city_does_not_invent_a_conflict(self):
  grounds=copy.deepcopy(G)
  for g in grounds:
   if g['venue_id']==23298:g['city']=None
  self.assertEqual(self.resolve(grounds=grounds),(23298,'MISSING'))
if __name__=='__main__':unittest.main(verbosity=2)
