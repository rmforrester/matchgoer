"""Presentation only. Alert decisions and integrity classifications live elsewhere."""
from collections import Counter
from html import escape

LABELS = {
    'VENUE_UNKNOWN': 'Venue not identified', 'UNRESOLVED_VENUE': 'Venue not resolved',
    'VENUE_COORDINATES_MISSING': 'Stadium coordinates missing',
    'VENUE_COORDINATE_COUNTRY_CONFLICT': 'Stadium location conflicts with its country',
    'VENUE_DISPUTED': 'Venue is disputed',
    'VERIFIED_VENUE_ASSIGNMENT_REGRESSION': 'A verified venue assignment changed',
    'VERIFIED_FIXTURE_IDENTITY_REGRESSION': 'A verified fixture identity changed',
}


def label(reason):
    return LABELS.get(reason, str(reason).replace('_', ' ').capitalize())


def comparison(current, previous):
    """Only already-recorded, like-for-like reconciliation metrics; no state writes."""
    def metrics(run):
        receipt = (run or {}).get('receipt') or {}
        report = receipt.get('report') or {}
        accounting = receipt.get('accounting') or {}
        values = {'New fixtures': accounting.get('inserted'),
                  'Fixture updates': accounting.get('updated'),
                  'Provider requests': report.get('total_provider_requests')}
        return {k: v for k, v in values.items() if type(v) is int}
    current_report = ((current or {}).get('receipt') or {}).get('report') or {}
    previous_report = ((previous or {}).get('receipt') or {}).get('report') or {}
    comparable = bool(current_report.get('mode') and
                      current_report.get('mode') == previous_report.get('mode') and
                      current_report.get('policy') == previous_report.get('policy') and
                      (current or {}).get('source_sha') == (previous or {}).get('source_sha'))
    old = metrics(previous) if comparable else {}
    return {'metrics': [{'name': k, 'value': v, 'delta': v-old[k] if k in old else None,
                         'limit': current_report.get('max_requests') if k=='Provider requests' else None}
                        for k, v in metrics(current).items()],
            'previous_run_id': previous.get('run_id') if previous and comparable else None,
            'previous_scheduled_for': str(previous.get('scheduled_for')) if previous and comparable else None,
            'warning_delta_available': False}


