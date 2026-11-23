"""Reason-only alert presentation. Does not check health, send mail or change alerts."""
from html import escape
import re


def render(reason, observed, *, test=False, env=None):
    env = env or {}
    # Do not echo arbitrary exception messages or configuration into an email.
    code = reason if isinstance(reason, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{1,100}', reason) else 'UNCLASSIFIED_ALERT'
    unknown_evidence = ('MONITOR_CHECK_FAILED', 'MONITOR_CHECK_UNAVAILABLE', 'RECOVERY_ACCEPTANCE',
                        'RETENTION', 'ALERT_UNAVAILABLE')
    amber = any(token in code for token in unknown_evidence) or code == 'UNCLASSIFIED_ALERT'
    status = 'GREEN' if test else 'AMBER' if amber else 'RED'
    if code.startswith('SUPABASE_AUTH_'):
        scope, finding = 'Supabase Auth backup', 'The Auth backup operation did not complete successfully.'
    elif code.startswith('SUPABASE_PHOTOS_'):
        scope, finding = 'Private photo backup', 'The private photo backup operation did not complete successfully.'
    elif code == 'SUPABASE_IDENTITY_CONTINUITY_EXCEPTION':
        scope, finding = 'Auth identity continuity', 'The identity check found a failure or could not establish continuity.'
    elif code.startswith('SUPABASE_'):
        scope, finding = 'Supabase recovery check', 'Supabase recovery protection requires attention.'
    elif code.startswith('RECOVERY_ACCEPTANCE_'):
        scope, finding = 'Deletion-safe restore readiness', 'Required restore-acceptance evidence could not be validated.'
    elif code.startswith('DELETION_SUPPRESSION_'):
        scope, finding = 'Deletion protection', 'A deletion-suppression record could not be made durable.'
    else:
        scope, finding = 'PostgreSQL backup check', 'The backup operation or verification reported an exception.'
    if test:
        finding = 'Safe delivery test only. No production health check or restore was performed.'
    elif 'MONITOR_CHECK_' in code:
        finding = 'The checker could not establish backup health; a failed backup is not confirmed.'
    elif 'RETENTION' in code:
        finding = 'Backup cleanup/retention needs review; this alert does not establish backup creation failure.'
    subject = f'[{status}] Matchgoer recovery — '+('safe test alert' if test else 'attention required')
    verdict = ('Delivery test; no operational health verdict.' if test else
               'Action required for the recovery check below.' if status == 'RED' else
               'Attention required; recovery status is not fully confirmed by this alert.')
    action = ('No operational action required for this synthetic example.' if test else
              'Inspect the technical receipt and restore evidence. Do not bypass mandatory deletion replay.'
              if code.startswith('RECOVERY_ACCEPTANCE_') else
              'Investigate the identity-check receipt; preserve accounts and do not automatically relink identities.'
              if code == 'SUPABASE_IDENTITY_CONTINUITY_EXCEPTION' else
              'Preserve immediate unpublication and stop irreversible erasure until suppression journaling is durable.'
              if code.startswith('DELETION_SUPPRESSION_') else
              'Inspect the source receipt, access and recent backup results. Do not restore into production.')
    reference = 'Existing Railway source-service logs / BACKUP_ALERT; UTC day '+observed.date().isoformat()
    repo, run = env.get('GITHUB_REPOSITORY', ''), env.get('GITHUB_RUN_ID', '')
    if re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) and re.fullmatch(r'[0-9]+', run):
        reference = 'GitHub checker receipt: https://github.com/'+repo+'/actions/runs/'+run
    lines = [subject, verdict, '', 'Status | Check | Finding', f'{status} | {scope} | {finding}',
             '', 'Action required', action,
             '', 'Metrics and changes', 'Observed UTC day: '+observed.date().isoformat(),
             'Change from previous comparable check: unavailable in this reason-only alert.',
             'Counts, backup timestamp and artifact checksums: see the source technical receipt.',
             '', 'Scope and evidence',
             'Other backup/Auth/photo outcomes are not established by this alert.',
             'Independent checker scheduling is not verified by backup creation.',
             'This notification does not establish a new successful restore.',
             '', 'Technical receipt', reference, 'Reason: '+code]
    e = lambda x: escape(str(x), quote=True)
    color = {'GREEN':'#17643b','AMBER':'#805700','RED':'#a82424'}[status]
    html = ('<!doctype html><html><body><main style="max-width:640px;margin:auto;padding:16px;'
            'font:16px/1.5 Arial,sans-serif;color:#202522;overflow-wrap:anywhere">'
            f'<h1 style="font-size:23px;color:{color}">{e(status)} — Matchgoer recovery</h1>'
            f'<p><strong>{e(verdict)}</strong></p>'
            '<table style="width:100%;table-layout:fixed;border-collapse:collapse;font-size:13px">'
            '<colgroup><col style="width:64px"><col style="width:108px"><col></colgroup><thead><tr>'
            '<th align="left">Status</th><th align="left">Check</th><th align="left">Finding</th>'
            f'</tr></thead><tbody><tr><td style="white-space:nowrap;font-weight:bold;padding:8px">{status}</td>'
            f'<td style="padding:8px;overflow-wrap:normal">{e(scope)}</td><td style="padding:8px">{e(finding)}</td></tr></tbody></table>'
            '<h2 style="font-size:18px">Action required</h2><p>'+e(action)+'</p>'
            '<h2 style="font-size:18px">Metrics and changes</h2><p>Observed UTC day: '+e(observed.date().isoformat())+'<br>'
            'Previous comparison unavailable; counts and checksums are in the source receipt.</p>'
            '<h2 style="font-size:18px">Scope</h2><p>Other systems are not established by this alert. '
            'Backup creation does not verify independent scheduling or a successful restore.</p>'
            '<h2 style="font-size:18px">Technical receipt</h2><p>'+e(reference)+'<br>Reason: '+e(code)+'</p>'
            '</main></body></html>')
    return {'subject':subject,'text':'\n'.join(lines),'html':html}
