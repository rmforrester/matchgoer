"""Real API paths over disposable in-memory data; never connects to production."""
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch
import asyncio
import json
from types import SimpleNamespace
from urllib.parse import urlencode

class TestClient:
    """Minimal in-process ASGI GET transport; no sockets or optional HTTP client dependency."""
    def __init__(self, app): self.app=app
    def get(self, path, params=None):
        async def request():
            events=[]
            async def receive(): return {'type':'http.request','body':b'','more_body':False}
            async def send(event): events.append(event)
            await self.app(dict(type='http',asgi={'version':'3.0','spec_version':'2.4'},http_version='1.1',
                method='GET',scheme='http',path=path,raw_path=path.encode(),query_string=urlencode(params or {}).encode(),
                root_path='',headers=[(b'host',b'local.test')],client=('127.0.0.1',123),server=('local.test',80)),receive,send)
            start=next(e for e in events if e['type']=='http.response.start')
            body=b''.join(e.get('body',b'') for e in events if e['type']=='http.response.body')
            headers={k.decode().title():v.decode() for k,v in start.get('headers',[])}
            return SimpleNamespace(status_code=start['status'],text=body.decode(),headers=headers,json=lambda:json.loads(body))
        return asyncio.run(request())
    def close(self): pass
from sqlalchemy import create_engine, select, text, event, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import main
from models import Base, Fixture, Venue, Team
from backend.fixture_integrity import META, SCHEDULE, VENUES, reconcile_observations, set_schedule_evidence, identity


