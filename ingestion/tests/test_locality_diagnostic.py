"""Offline diagnostic persistence/presentation; no external transport."""
import copy,json,unittest
from datetime import datetime,timezone
from types import SimpleNamespace as NS
from unittest.mock import patch
from sqlalchemy import select,text
from refresh_fixture_states import resolve_venue
from ingestion.discovery_venues import resolve_event_venue
from backend.fixture_integrity import RUNS
from backend.fixture_integrity_email_monitor import material,technical_summary,message
from backend.fixture_integrity_email_presentation import render
from test_automatic_venue_reconciliation import NightlyVenueIntegrationTests,item
from ingestion.pipeline import plan_fixture_discovery,run_fixture_discovery
from ingestion.global_discovery import DiscoveryScope
from test_fixture_discovery import Client

class DiagnosticWriterTests(NightlyVenueIntegrationTests):
    def test_diagnostic_survives_real_run_receipt_without_changing_disputed_reason(self):
        with self.engine.begin()as c:c.execute(text('UPDATE fixtures SET venue_id=23100'))
        with patch('requests.sessions.Session.request',side_effect=AssertionError('external request')):
            code,result=self.run_nightly(item(dict(id=907,name='San Siro',city='Wrong City')))
        self.assertTrue(result['commit_confirmed'])
        with self.engine.connect()as c:
            receipt=c.execute(select(RUNS.c.receipt)).scalar_one()
        detail=receipt['lifecycle_decisions'][0]['venue_diagnostic']
        self.assertEqual(detail['diagnostic_subreason'],'VENUE_LOCALITY_CONFLICT')
        self.assertEqual((detail['bound_ground_locality'],detail['observed_provider_locality']),('Milano','Wrong City'))
        self.assertFalse(detail['provider_venue_identity_missing'])
        self.assertEqual(receipt['report']['venue_reconciliation']['unresolved_or_conflicting'][0]['venue_diagnostic'],detail)
        self.assertIn('VENUE_DISPUTED',{x['reason']for x in receipt['exception_report']['exceptions']})
        self.assertEqual(result['provider_requests'],1)
    def test_missing_identity_guard_retains_both_localities_and_missing_flag(self):
        from test_stale_venue_locality import F,G,REFS,NAMES,item as versailles
        diagnostic={};self.assertEqual(resolve_venue(NS(**F),versailles(),G,REFS,NAMES,diagnostic=diagnostic),(23298,'DISPUTED'))
        self.assertTrue(diagnostic['provider_venue_identity_missing'])
        self.assertEqual((diagnostic['bound_ground_locality'],diagnostic['observed_provider_locality']),('Paris','Saint-Germain-en-Laye'))
    def test_discovery_receipt_preserves_diagnostic_without_new_requests(self):
        # This test uses the existing synthetic provider and actual discovery planner.
        p=item(dict(id=907,name='San Siro',city='Wrong City'));p['fixture']['id']=1639885
        p['fixture']['date']='2026-12-03T17:00:00+00:00'
        start=datetime(2026,12,1,tzinfo=timezone.utc);end=datetime(2026,12,9,tzinfo=timezone.utc)
        scope=DiscoveryScope('Italy',137,'Coppa Italia',2026,'2026/27')
        with self.engine.connect()as c:plan=plan_fixture_discovery(c,{(137,2026):[p]},start,end,approved_scopes=(scope,))
        self.assertIsNone(plan['rows'][0]['venue_id'])
        detail=plan['locality_conflicts'][0];self.assertEqual(detail['diagnostic_subreason'],'VENUE_LOCALITY_CONFLICT')
        self.assertEqual(detail['conflicting_ground_locality'],'Milano')
        self.assertIsNone(detail['bound_ground_locality']) # New event: no invented old binding.
        client=Client();client.fixtures_between=lambda *args:[p]
        with patch('requests.sessions.Session.request',side_effect=AssertionError('external request')):
            result=run_fixture_discovery(self.engine,client,start.date(),write=False,approved_scopes=(scope,))
        self.assertEqual(result['locality_conflicts'],plan['locality_conflicts'])

class DiagnosticEmailTests(unittest.TestCase):
    now=datetime(2026,11,20,18,tzinfo=timezone.utc)
    def data(self,n=105):
        detail=dict(diagnostic_subreason='VENUE_LOCALITY_CONFLICT',bound_ground_locality='Kristiansund',observed_provider_locality='Kristiansand',provider_venue_identity_missing=False)
        rows={i:dict(fixture_id=i,fixture_id_original=i,kickoff='2026-11-22T16:00:00+00:00',status='NS',country='Norway',competition='Eliteserien',canonical_ground_id=23175,venue_country='Norway',latitude=63.124987,longitude=7.719229,policy_state='DISPUTED',home_team='Home',away_team='Away')for i in range(1,n+1)}
        receipt=dict(exception_report=dict(exceptions=[dict(fixture_id=i,reason='VENUE_DISPUTED')for i in rows]),lifecycle_decisions=[dict(fixture_id=i,venue_diagnostic=detail)for i in rows])
        return receipt,rows
    def test_all_conflicts_retained_outside_first100_and_email_only_small_sample(self):
        receipt,rows=self.data();s=material(receipt,self.now,rows);technical=technical_summary({'passed':True},s,self.now)
        self.assertEqual(len(technical['current_exceptions']),100);self.assertEqual(len(technical['locality_conflicts']),105)
        self.assertEqual(technical['locality_conflict_count'],105)
        self.assertEqual({x['policy_reason']for x in technical['locality_conflicts']},{'VENUE_DISPUTED'})
        email=render({'passed':True},s,self.now);self.assertIn('Venue locality conflicts: 105',email['text'])
        self.assertEqual(email['text'].count('→ observed Kristiansand'),3)
        self.assertIn('[AMBER]',email['subject'])
    def test_diagnostics_do_not_change_thresholds_counts_coverage_or_delivery_decision(self):
        receipt,rows=self.data();before=copy.deepcopy(receipt);before.pop('lifecycle_decisions')
        a=material(before,self.now,rows);b=material(receipt,self.now,rows)
        for k in a:
            if not k.startswith('locality_'):self.assertEqual(a[k],b[k],k)
        for health in ({'passed':True},{'passed':False}):
            self.assertEqual(message(health,a,self.now)['subject'],message(health,b,self.now)['subject'])
        self.assertEqual(b['critical_count'],0);self.assertEqual(b['warning_count'],105)
    def test_resolved_inactive_and_verified_cases_not_reported_as_current_conflicts(self):
        receipt,rows=self.data(3);rows[1]['policy_state']='OFFICIAL_VERIFIED';rows[2]['status']='CANC';rows[3]['kickoff']='2026-11-01T16:00:00+00:00'
        s=material(receipt,self.now,rows);self.assertEqual(s['locality_conflicts'],[])
    def test_discovery_only_diagnostics_not_lost_when_absent_from_lifecycle(self):
        receipt,rows=self.data(1);d=receipt.pop('lifecycle_decisions')[0];detail=dict(d['venue_diagnostic'],fixture_id=1)
        receipt['report']={'global_fixture_discovery':{'groups':[{'locality_conflicts':[detail]}]}}
        self.assertEqual(material(receipt,self.now,rows)['locality_conflict_count'],1)

if __name__=='__main__':unittest.main(verbosity=2)
