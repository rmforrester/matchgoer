from pathlib import Path
import os,sys,subprocess,json
WT=Path('/source');OUT=Path('/output');port=5432
assert os.environ.get('DATABASE_URL')=='postgresql://terraces_ci:synthetic_ci_only@127.0.0.1:5432/terraces_ci'
assert not os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
assert not os.environ.get('TERRACES_MODERATOR_USER_ID')
assert not os.environ.get('TERRACES_BACKEND_ENABLED')
sys.path[:0]=['/validation',str(WT),str(WT/'backend')]
os.environ['PYTHONPATH']='/validation'+os.pathsep+str(WT)+os.pathsep+str(WT/'backend')
from database import engine
from models import Base,Venue,Team,Fixture,ClubVenue
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime,timezone
assert engine.url.host=='127.0.0.1' and engine.url.port==port
with engine.begin() as cleanup:
 for name in ('terrace_attendance_removed','terrace_photo_event','terrace_photo_guard'):
  cleanup.execute(text(f'DROP FUNCTION IF EXISTS {name}() CASCADE'))
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine,tables=[t for t in Base.metadata.sorted_tables if t.name not in {'terrace_photos','terrace_photo_events'}])
import psycopg2
connection=psycopg2.connect(os.environ['DATABASE_URL']);connection.autocommit=True
with connection.cursor() as cursor:cursor.execute((WT/'backend/migrations/20261013_terrace_photo_foundation.sql').read_text(encoding='utf-8'))
with connection.cursor() as cursor:
 cursor.execute((WT/'backend/migrations/20261013_terrace_photo_b1.sql').read_text())
 cursor.execute((WT/'backend/migrations/20261013_terrace_photo_b1_rollback.sql').read_text())
 cursor.execute((WT/'backend/migrations/20261013_terrace_photo_b1.sql').read_text())
connection.close()
with engine.begin() as c:
 c.execute(text('CREATE UNIQUE INDEX uq_user_profiles_username_ci ON user_profiles (lower(username)) WHERE username IS NOT NULL'))
 c.execute(text("ALTER TABLE user_profiles ADD CONSTRAINT display_name_check CHECK (char_length(btrim(display_name)) BETWEEN 2 AND 40)"))
with Session(engine) as db:
 v=Venue(name='Synthetic ground',city='Test',country='Test',latitude=51,longitude=-1);db.add(v);db.flush()
 db.add_all([Team(team_id=900000001,team_name='Synthetic home',venue_id=v.venue_id),Team(team_id=900000002,team_name='Synthetic away')]);db.flush()
 db.add(ClubVenue(team_id=900000001,venue_id=v.venue_id,relationship_type='HOME',status='CURRENT'))
 db.add(Fixture(fixture_id=900000001,home_team_id=900000001,away_team_id=900000002,home_team='Synthetic home',away_team='Synthetic away',venue_id=v.venue_id,fixture_date=datetime.now(timezone.utc),country='Test',league_name='Synthetic'));db.flush();baseline_venue_id=v.venue_id;db.commit()
engine.dispose()
modules=['test_venue_timezone','test_fixture_tickets','test_football_footprint','test_profile_ground_count','test_analytics_audience','test_personal_ratings','test_terraces_apple_hdr','test_terraces_request_diagnostic','test_terraces_image_errors','test_terraces_images','test_terraces_b1','test_terraces_storage','test_terraces_cleanup','test_terraces_api','test_terraces','test_account_claim','test_account_ux','test_identity','test_social_permissions','test_venue_visits']
modules=[f'backend.tests.{name}' for name in modules if (WT/'backend/tests'/f'{name}.py').exists()]
modules += ['multi_fixture_journey']
r=subprocess.run([sys.executable,'-m','unittest','-v',*modules],cwd=WT,env=os.environ.copy(),capture_output=True,text=True,encoding='utf-8')
(OUT/'backend-tests.txt').write_text(r.stdout+r.stderr,encoding='utf-8');print((r.stdout+r.stderr)[-5500:]);test_returncode=r.returncode
connection=psycopg2.connect(os.environ['DATABASE_URL']);connection.autocommit=True
with connection.cursor() as cursor:
 cursor.execute((WT/'backend/migrations/20261013_terrace_photo_foundation_rollback.sql').read_text(encoding='utf-8'))
 cursor.execute("SELECT to_regclass('terrace_photos'),to_regclass('venue_visits')");a,b=cursor.fetchone();assert a is None and b is not None
 cursor.execute((WT/'backend/migrations/20261013_terrace_photo_foundation.sql').read_text(encoding='utf-8'))