class IntegrityApiTests(unittest.TestCase):
    def setUp(self):
        self.aware_load=lambda target, _: setattr(target,'fixture_date',target.fixture_date.replace(tzinfo=timezone.utc)) if target.fixture_date.tzinfo is None else None
        event.listen(Fixture,'load',self.aware_load)
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        event.listen(self.engine, 'connect', lambda connection, _: connection.create_function('btrim',1,lambda s:s.strip() if s else s))
        event.listen(self.engine, 'connect', lambda connection, _: connection.create_function('num_nonnulls',-1,lambda *v:sum(x is not None for x in v)))
        event.listen(self.engine, 'connect', lambda connection, _: connection.create_function('char_length',1,lambda s:len(s) if s is not None else None))
        Base.metadata.create_all(self.engine,tables=[t for t in Base.metadata.sorted_tables if t.name!='account_conversion_handoffs']);META.create_all(self.engine)
        self.sessions=sessionmaker(bind=self.engine)
        self.patch=patch.object(main,'SessionLocal',self.sessions);self.patch.start()
        self.date_patch=patch.object(main,'utc_date_expression',lambda col:func.date(col));self.date_patch.start()
        self.social_id=0
        def assign_id(mapper,connection,target):
            self.social_id+=1;target.event_id=self.social_id
        self.assign_id=assign_id
        event.listen(main.SocialEvent,'before_insert',self.assign_id)

        self.client=TestClient(main.app)
        self.now=datetime.now(timezone.utc);self.future=self.now+timedelta(days=5);self.past=self.now-timedelta(days=5)
        with self.sessions() as db:
            db.add(Venue(venue_id=22805,name='Memorial',city='Charlotte',country='USA',latitude=35.218163,longitude=-80.828929))
            db.add_all([Team(team_id=10,team_name='Home'),Team(team_id=11,team_name='Away')])
            for i,status in enumerate(['NS','TBD','PST','CANC','SUSP','INT','ABD','AWD','WO'],1):
                db.add(Fixture(fixture_id=i,fixture_date=self.future,status=status,venue_id=22805,
                    home_team_id=10,home_team='Home',away_team_id=11,away_team='Away',league_id=489,league_name='USL League One',season=2026,country='USA'))
            db.add(Fixture(fixture_id=99,fixture_date=self.past,status='FT',venue_id=22805,home_team_id=10,
                home_team='Home',away_team_id=11,away_team='Away',league_id=489,league_name='USL League One',season=2026,country='USA'))
            db.commit()

    def tearDown(self):
        self.client.close();self.patch.stop();self.engine.dispose()
        event.remove(Fixture,'load',self.aware_load)
        self.date_patch.stop();event.remove(main.SocialEvent,'before_insert',self.assign_id)

    def nearby(self,**extra):
        r=self.client.get('/nearby',params=dict(latitude=35.218163,longitude=-80.828929,radius=1,limit=500,**extra))
        self.assertEqual(r.status_code,200,r.text);return r

    def test_discovery_status_filter_before_counts_and_pagination(self):
        r=self.nearby(start_date=self.future.date().isoformat(),end_date=self.future.date().isoformat())
        self.assertEqual({x['fixture_id'] for x in r.json()},{1,2});self.assertEqual(r.headers['X-Total-Matches'],'2')

    def test_future_fixture_list_and_venue_lookup_exclude_inactive(self):
        for path in ['/fixtures','/venues/22805/fixtures']:
            params={'date':self.future.date().isoformat()} if path=='/fixtures' else {'around_date':self.future.date().isoformat(),'days':0}
            r=self.client.get(path,params=params);self.assertEqual(r.status_code,200,r.text)
            self.assertEqual({x['fixture_id'] for x in r.json()},{1,2})

    def test_history_and_inactive_detail_not_deleted_or_hidden(self):
        r=self.client.get('/fixtures',params={'date':self.past.date().isoformat()})
        self.assertEqual([x['fixture_id'] for x in r.json()],[99])
        r=self.client.get('/fixtures/3/social');self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['fixture']['status'],'PST')
        self.assertEqual([x['fixture_id'] for x in self.nearby(date=self.past.date().isoformat()).json()],[99])

    def test_country_label_cannot_hide_Peru_coordinates_and_pin_restores_after_repair(self):
        with self.engine.begin() as c:
            c.execute(Venue.__table__.update().where(Venue.venue_id==22805).values(country='Spain',latitude=-5.437638,longitude=-80.738506))
        r=self.client.get('/nearby',params=dict(latitude=-5.437638,longitude=-80.738506,radius=1,date=self.future.date().isoformat()))
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json(),[])
        self.assertEqual(r.headers['X-Total-Matches'],'0')
        r=self.client.get('/fixtures/1/social');self.assertIsNone(r.json()['fixture']['venue_id'])
        self.assertTrue(r.json()['fixture']['integrity']['venue_geography']['hold'])
        with self.engine.begin() as c:
            c.execute(Venue.__table__.update().where(Venue.venue_id==22805).values(country='USA',latitude=35.218163,longitude=-80.828929))
        self.assertIn(1,{x['fixture_id'] for x in self.nearby(date=self.future.date().isoformat()).json()})

    def test_legacy_zero_point_is_excluded_before_counting_and_pagination(self):
        with self.engine.begin() as c:
            c.execute(Venue.__table__.update().where(Venue.venue_id==22805).values(country='USA',latitude=0,longitude=0))
        for offset in [0,1]:
            r=self.client.get('/nearby',params=dict(latitude=0,longitude=0,radius=1,date=self.future.date().isoformat(),limit=1,offset=offset))
            self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json(),[]);self.assertEqual(r.headers['X-Total-Matches'],'0')
        with self.engine.connect() as c:self.assertEqual(c.execute(select(func.count()).select_from(Fixture)).scalar_one(),10)

    def create_decision(self,fid,**changes):
        with self.engine.begin() as c:
            raw=dict(c.execute(Fixture.__table__.select().where(Fixture.fixture_id==fid)).mappings().one())
            new=dict(raw,fixture_date=raw['fixture_date'].isoformat())
            reconcile_observations(c,{fid:[new]},now=self.now)
            if changes:c.execute(SCHEDULE.update().where(SCHEDULE.c.fixture_id==fid).values(**changes))

    def test_rescheduled_effective_date_filters_before_query_not_after(self):
        moved=self.future+timedelta(days=20)
        self.create_decision(1,effective_kickoff=moved,state='CONFIRMED_RESCHEDULED')
        self.assertNotIn(1,{x['fixture_id'] for x in self.nearby(date=self.future.date().isoformat()).json()})
        self.assertEqual([x['fixture_id'] for x in self.nearby(date=moved.date().isoformat()).json()],[1])
        self.assertEqual([x['fixture_id'] for x in self.client.get('/fixtures',params={'date':moved.date().isoformat()}).json()],[1])

    def test_superseded_and_schedule_holds_hide_only_target_and_are_reversible(self):
        self.create_decision(1)
        self.create_decision(2,superseded_by=1)
        with self.engine.begin() as c:c.execute(SCHEDULE.update().where(SCHEDULE.c.fixture_id==1).values(schedule_hold=True))
        self.assertEqual(self.nearby(date=self.future.date().isoformat()).json(),[])
        with self.engine.begin() as c:c.execute(SCHEDULE.update().where(SCHEDULE.c.fixture_id==1).values(schedule_hold=False))
        self.assertEqual([x['fixture_id'] for x in self.nearby(date=self.future.date().isoformat()).json()],[1])

    def test_disputed_venue_hidden_but_fixture_detail_and_uncertainty_remain(self):
        with self.engine.begin() as c:
            row=dict(c.execute(Fixture.__table__.select().where(Fixture.fixture_id==1)).mappings().one())
            c.execute(VENUES.insert().values(fixture_id=1,identity=identity(row),state='DISPUTED',provider_venue={},revision=1))
        self.assertNotIn(1,{x['fixture_id'] for x in self.nearby(date=self.future.date().isoformat()).json()})
        r=self.client.get('/fixtures/1/social');self.assertEqual(r.status_code,200,r.text)
        self.assertIsNone(r.json()['fixture']['venue_id']);self.assertIsNone(r.json()['fixture']['venue_name'])
        self.assertEqual(r.json()['fixture']['integrity']['venue_state'],'DISPUTED')
        with self.engine.begin() as c:
            c.execute(VENUES.update().where(VENUES.c.fixture_id==1).values(state='UNRESOLVED'))
        self.assertNotIn(1,{x['fixture_id'] for x in self.nearby(date=self.future.date().isoformat()).json()})
        r=self.client.get('/fixtures/1/social')
        self.assertIsNone(r.json()['fixture']['venue_id'])
        self.assertEqual(r.json()['fixture']['integrity']['venue_state'],'UNRESOLVED')


if __name__=='__main__':unittest.main()
