"""Email adapter for the existing read-only checker; never reconciles fixtures."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,urllib.request
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]

def probe():
    p=subprocess.run([sys.executable,str(ROOT/'scripts/check_fixture_integrity.py'),'--grace-hours','2'],capture_output=True,text=True,timeout=50)
    try:result=json.loads(p.stdout.strip().splitlines()[-1])
    except (ValueError,IndexError):return {'passed':False,'reason':'INTEGRITY_MONITOR_UNAVAILABLE'}
    return result if p.returncode in (0,1,2) else {'passed':False,'reason':'INTEGRITY_MONITOR_UNAVAILABLE'}

def execution_health(rows, now, grace_hours=2):
    """Interpret coverage separately, without changing the writer's run receipt."""
    from backend.fixture_integrity import missed_run
    result=missed_run(rows,now=now,grace_hours=grace_hours)
    if result.get('reason') not in ('OK','COVERAGE_INCOMPLETE'):return result
    row=next(r for r in rows if r['run_id']==result['run_id'])
    receipt=row.get('receipt') or {};report=receipt.get('report') or {}
    accounting=receipt.get('accounting')or{}
    discovery=report.get('global_fixture_discovery')or{}
    unsafe=(report.get('execution_success') is not True or report.get('commit_confirmed') is not True
            or bool(receipt.get('error')) or bool(report.get('write_error'))
            or 'unaccounted_missing_ids'not in accounting or bool(accounting['unaccounted_missing_ids'])
            or bool(report.get('provider_failures'))
            or any(g.get('errors')for g in discovery.get('groups',[])))
    if unsafe:return {**result,'passed':False,'reason':'RECONCILIATION_EXECUTION_OR_ACCOUNTING_FAILED','severity':'P0'}
    return {**result,'passed':True,'reason':'EXECUTION_HEALTHY','severity':'OK',
            'coverage_incomplete':row['state']=='INCOMPLETE' or report.get('complete') is False}


def _time(value):
    result=value if isinstance(value,datetime) else datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('NAIVE_FIXTURE_TIME')
    return result


def venue_diagnostics(receipt):
    """Uncapped original observations; never reinterpret the recorded policy reason."""
    report = receipt.get('report') or {}
    sources = list((report.get('venue_reconciliation') or {}).get('unresolved_or_conflicting', []))
    sources += list(receipt.get('lifecycle_decisions') or [])
    for group in [(report.get('fixture_discovery') or {})] + list((report.get('global_fixture_discovery') or {}).get('groups', [])):
        sources += list(group.get('locality_conflicts') or [])
    result = {}
    for item in sources:
        detail = item.get('venue_diagnostic') or item
        if detail.get('diagnostic_subreason') == 'VENUE_LOCALITY_CONFLICT':
            result[item['fixture_id']] = dict(detail, fixture_id=item['fixture_id'],
                policy_reason=detail.get('policy_reason') or 'VENUE_DISPUTED')
    return sorted(result.values(), key=lambda x:x['fixture_id'])


def diagnostic_review(detail, row, now):
    """Presentation-only current evidence classification; no resolver or policy writes."""
    from backend.fixture_integrity import ACTIVE
    from ingestion.venue_identity import normalize_identity as norm
    if not row or _time(row['kickoff']) < now or row.get('status') not in ACTIVE or row.get('superseded_by') is not None:
        return 'INACTIVE_OR_UNAVAILABLE'
    bound = row.get('canonical_ground_id')
    identity = row.get('policy_identity') or {}
    verified = (row.get('policy_state') == 'OFFICIAL_VERIFIED'
                and row.get('policy_venue_id') == bound and bound is not None
                and all(identity.get(k) == row.get(k) for k in ('fixture_id','league_id','season','home_team_id','away_team_id')))
    if verified:
        return 'RESOLVED_CURRENT_POLICY'
    observed = row.get('observed_provider_venue')
    if observed is None:
        observed = dict(id=detail.get('provider_venue_id'), name=detail.get('provider_venue_name'), city=detail.get('observed_provider_locality'))
    names = {norm(n) for n in row.get('canonical_names', []) if norm(n)}
    name = norm(observed.get('name'))
    reference_ground = row.get('observed_provider_ground_id')
    if bound is not None and ((reference_ground is not None and reference_ground != bound)
                             or (name and names and name not in names)):
        return 'PROVIDER_CANONICAL_IDENTITY_REVIEW'
    left = norm(row.get('ground_locality', detail.get('bound_ground_locality')))
    right = norm(observed.get('city'))
    placeholders = {'unknown','not supplied','unbound','none','n a'}
    if bound is None or len(left) < 2 or len(right) < 2 or left in placeholders or right in placeholders:
        return 'INCOMPLETE_COMPARISON'
    if left == right:
        return 'EQUIVALENT_CURRENT_CONTEXT'
    approved = {norm(v) for v in row.get('approved_localities', [])}
    if left in approved and right in approved:
        return 'VERIFIED_SCOPED_EQUIVALENT'
    return 'MATERIAL_LOCALITY_REVIEW'