connection.close()
(OUT/'migration-tests.txt').write_text('B1 forward/empty rollback/reapply PASS; foundation rollback preserving attendance/reapply PASS; local PostgreSQL only.\n',encoding='utf-8')
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4
from hashlib import sha256
from models import User,UserIdentity,VenueVisit,TerracePhoto
from terraces_images import SanitisedPhoto,ImageVariant
from terraces import reserve_photo,CONSENT_VERSION
from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError
now=datetime.now(timezone.utc)
with Session(engine) as db:
 owner=User(account_status='registered',is_anonymous=False);db.add(owner);db.flush();owner_id=owner.user_id
 db.add(UserIdentity(user_id=owner_id,issuer='https://synthetic.test/auth/v1',subject=str(owner_id),email_verified_at=now))
 visits=[VenueVisit(user_id=owner_id,venue_id=baseline_venue_id,source='manual') for _ in range(3)];db.add_all(visits);db.flush();visit_ids=[x.visit_id for x in visits];db.commit()
# Isolated synthetic CI owner only; never a production permission grant.
os.environ['TERRACES_UPLOAD_USER_IDS']=str(owner_id)
provider=type('Verified',(),{'issuer':'https://synthetic.test/auth/v1','subject':str(owner_id)})()
outcomes=[]
for mode,visit_id in zip(('helper','database','service'),visit_ids):
 def attempt(index):
  with Session(engine) as db:
   try:
    if mode in ('helper','service'):
     photo=SanitisedPhoto(sha256(str(index).encode()).hexdigest(),1,ImageVariant(b'synthetic',1,1),ImageVariant(b'synthetic',1,1))
     if mode=='service':
      from backend.tests.test_terraces_b1 import FakeStorage
      import terraces_service
      terraces_service.submit(db,FakeStorage(),'Bearer synthetic',visit_id,photo,{'consent_version':CONSENT_VERSION,'public_consent':True,'rights_acknowledged':True},str(uuid4()))
     else:
      reserve_photo(db,'Bearer synthetic',visit_id=visit_id,photo=photo,submission_key=str(uuid4()),consent_version=CONSENT_VERSION,public_consent=True,rights_acknowledged=True)
    else:
     key=uuid4().hex
     db.add(TerracePhoto(owner_user_id=owner_id,visit_id=visit_id,venue_id=baseline_venue_id,source_sha256=sha256(str(index).encode()).hexdigest(),original_bytes=1,display_key=f'photos/{key}/display.jpg',thumbnail_key=f'photos/{key}/thumbnail.jpg',width=1,height=1,thumbnail_width=1,thumbnail_height=1,content_type='image/jpeg',status='PENDING',submission_key=str(uuid4()),consent_version=CONSENT_VERSION))
    db.commit();return 'saved'
   except (HTTPException,DBAPIError):db.rollback();return 'rejected'
 with patch('terraces.verify_claim_provider_identity',return_value=provider),ThreadPoolExecutor(max_workers=4) as workers:result=list(workers.map(attempt,range(4)))
 with Session(engine) as db:count=db.query(TerracePhoto).filter_by(visit_id=visit_id).count()
 assert result.count('saved')==3 and count==3,(mode,result,count)
 outcomes.append({'mode':mode,'saved':3,'rejected':1,'final_rows':count})
(OUT/'concurrency-tests.json').write_text(json.dumps(outcomes,indent=2)+'\n',encoding='utf-8')
assert test_returncode==0
