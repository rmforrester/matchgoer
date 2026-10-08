import copy
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

from official_channels import HTTP_TICKETING, INFORMATION_STATE, official_channels, ticket_destination_allowed
from fixture_tickets import resolve_fixture_ticket_presentation
from models import Team, Fixture
ONLINE="VERIFIED_OFFICIAL_TICKET_NAVIGATION_SOURCE"


def source(tid=1, url='https://club.test/tickets', info=False):
    return NS(team_id=tid, club_venue_id=None, source_url=url, source_domain='club.test',
              source_state=INFORMATION_STATE if info else ONLINE,
              ticketing_model='OFFICIAL_INFORMATION' if info else 'ONLINE_NAVIGATION',
              operational_status='ACTIVE', source_role='PRIMARY', source_label=None)


class ContractTests(unittest.TestCase):
    def presentation(self, src):
        return resolve_fixture_ticket_presentation(NS(home_team_id=src.team_id, venue_id=None), [], [], [src])

    def test_online_and_information_https_labels(self):
        self.assertEqual(self.presentation(source())['action']['label'], 'Buy tickets')
        self.assertEqual(self.presentation(source(info=True))['action']['label'], 'Ticket info')

    def test_all_exact_http_exceptions_with_wrong_owner_type_and_url_rejected(self):
        self.assertEqual(len(HTTP_TICKETING), 10)
        for tid, model, url in HTTP_TICKETING:
            src = source(tid, url, model == 'OFFICIAL_INFORMATION')
            self.assertEqual(self.presentation(src)['action']['url'], url)
            for changes in ({'team_id':999999}, {'source_url':url+'?other=1'}, {'ticketing_model':'ONLINE_DIRECT'}, {'source_state':'SOURCE_NEEDS_REVIEW'}, {'club_venue_id':123}):
                changed = copy.copy(src)
                for k,v in changes.items(): setattr(changed,k,v)
                self.assertFalse(ticket_destination_allowed(changed))

    def test_no_url_unapproved_http_and_nonestablished_have_no_destination(self):
        for src in (source(url=None),source(url='http://unapproved.test/'),source(url='javascript:alert(1)'),source(url='https://user:password@club.test/')):
            self.assertIsNone(self.presentation(src)['action'])
        src=source();src.source_state='NO_SAFE_TICKET_SOURCE';src.ticketing_model='NONE'
        self.assertIsNone(self.presentation(src)['action'])

    def test_protected_blank_guidance_unchanged(self):
        src=source(url=None);src.source_state='PAY_AT_GATE_OR_OFFLINE_SOURCE';src.ticketing_model='OFFLINE';src.source_label='Tickets from the box office'
        result=self.presentation(src)
        self.assertIsNone(result['action']);self.assertEqual(result['guidance']['message'],src.source_label)

    def test_optional_digital_serialization_and_unsafe_values(self):
        self.assertTrue(Team.__table__.c.official_homepage_url.nullable)
        self.assertTrue(Team.__table__.c.official_instagram_url.nullable)
        for home,ig in [(None,None),('https://club.test/',None),(None,'https://www.instagram.com/club/'),('https://club.test/','https://www.instagram.com/club/')]:
            team=Team(team_id=1,official_homepage_url=home,official_instagram_url=ig)
            result=official_channels(team)
            self.assertEqual(result,dict(official_homepage_url=home,official_instagram_url=ig))
        bad=Team(official_homepage_url='javascript:alert(1)',official_instagram_url='https://www.instagram.com/p/abc/')
        self.assertEqual(official_channels(bad),dict(official_homepage_url=None,official_instagram_url=None))

    def test_fixture_api_serializes_exact_home_team_links_with_mocked_session(self):
        import main
        f=Fixture(fixture_id=1,fixture_date=datetime.now(timezone.utc),home_team_id=99,home_team='Home',away_team='Away',status='NS')
        team=Team(team_id=99,official_homepage_url='https://home.test/',official_instagram_url='https://www.instagram.com/home/')
        db=MagicMock()
        def query(entity,*args):
            q=MagicMock();q.options.return_value=q;q.filter.return_value=q;q.order_by.return_value=q
            q.first.return_value=f if entity is Fixture else (team if entity is Team else None)
            q.all.return_value=[];q.scalar.return_value=0;q.one.return_value=(None,None,0)
            return q
        db.query.side_effect=query
        with patch.object(main,'SessionLocal',return_value=db),patch.object(main,'fixture_decision_payload',return_value={}):
            result=main.get_fixture_social(1,None)
        self.assertEqual(result['official_channels'],official_channels(team))