def material(receipt,now,current):
    """Current SELECT facts override historical severity; no writer/policy mutations."""
    from backend.fixture_integrity import ACTIVE,venue_geography
    output={};excluded=Counter();groups=Counter()
    def add(row,reason,priority):
        fid=row['fixture_id'];kick=_time(row['kickoff'])
        item=dict(fixture_id=fid,reason=reason,kickoff=kick.isoformat(),priority=priority,
                  country=row.get('country') or 'UNKNOWN',competition=row.get('competition') or 'UNKNOWN',
                  home_team=row.get('home_team'),away_team=row.get('away_team'),
                  case_key=f'{fid}:{reason}')
        output[(fid,reason)]=item
    def active(row):
        if not row:return False
        if _time(row['kickoff'])<now-timedelta(hours=2):excluded['past_window']+=1;return False
        if row.get('status') not in ACTIVE or row.get('superseded_by') is not None:
            excluded['inactive_or_superseded']+=1;return False
        return True
    def geo(row):
        place=None if row.get('canonical_ground_id') is None else dict(venue_id=row['canonical_ground_id'],
              country=row.get('venue_country'),latitude=row.get('latitude'),longitude=row.get('longitude'))
        return venue_geography({'country':row.get('country')},place)
    def ready(row):
        checked=geo(row)
        return (checked.get('coordinates_checked',False) and not checked['hold']
                and row.get('policy_state') not in ('DISPUTED','UNRESOLVED')
                and not row.get('schedule_hold'))
    # A verified regression must be detected even if absent from the old digest.
    for row in current.values():
        if row.get('policy_state')!='OFFICIAL_VERIFIED' or not active(row):continue
        if row.get('policy_venue_id')!=row.get('canonical_ground_id'):
            add(row,'VERIFIED_VENUE_ASSIGNMENT_REGRESSION','P0')
        identity=row.get('policy_identity')
        if not isinstance(identity,dict) or any(k not in identity or identity[k]!=row.get(k)
                for k in ('fixture_id','league_id','season','home_team_id','away_team_id')):
            add(row,'VERIFIED_FIXTURE_IDENTITY_REGRESSION','P0')
    for item in receipt.get('exception_report',{}).get('exceptions',[]):
        row=current.get(item['fixture_id'])
        if row is None:
            # Missing returned fixtures stay visible, but cannot invent an event date.
            groups[('UNKNOWN','UNSTORED_FIXTURE',item['reason'])]+=1
            continue
        if not active(row):continue
        reason=item['reason'];kick=_time(row['kickoff']);imminent=kick<=now+timedelta(hours=72)
        if reason.startswith('VENUE_') or reason=='UNRESOLVED_VENUE':
            if ready(row):excluded['resolved_location']+=1;continue
            geographic=geo(row)
            attested_dispute=(row.get('policy_state')=='DISPUTED'
                              and bool(row.get('policy_source_url')) and bool(row.get('policy_evidence_sha256')))
            high=geographic['hold'] or attested_dispute
        elif reason in ('OVERLAPPING_KICKOFFS','SAME_OR_ADJACENT_DAY'):
            cases=[x for x in row.get('conflicts') or [] if x.get('key')==item.get('case_key')]
            if not cases:excluded['resolved_schedule']+=1;continue
            high=any(x.get('high_confidence') is True for x in cases)
        else:high=False
        add(row,reason,'P0'if high and imminent else 'P1'if imminent else 'P2')
    details=sorted(output.values(),key=lambda i:(i['priority'],i['kickoff'],i['fixture_id'],i['reason']))
    for item in details:groups[(item['country'],item['competition'],item['reason'])]+=1
    grouped=[dict(country=k[0],competition=k[1],reason=k[2],count=n)
             for k,n in sorted(groups.items(),key=lambda x:(-x[1],x[0]))]
    urgent=[x for x in details if x['priority']in ('P0','P1')]
    critical_ids={x['fixture_id']for x in urgent if x['priority']=='P0'}
    warning_ids={x['fixture_id']for x in urgent if x['priority']=='P1'}-critical_ids
    deferred=(receipt.get('report',{}).get('global_fixture_discovery')or{}).get('deferred_scopes',[])
    # Keep every original diagnostic, including elapsed/resolved/incomplete cases.
    locality = venue_diagnostics(receipt)
    actionable = []; provider_conflicts = []; review_categories = Counter()
    for detail in locality:
        row = current.get(detail['fixture_id'])
        category = diagnostic_review(detail, row, now)
        review_categories[category] += 1
        if category not in ('MATERIAL_LOCALITY_REVIEW','PROVIDER_CANONICAL_IDENTITY_REVIEW'): continue
        observed = (row or {}).get('observed_provider_venue') or {}
        case = dict(detail, home_team=row.get('home_team'), away_team=row.get('away_team'),
                    current_review_category=category,
                    current_bound_ground_id=row.get('canonical_ground_id'),
                    current_bound_ground_locality=row.get('ground_locality', detail.get('bound_ground_locality')),
                    current_observed_provider_locality=observed.get('city',detail.get('observed_provider_locality')),
                    current_observed_provider_name=observed.get('name',detail.get('provider_venue_name')))
        (actionable if category == 'MATERIAL_LOCALITY_REVIEW' else provider_conflicts).append(case)
    return dict(locality_conflicts=locality, locality_conflict_count=len(actionable),
                raw_locality_diagnostic_count=len(locality), actionable_locality_conflicts=actionable,
                provider_identity_conflicts=provider_conflicts, provider_identity_conflict_count=len(provider_conflicts),
                locality_diagnostic_categories=dict(review_categories),
                urgent=urgent,coverage_entries=sum(groups.values()),groups=grouped,
                excluded=dict(excluded),deferred_scopes=deferred,
                critical_count=len(critical_ids),warning_count=len(warning_ids),
                critical_entries=sum(x['priority']=='P0'for x in urgent),
                warning_entries=sum(x['priority']=='P1'for x in urgent),
                source_digest_is_historical=True,current_facts_rechecked=True)