def render(health, summary, now):
    """GREEN preview is supported; the caller preserves quiet-on-success delivery."""
    failed = health.get('passed') is not True
    critical = summary.get('critical_count', 0)
    warnings = summary.get('warning_count', 0)
    deferred = summary.get('deferred_scopes') or []
    checked = summary.get('current_facts_rechecked') is True
    coverage = summary.get('league_coverage') or {}
    coverage_checked = coverage.get('status') == 'CHECKED' and coverage.get('primary_period') == 'FULL_SEASON'
    worldwide = coverage.get('totals', {}).get('Worldwide', {}).get('FULL_SEASON', {})
    coverage_gap = bool(worldwide.get('missing'))
    gaps = bool(summary.get('groups') or summary.get('coverage_entries') or warnings or deferred or not checked
                or not coverage_checked or coverage_gap)
    status = 'RED' if failed or critical else 'AMBER' if gaps else 'GREEN'
    title = 'critical incident' if status == 'RED' else 'coverage warning' if status == 'AMBER' else 'healthy'
    subject = f'[{status}] Matchgoer fixtures — {title}'
    verdict = ('Action required: reconciliation execution or its monitoring evidence needs investigation.' if failed else
               'Action required: fixture checks found a critical venue-integrity issue.' if critical else
               'Reconciliation is healthy; fixture coverage needs attention.' if status == 'AMBER' else
               'Fixture checks are healthy. No action required.')
    rows = [
        ('RED' if failed else 'GREEN', 'Reconciliation',
         'Successful execution is not confirmed' if failed else 'Completed successfully'),
        ('RED' if critical else 'GREEN' if checked else 'AMBER', 'Venue integrity',
         f'{critical} critical fixture(s)' if checked else 'Not checked; current venue evidence unavailable'),
        ('AMBER' if warnings or summary.get('coverage_entries') or not checked or not coverage_checked or coverage_gap else 'GREEN', 'Coverage',
         (f"Stored Discover (full season): {worldwide['visible']}/{worldwide['eligible']}; "
          f'{warnings} imminent warning fixture(s); gaps are not execution failures') if coverage_checked else
         'League coverage not checked; no coverage pass claimed'),
        ('AMBER' if deferred or not checked else 'GREEN', 'Discovery budget',
         f'{len(deferred)} competition scope(s) deferred' if checked else 'Not checked'),
    ]
    actions = []
    if failed:
        reason = health.get('reason') or 'EXECUTION_EVIDENCE_UNAVAILABLE'
        actions.append(f'Check reconciliation execution/monitoring evidence ({reason}). '
                       'Missing evidence does not prove that reconciliation failed.')
    if critical:
        actions.append(f'Investigate {critical} critical venue-integrity fixture(s). '
                       'Keep existing location safeguards in place; do not guess a replacement venue.')
        cases = [x for x in summary.get('urgent', []) if x.get('priority') == 'P0']
        for item in cases[:3]:
            teams = ' vs '.join(str(item[k]) for k in ('home_team', 'away_team') if item.get(k))
            actions.append(f"{teams+' — ' if teams else ''}Fixture {item['fixture_id']}: {label(item['reason'])}.")
        if len(cases) > 3:
            actions.append(f'{len(cases)-3} additional critical reason entries are in the technical receipt.')
    if status == 'AMBER':
        actions.append('Review unresolved coverage when practical. Unaffected fixtures continue normally.')
        if deferred:
            actions.append('Some competition discovery checks were deferred by the existing budget; '
                           'coverage for those scopes is not confirmed by this run.')
    metrics = []
    context = summary.get('presentation_comparison') or {}
    for item in context.get('metrics', []):
        delta = item.get('delta')
        change = f" ({delta:+d} versus previous comparable run)" if delta is not None else ' (comparison unavailable)'
        limit = item.get('limit')
        cap = f' / {limit}' if type(limit) is int else ''
        metrics.append(f"{item['name']}: {item['value']}{cap}{change}")
    if context.get('previous_run_id'):
        metrics.append(f"Compared with {context['previous_scheduled_for']} UTC; run {context['previous_run_id']}.")
    metrics.append('Coverage-warning change: unavailable; the previous rechecked summary is not retained here.')
    from backend.fixture_coverage import email_lines
    metrics.extend(email_lines(summary.get('league_coverage')))
    categories = Counter(x['reason'] for x in summary.get('urgent', []) if x.get('priority') == 'P1')
    for reason, count in categories.most_common(3):
        metrics.append(f'Top warning reason: {label(reason)} — {count} reason entries (may overlap).')
    for title,key in [('Venue locality conflicts requiring review','actionable_locality_conflicts'),
                      ('Provider/canonical identity conflicts requiring review','provider_identity_conflicts')]:
        cases = summary.get(key) or []
        metrics.append(f'{title}: {len(cases)}')
        for case in cases[:3]:
            bound = case.get('current_bound_ground_locality') or case.get('bound_ground_locality') or 'unbound'
            observed = case.get('current_observed_provider_locality') or case.get('observed_provider_locality') or 'not supplied'
            name = case.get('current_observed_provider_name') or case.get('provider_venue_name')
            suffix = f" ({name})" if key == 'provider_identity_conflicts' and name else ''
            metrics.append(f"{case['fixture_id']} {bound} ? observed {observed}{suffix}")
    metrics.append('Complete raw diagnostics and review cases: technical receipt/detail (not limited to the first 100 warnings).')
    if not context.get('metrics'):
        metrics.append('Insert/update/request metrics are not available in this alert.')
    references = [f"Reconciliation receipt: fixture_integrity_runs / {summary.get('run_id') or health.get('run_id') or 'unavailable'}",
                  'Full current alert detail: Railway Fixture Integrity monitor logs / FIXTURE_INTEGRITY_MONITOR_DETAIL',
                  'Full observed fixture IDs/reasons: the referenced reconciliation receipt; email is a summary.',
                  'Not checked here: backups, Auth/photo recovery or independent backup-checker scheduling.']
    if deferred:
        references.append('Deferred scopes (competition/season): ' + ', '.join(
            f"{x['league_id']}/{x['season']}" for x in deferred))
    lines = [subject, verdict, f"Checked: {now.strftime('%Y-%m-%d UTC')}", '', 'Status | System | Result']
    lines += [' | '.join(row) for row in rows]
    if actions: lines += ['', 'Action required'] + ['- '+x for x in actions]
    lines += ['', 'Metrics and changes'] + ['- '+x for x in metrics]
    lines += ['', 'Technical references'] + references
    color = {'GREEN': '#17643b', 'AMBER': '#805700', 'RED': '#a82424'}[status]
    e = lambda x: escape(str(x), quote=True)
    table = ''.join('<tr>'+''.join(f'<td style="padding:8px;border-bottom:1px solid #ddd;vertical-align:top;'
                    f'{"white-space:nowrap;font-weight:bold" if i == 0 else "overflow-wrap:normal"}">{e(v)}</td>'
                    for i,v in enumerate(row))+'</tr>' for row in rows)
    bullets = lambda values: '<ul>'+''.join(f'<li style="margin:8px 0">{e(x)}</li>' for x in values)+'</ul>'
    html = ('<!doctype html><html><body><main style="max-width:640px;margin:auto;padding:16px;'
            'font:16px/1.5 Arial,sans-serif;color:#202522;overflow-wrap:anywhere">'
            f'<h1 style="font-size:23px;color:{color}">{e(status)} — Matchgoer fixtures</h1>'
            f'<p><strong>{e(verdict)}</strong></p><p>{e(now.strftime("%Y-%m-%d UTC"))}</p>'
            '<table style="width:100%;table-layout:fixed;border-collapse:collapse;font-size:13px">'
            '<colgroup><col style="width:64px"><col style="width:108px"><col></colgroup><thead><tr>'
            '<th align="left" style="padding:8px">Status</th><th align="left" style="padding:8px">System</th><th align="left" style="padding:8px">Result</th>'
            f'</tr></thead><tbody>{table}</tbody></table>'
            + ('<h2 style="font-size:18px">Action required</h2>'+bullets(actions) if actions else '')
            + '<h2 style="font-size:18px">Metrics and changes</h2>'+bullets(metrics)
            + '<h2 style="font-size:18px">Technical references</h2>'+bullets(references)+'</main></body></html>')
    return {'subject': subject, 'text': '\n'.join(lines), 'html': html}
