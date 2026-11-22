"""Admin-only PIN restoration, single use, preserved timestamps and stock."""
import concurrent.futures
import http.cookiejar
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import server

class PinRestore(unittest.TestCase):
 def test_restore_flow(self):
  old=server.DB
  with tempfile.TemporaryDirectory() as tmp, patch.object(server,'RESTORE_PIN_HASH',server.hash_pass('test-pin-only',server.RESTORE_PIN_SALT)), patch.object(server,'FAILS',{}):
   server.DB=Path(tmp)/'test.sqlite3';server.init_db()
   h=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
   threading.Thread(target=h.serve_forever,daemon=True).start()
   def client():return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
   def call(c,path,body=None):
    req=urllib.request.Request('http://127.0.0.1:'+str(h.server_port)+path,data=json.dumps(body).encode() if body is not None else None,headers={'X-FoodDesk':'local-app','Content-Type':'application/json'})
    try:
     with c.open(req) as r:return r.status,json.load(r)
    except urllib.error.HTTPError as e:return e.code,json.load(e)
   try:
    admin=client();counter=client();other=client()
    call(admin,'/api/setup',{'password':'administrator123'})
    call(admin,'/api/login',{'username':'admin','password':'administrator123'})
    with patch.object(server,'DATA',Path(tmp)/'logs'), patch.object(server,'decode_secure_qr',side_effect=RuntimeError('simulated internal failure')):
     status,error=call(admin,'/api/check',{'token':'TV26E2.test.test.test'})
     self.assertEqual(status,500);self.assertEqual(error['status'],'unavailable')
     self.assertIn('request-error.log',error['error'])
     log=(Path(tmp)/'logs'/'request-error.log').read_text()
     self.assertIn('simulated internal failure',log);self.assertNotIn('TV26E2.test.test.test',log)

    call(admin,'/api/create-counter',{'username':'counter1','password':'counter123','counter_name':'Counter One'})
    for c in [counter,other]:call(c,'/api/login',{'username':'counter1','password':'counter123'})
    call(admin,'/api/distribution',{'open':True,'year':'2','quantities':{'VEG':2,'NON-VEG':0}})
    with server.db() as conn:
     conn.execute("INSERT INTO students(reg_no,name,food_type,attendance,qr_token,imported_at,student_year) VALUES('PIN-001','Student','VEG','present','token-one',?,2)",(server.now(),));conn.commit()
    first=call(counter,'/api/redeem',{'token':'token-one'})[1]['student']
    body={'reg_no':'PIN-001','pin':'test-pin-only','revision':first['collection_revision']}
    self.assertEqual(call(counter,'/api/restore-collection',body)[0],403)
    self.assertEqual(call(admin,'/api/restore-collection',dict(body,pin='wrong'))[0],403)
    self.assertEqual(call(counter,'/api/check',{'token':'token-one'})[1]['status'],'used')
    self.assertEqual(call(admin,'/api/restore-collection',dict(body,revision=-1))[0],409)
    self.assertEqual(call(admin,'/api/restore-collection',body)[0],200)
    self.assertEqual(call(admin,'/api/restore-collection',body)[0],409)
    self.assertEqual(call(counter,'/api/check',{'token':'token-one'})[1]['status'],'valid')
    stats=call(admin,'/api/stats')[1]
    self.assertEqual(stats['inventory']['VEG']['served'],1);self.assertEqual(stats['inventory']['VEG']['remaining'],1)
    self.assertEqual(stats['totals']['served'],1)
    with concurrent.futures.ThreadPoolExecutor() as pool:
     results=list(pool.map(lambda c:call(c,'/api/redeem',{'token':'token-one'}),[counter,other]))
    self.assertEqual(sorted(x[0] for x in results),[200,409])
    self.assertEqual(call(counter,'/api/check',{'token':'token-one'})[1]['status'],'used')
    self.assertEqual(call(admin,'/api/restore-collection',body)[0],409)
    server.init_db()
    with server.db() as conn:
     self.assertEqual(conn.execute('SELECT COUNT(*) FROM collection_archive').fetchone()[0],1)
     self.assertEqual(conn.execute('SELECT redeemed_at FROM collection_archive').fetchone()[0],first['redeemed_at'])
     self.assertEqual(conn.execute('SELECT COUNT(*) FROM all_collections').fetchone()[0],2)
     self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit WHERE action='collection_restored'").fetchone()[0],1)
     self.assertNotIn('test-pin-only',str([tuple(x) for x in conn.execute('SELECT * FROM audit')]))
    stats=call(admin,'/api/stats')[1]
    self.assertEqual(stats['totals']['served'],2);self.assertEqual(stats['inventory']['VEG']['remaining'],0)
    live=call(admin,'/api/live')[1];self.assertEqual(len(live['served']),2)
    self.assertEqual(sum(d['served'] for d in live['devices']),2)
    self.assertEqual(sum(call(c,'/api/my-device')[1]['total'] for c in [counter,other]),2)
    latest=call(admin,'/api/students')[1]['students'][0]
    body['revision']=latest['collection_revision']
    self.assertEqual(call(admin,'/api/restore-collection',body)[0],200)
    self.assertEqual(call(counter,'/api/redeem',{'token':'token-one'})[1]['status'],'blocked')
    with server.db() as conn:
     conn.execute("INSERT INTO students(reg_no,name,food_type,attendance,qr_token,imported_at,student_year) VALUES('PIN-002','Unused Student','VEG','present','token-two',?,2)",(server.now(),));conn.commit()
    self.assertEqual(call(admin,'/api/revoke',{'reg_no':'PIN-002','pin':'wrong'})[0],403)
    self.assertEqual(call(admin,'/api/revoke',{'reg_no':'PIN-002','pin':'test-pin-only'})[1]['pass_status'],'revoked')
    self.assertEqual(call(counter,'/api/check',{'token':'token-two'})[1]['status'],'blocked')
    self.assertEqual(call(admin,'/api/revoke',{'reg_no':'PIN-002','pin':'test-pin-only'})[1]['pass_status'],'active')
    for _ in range(5):self.assertEqual(call(admin,'/api/revoke',{'reg_no':'PIN-001','pin':'wrong'})[0],403)
    self.assertEqual(call(admin,'/api/revoke',body)[0],429)
   finally:
    h.shutdown();h.server_close();server.DB=old

if __name__=='__main__':unittest.main()