def read_material(now):
    from sqlalchemy import create_engine,select,text
    from sqlalchemy.engine import make_url
    from backend.fixture_integrity import RUNS
    url=make_url(os.environ['DATABASE_URL']);options=url.query.get('options','')
    engine=create_engine(url,connect_args={'connect_timeout':8,'options':options+' -c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=3000'})
    try:
        with engine.connect().execution_options(isolation_level='REPEATABLE READ') as c:
            runs=[dict(r)for r in c.execute(select(RUNS).where(RUNS.c.scheduled_for>=now-timedelta(days=3))).mappings()]
            health=execution_health(runs,now)
            selected=next((r for r in runs if r['run_id']==health.get('run_id')),None)
            receipt=selected['receipt']if selected else {}
            ids={i['fixture_id']for i in receipt.get('exception_report',{}).get('exceptions',[])}
            ids.update(i['fixture_id'] for i in receipt.get('lifecycle_decisions', []) if i.get('venue_diagnostic'))
            report = receipt.get('report') or {}
            groups = [report.get('fixture_discovery') or {}] + list((report.get('global_fixture_discovery') or {}).get('groups', []))
            ids.update(i['fixture_id'] for g in groups for i in g.get('locality_conflicts', []))
            ids.update(i['fixture_id'] for i in venue_diagnostics(receipt))
            ids=list(ids)
            rows=c.execute(text('''SELECT f.fixture_id,f.league_id,f.season,f.home_team_id,f.away_team_id,
              f.home_team,f.away_team,f.country,f.league_name competition,coalesce(s.effective_kickoff,f.fixture_date) kickoff,
              coalesce(s.effective_status,f.status) status,s.schedule_hold,s.superseded_by,s.conflicts,
              coalesce(cv.venue_id,v.venue_id) canonical_ground_id,
              CASE WHEN cv.venue_id IS NOT NULL THEN cv.latitude ELSE v.latitude END latitude,
              CASE WHEN cv.venue_id IS NOT NULL THEN cv.longitude ELSE v.longitude END longitude,
              CASE WHEN cv.venue_id IS NOT NULL THEN cv.country ELSE v.country END venue_country,
              coalesce(cv.city,v.city) ground_locality,coalesce(cv.name,v.name) ground_name,
              s.provider_observation, p.state policy_state,p.venue_id policy_venue_id,p.identity policy_identity,
              p.source_url policy_source_url,p.evidence_sha256 policy_evidence_sha256
              FROM fixtures f LEFT JOIN fixture_schedule_integrity s USING(fixture_id)
              LEFT JOIN fixture_venue_verifications p USING(fixture_id)
              LEFT JOIN venues v ON v.venue_id=f.venue_id LEFT JOIN venues cv ON cv.venue_id=v.canonical_venue_id
              WHERE f.fixture_id=ANY(:ids) OR p.state='OFFICIAL_VERIFIED' '''),{'ids':ids}).mappings()
            current={r['fixture_id']:dict(r)for r in rows}
            # Same approved scoped facts already deployed to both writers; read only.
            registry_path=ROOT/'config/global_fixture_discovery.json'
            reviews=json.loads(registry_path.read_text(encoding='utf-8'))['venue_reviews'] if registry_path.exists() else []
            review={r['venue_id']:r for r in reviews}
            grounds={r['venue_id']:dict(r)for r in c.execute(text('SELECT venue_id,name,canonical_venue_id,provider_venue_id FROM venues')).mappings()}
            def root(gid):return (grounds.get(gid)or{}).get('canonical_venue_id') or gid
            names={}
            for gid,g in grounds.items(): names.setdefault(root(gid),[]).append(g['name'])
            for a in c.execute(text('SELECT venue_id,name FROM venue_names')).mappings():names.setdefault(root(a['venue_id']),[]).append(a['name'])
            refs={r['provider_venue_id']:root(r['venue_id'])for r in c.execute(text("SELECT venue_id,provider_venue_id FROM venue_provider_refs WHERE provider='api_football'")).mappings()}
            for gid,g in grounds.items():
                if g['provider_venue_id'] is not None: refs.setdefault(g['provider_venue_id'],root(gid))
            for row in current.values():
                gid=row['canonical_ground_id'];scoped=review.get(gid,{})
                row['canonical_names']=names.get(gid,[])+list(scoped.get('names',[]))
                row['approved_localities']=scoped.get('localities',[])
                observation=row.get('provider_observation')
                if isinstance(observation,dict):
                    observed=observation.get('venue') or {};row['observed_provider_venue']=observed
                    row['observed_provider_ground_id']=refs.get(observed.get('id')) if type(observed.get('id')) is int and observed['id']!=0 else None
            c.rollback()
        from backend.fixture_integrity_email_presentation import comparison
        previous=max((r for r in runs if selected and r.get('completed_at') and r['scheduled_for']<selected['scheduled_for']
                      and r['completed_at']<=selected['started_at'] and comparison(selected,r)['previous_run_id']),
                     key=lambda r:r['scheduled_for'],default=None)
        return {**material(receipt,now,current),'execution_health':health,
                'league_coverage':receipt.get('league_coverage'),
                'presentation_comparison':comparison(selected,previous),
                'run_id':selected['run_id']if selected else None}
    finally:engine.dispose()

