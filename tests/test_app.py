import csv, io, sqlite3, tempfile, unittest
from datetime import date,timedelta
from app import create_app
class EventTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.config={'TESTING':True,'SECRET_KEY':'testing','DATABASE':self.temp.name+'/events.db'}
  self.app=create_app(self.config);self.client=self.app.test_client();self.future=(date.today()+timedelta(days=3)).isoformat()
  self.assertEqual(self.app.test_cli_runner().invoke(args=['init-admin','--username','organiser','--password','correct-horse-battery']).exit_code,0)
 def tearDown(self):self.temp.cleanup()
 def token(self,c=None):
  c=c or self.client;c.get('/login')
  with c.session_transaction() as s:return s['csrf']
 def post(self,path,data=None,c=None):
  c=c or self.client;return c.post(path,data=dict(data or {},csrf=self.token(c)),follow_redirects=True)
 def login(self):self.post('/login',{'username':'organiser','password':'correct-horse-battery'})
 def create(self,**v):
  d=dict(name='Garden workshop',date=self.future,time='09:30',location='Community hall',description='A day together.',capacity='2');d.update(v);return self.post('/add_event',d)
 def sql(self,q):
  with sqlite3.connect(self.config['DATABASE']) as c:return c.execute(q).fetchall()
 def test_first_run_and_missing_pages(self):
  for path,code in [('/',200),('/login',200),('/profile',302),('/event/999',404)]:self.assertEqual(self.client.get(path).status_code,code)
 def test_hashed_password_cli_and_login(self):
  self.assertNotEqual(self.sql('SELECT password_hash FROM users')[0][0],'correct-horse-battery')
  self.assertIn(b'incorrect',self.post('/login',{'username':'organiser','password':'wrong'}).data)
  self.assertEqual(self.app.test_cli_runner().invoke(args=['init-admin','--username','x','--password','short']).exit_code,1)
  self.assertEqual(self.app.test_cli_runner().invoke(args=['init-admin','--username','organiser','--password','another-good-password']).exit_code,1)
 def test_auth_csrf_and_logout(self):
  self.create();self.assertEqual(self.sql('SELECT * FROM events'),[]);self.login()
  self.assertEqual(self.client.post('/add_event',data={}).status_code,400)
  self.assertEqual(self.client.post('/logout',data={'csrf':'🔥'}).status_code,400)
  self.assertEqual(self.client.get('/logout').status_code,405)
  self.post('/logout');self.assertEqual(self.client.get('/profile').status_code,302)
 def test_crud_persistence_safe_delete_and_unique_ids(self):
  self.login();self.create();self.create(name='Second event')
  self.assertIn(b'Garden workshop',create_app(self.config).test_client().get('/').data)
  self.post('/edit_event/1',dict(name='Updated',date=self.future,time='10:30',location='Hall',description='',capacity='2'))
  self.assertEqual(self.sql('SELECT name FROM events WHERE id=1')[0][0],'Updated')
  self.client.get('/delete_event/1');self.assertEqual(len(self.sql('SELECT * FROM events')),2)
  self.post('/delete_event/1');self.create(name='Third');self.assertEqual(len(self.sql('SELECT DISTINCT id FROM events')),2)
 def test_invalid_form_is_friendly(self):
  self.login()
  for v in [{'date':'2026-02-30'},{'time':'25:00'},{'capacity':'0'},{'capacity':'2.5'},{'name':''},{'location':''}]:self.assertEqual(self.create(**v).status_code,400)
  self.assertEqual(self.sql('SELECT * FROM events'),[])
 def test_date_filters_search_and_cancel(self):
  self.login();self.create();self.create(name='Old conference',date='2024-01-01')
  self.assertNotIn(b'Old conference',self.client.get('/').data);self.assertIn(b'Old conference',self.client.get('/?view=past').data)
  self.assertIn(b'Garden workshop',self.client.get('/?q=community').data);self.assertNotIn(b'Garden workshop',self.client.get('/?q=missing').data)
  self.post('/event/1/status');self.assertNotIn(b'Garden workshop',self.client.get('/').data);self.assertIn(b'Garden workshop',self.client.get('/?view=cancelled').data)
 def test_registration_duplicates_capacity_and_edit_limit(self):
  self.login();self.create();self.post('/event/1/attendees',{'name':'Jane','email':'jane@example.com'})
  self.assertIn(b'already registered',self.post('/event/1/attendees',{'name':'Other','email':'JANE@example.com'}).data)
  self.post('/event/1/attendees',{'name':'Bob'});self.post('/event/1/attendees',{'name':'Third'})
  self.assertEqual(len(self.sql('SELECT * FROM attendees')),2)
  self.assertEqual(self.post('/edit_event/1',dict(name='Updated',date=self.future,time='09:30',location='Hall',description='',capacity=1)).status_code,400)
  self.assertEqual(self.sql('SELECT capacity FROM events')[0][0],2)
 def test_closed_registration_and_invalid_attendee(self):
  self.login();self.create(date='2024-01-01');self.create();self.post('/event/2/status')
  for i in (1,2):self.assertIn(b'Registration is closed',self.post(f'/event/{i}/attendees',{'name':'Jane'}).data)
  self.create();self.post('/event/3/attendees',{'name':''});self.post('/event/3/attendees',{'name':'Test','email':'broken'})
  self.assertEqual(self.sql('SELECT * FROM attendees'),[])
 def test_guest_privacy_and_export_permissions(self):
  self.login();self.create();self.post('/event/1/attendees',{'name':'Private Guest','email':'private@example.com'})
  public=self.app.test_client();body=public.get('/event/1').data
  self.assertNotIn(b'Private Guest',body);self.assertNotIn(b'private@example.com',body)
  self.assertEqual(public.get('/event/1/export').status_code,302)
  self.post('/event/1/attendees/1/checkin',c=public);self.assertEqual(self.sql('SELECT checked_in FROM attendees')[0][0],0)
 def test_scoped_checkin_export_and_cascade(self):
  self.login();self.create();self.create(name='Other');self.post('/event/1/attendees',{'name':'=Formula','email':'guest@example.com'})
  self.assertEqual(self.post('/event/2/attendees/1/checkin').status_code,404)
  self.post('/event/1/attendees/1/checkin');self.assertEqual(self.sql('SELECT checked_in FROM attendees')[0][0],1)
  rows=list(csv.reader(io.StringIO(self.client.get('/event/1/export').data.decode())))
  self.assertEqual(rows[1],["'=Formula",'guest@example.com','Yes'])
  self.post('/event/1/attendees/1/checkin');self.assertEqual(self.sql('SELECT checked_in FROM attendees')[0][0],0)
  self.post('/delete_event/1');self.assertEqual(self.sql('SELECT * FROM attendees'),[])
 def test_template_escapes_html(self):
  self.login();self.create(name='<script>alert(1)</script>');self.assertNotIn(b'<script>alert(1)</script>',self.client.get('/').data)
