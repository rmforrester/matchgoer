import importlib.util,unittest,os,json
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch,MagicMock
from backend import fixture_integrity_email_monitor as m
class AdapterTests(unittest.TestCase):
 def setUp(self):self.now=datetime(2026,11,11,6,25,tzinfo=timezone.utc)
 def test_healthy_is_silent(self):self.assertIsNone(m.message({'passed':True},[],self.now))
 def test_missed_failed_or_unavailable_alerts(self):
  for reason in ['MISSING','FAILED','INTEGRITY_MONITOR_UNAVAILABLE']:self.assertIn(reason,m.message({'passed':False,'reason':reason},[],self.now)['text'])
 def test_only_imminent_material_exceptions(self):
  items=[dict(fixture_id=i,priority=priority,kickoff=date,reason='UNRESOLVED_VENUE',case_key=str(i)) for i,priority,date in [(1,'P0','2026-11-12T12:00:00Z'),(2,'P1','2026-11-13T12:00:00Z'),(3,'P2','2026-11-12T12:00:00Z'),(4,'P1','2026-12-01T12:00:00Z'),(5,'P0','2026-10-01T12:00:00Z')]]
  self.assertEqual([i['fixture_id'] for i in m.material({'exception_report':{'exceptions':items}},self.now)],[1,2]);self.assertIsNotNone(m.message({'passed':True},items[:1],self.now))
 def test_test_alert_is_explicit(self):self.assertIn('Controlled delivery test',m.message({},[],self.now,True)['text'])
 def test_send_is_bounded_and_idempotent_without_secret_output(self):
  response=MagicMock();response.__enter__.return_value=response;response.read.return_value=b'{"id":"synthetic-message"}'
  with patch.dict(os.environ,{'FIXTURE_INTEGRITY_RESEND_API_KEY':'synthetic-private-key','FIXTURE_INTEGRITY_ALERT_TO':'admin@example.test','FIXTURE_INTEGRITY_ALERT_FROM':'accounts@mail.matchgoer.com'}),patch.object(m.urllib.request,'urlopen',return_value=response) as call:
   payload=m.message({'passed':False,'reason':'MISSING'},[],self.now);a=m.send(payload,self.now);b=m.send(payload,self.now);self.assertEqual(a,b);self.assertFalse(a['delivery_confirmed']);self.assertNotIn('synthetic-private-key',json.dumps(a));self.assertEqual(call.call_args.kwargs['timeout'],25);self.assertEqual(call.call_args_list[0].args[0].get_header('Idempotency-key'),call.call_args_list[1].args[0].get_header('Idempotency-key'))
 def test_invalid_sender_fails_before_network(self):
  with patch.dict(os.environ,{'FIXTURE_INTEGRITY_RESEND_API_KEY':'synthetic','FIXTURE_INTEGRITY_ALERT_TO':'admin@example.test','FIXTURE_INTEGRITY_ALERT_FROM':'unverified@example.test'}),patch.object(m.urllib.request,'urlopen') as call:
   with self.assertRaises(ValueError):m.send({'subject':'Test','text':'Test'},self.now)
   call.assert_not_called()
 def test_provider_errors_report_status_without_echoing_body(self):
  import io,urllib.error,contextlib
  secret='sensitive-test-value';error=urllib.error.HTTPError('https://api.resend.com/emails',403,'Forbidden',{},io.BytesIO(json.dumps({'name':'validation_error','message':secret}).encode()));output=io.StringIO()
  with patch.object(m.sys,'argv',['monitor','--test-alert']),patch.object(m,'send',side_effect=error),contextlib.redirect_stdout(output):self.assertEqual(m.main(),2)
  data=json.loads(output.getvalue());self.assertEqual(data['http_status'],403);self.assertEqual(data['provider_error'],'validation_error');self.assertNotIn(secret,output.getvalue())
if __name__=='__main__':unittest.main(verbosity=2)