def technical_summary(health, summary, now):
    urgent=summary.get('urgent',[]);groups=summary.get('groups',[]);deferred=summary.get('deferred_scopes',[])
    content={'observed_day_utc':now.date().isoformat(),'execution_health':health,
             'venue_integrity_critical_count':summary.get('critical_count',0),
             'venue_integrity_critical_entries':summary.get('critical_entries',0),
             'coverage_warning_count':summary.get('warning_count',0),
             'coverage_warning_entries':summary.get('warning_entries',0),
             'coverage_entries':summary.get('coverage_entries',len(urgent)),
             'urgent_entries_total':len(urgent),'urgent_entries_shown':min(100,len(urgent)),
             'urgent_entries_omitted':max(0,len(urgent)-100),'current_exceptions':urgent[:100],
             'groups':groups[:30],'groups_total':len(groups),'groups_omitted':max(0,len(groups)-30),
             'deferred_scopes':deferred,'excluded_after_recheck':summary.get('excluded',{}),
             'run_id':summary.get('run_id'),'presentation_comparison':summary.get('presentation_comparison'),
             'league_coverage_reference':'fixture_integrity_runs.receipt.league_coverage',
             'league_coverage_status':(summary.get('league_coverage')or{}).get('status','UNAVAILABLE'),
             'note':'Current SELECT facts rechecked. Coverage warnings do not mean reconciliation failed; unaffected processing continues.'}
    content['locality_conflicts'] = summary.get('locality_conflicts', [])
    content['locality_conflict_count'] = summary.get('locality_conflict_count', 0)
    for key in ('raw_locality_diagnostic_count','actionable_locality_conflicts','provider_identity_conflicts','provider_identity_conflict_count','locality_diagnostic_categories'):
        content[key] = summary.get(key, [] if key.endswith('conflicts') else {} if key.endswith('categories') else 0)
    return content


def message(health,exceptions,now,test=False):
    if test:return {'subject':'[GREEN] Matchgoer Fixture Integrity - safe test alert','text':'Controlled delivery test only. No reconciliation or provider request was executed. No fixture or supporter records were changed.'}
    summary=exceptions if isinstance(exceptions,dict)else {'urgent':exceptions,'groups':[],'deferred_scopes':[]}
    if health.get('passed') is True and not summary.get('urgent') and not summary.get('groups') and not summary.get('deferred_scopes'):return None
    from backend.fixture_integrity_email_presentation import render
    return render(health,summary,now)

def send(payload,now):
    key=os.environ['FIXTURE_INTEGRITY_RESEND_API_KEY'];recipient=os.environ['FIXTURE_INTEGRITY_ALERT_TO'];sender=os.environ['FIXTURE_INTEGRITY_ALERT_FROM']
    if sender!='accounts@mail.matchgoer.com' or not recipient or '\n' in recipient or '\r' in recipient:raise ValueError('ALERT_CONFIGURATION_INVALID')
    body={'from':sender,'to':[recipient],**payload};encoded=json.dumps(body,sort_keys=True).encode();dedup='fixture-integrity-'+now.date().isoformat()+'-'+hashlib.sha256(encoded).hexdigest()
    request=urllib.request.Request('https://api.resend.com/emails',data=encoded,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','Accept':'application/json','User-Agent':'Matchgoer-FixtureIntegrity/1.0','Idempotency-Key':dedup},method='POST')
    with urllib.request.urlopen(request,timeout=25) as response:result=json.load(response)
    if not result.get('id'):raise ValueError('ALERT_NOT_ACCEPTED')
    return {'provider':'Resend','email_id':result['id'],'accepted':True,'delivery_confirmed':False}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--test-alert',action='store_true');args=parser.parse_args();now=datetime.now(timezone.utc)
    try:
        if args.test_alert:health,exceptions={'passed':True},[]
        else:
            try:
                exceptions=read_material(now);health=exceptions['execution_health']
            except Exception:health={'passed':False,'reason':'INTEGRITY_EXCEPTION_READ_UNAVAILABLE','severity':'P0'};exceptions={}
        payload=message(health,exceptions,now,args.test_alert)
        if not args.test_alert:
            from backend.production_source_continuity import check_from_environment, extend_alert
            source_health=check_from_environment()
            print(json.dumps({'event':'PRODUCTION_SOURCE_CONTINUITY',**source_health}),flush=True)
            payload=extend_alert(payload,source_health)
        if not args.test_alert:
            summary=exceptions if isinstance(exceptions,dict)else{}
            print(json.dumps({'event':'FIXTURE_INTEGRITY_MONITOR_RESULT',
                'execution_health':health,'critical_fixture_count':summary.get('critical_count',0),
                'critical_reason_entries':summary.get('critical_entries',0),
                'coverage_warning_fixture_count':summary.get('warning_count',0),
                'coverage_entries':summary.get('coverage_entries',0),
                'excluded_after_recheck':summary.get('excluded',{}),
                'deferred_scopes':summary.get('deferred_scopes',[]),
                'run_id':summary.get('run_id')}),flush=True)
        if payload is None:print(json.dumps({'passed':True,'email_sent':False}));return 0
        if not args.test_alert:
            print(json.dumps({'event':'FIXTURE_INTEGRITY_MONITOR_DETAIL',
                              **technical_summary(health,exceptions,now)}),flush=True)
        receipt=send(payload,now);print(json.dumps(receipt));return 0
    except Exception as error:
        details={}
        if isinstance(error,urllib.error.HTTPError):
            details['http_status']=error.code
            try:
                raw=error.read(4096);provider=json.loads(raw);name=provider.get('name')
                details['provider_error']=name if name in {'validation_error','invalid_api_key','missing_api_key','restricted_api_key','rate_limit_exceeded','application_error','internal_server_error','not_found','invalid_access'} else 'UNCLASSIFIED_PROVIDER_ERROR'
            except Exception:details['provider_error']='NON_JSON_PROVIDER_ERROR'
        print(json.dumps({'passed':False,'reason':'ALERT_DELIVERY_UNAVAILABLE','error_type':type(error).__name__,**details}));return 2
if __name__=='__main__':
    sys.path.insert(0,str(ROOT))
    raise SystemExit(main())
