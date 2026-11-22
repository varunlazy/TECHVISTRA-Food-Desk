"""Integration checks using isolated database and real HTTP requests."""
import concurrent.futures
import http.cookiejar
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
import server

class Flow(unittest.TestCase):
 def test_full_flow(self):
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'test.sqlite3';server.init_db();server.init_db()
   httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
   threading.Thread(target=httpd.serve_forever,daemon=True).start()
   url='http://127.0.0.1:'+str(httpd.server_port)
   def client(): return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
   def call(c,path,body=None):
    req=urllib.request.Request(url+path,data=json.dumps(body).encode() if body is not None else None,headers={'X-FoodDesk':'local-app','Content-Type':'application/json'})
    try:
     with c.open(req) as r:return r.status,json.load(r)
    except urllib.error.HTTPError as e:return e.code,json.load(e)
   try:
    admin=client();a=client();b=client()
    self.assertEqual(call(admin,'/api/setup',{'password':'administrator123'})[0],200)
    self.assertEqual(call(admin,'/api/login',{'username':'admin','password':'administrator123'})[0],200)
    for name in ['phone1','phone2']:
     self.assertEqual(call(admin,'/api/create-counter',{'username':name,'password':'staffpass123','counter_name':name})[0],200)
    for c,name in [(a,'phone1'),(b,'phone2')]:
     self.assertEqual(call(c,'/api/login',{'username':name,'password':'staffpass123','device_name':name})[0],200)
     self.assertEqual(call(c,'/api/heartbeat',{})[0],200)
     self.assertEqual(call(c,'/api/live')[0],403)
     self.assertEqual(call(c,'/api/students')[0],403)
    conn=server.db()
    conn.execute("INSERT INTO students(reg_no,name,food_type,attendance,qr_token,imported_at) VALUES('REG1','Student One','VEG','present','token-one',?)",(server.now(),))
    conn.executemany('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',[('classroom_year','2')])
    conn.execute("UPDATE settings SET value='1' WHERE key='distribution_open'");conn.execute('UPDATE students SET student_year=2');conn.commit();conn.close()
    self.assertEqual(call(a,'/api/check',{'token':'token-one'})[1]['status'],'valid')
    self.assertEqual(call(b,'/api/check',{'token':'bad-token'})[1]['status'],'invalid')
    x=call(admin,'/api/live')[1];self.assertTrue(any(r['status']=='valid' for r in x['requests']))
    with concurrent.futures.ThreadPoolExecutor() as pool:
     results=list(pool.map(lambda c:call(c,'/api/redeem',{'token':'token-one'}),[a,b]))
    self.assertEqual(sorted(r[0] for r in results),[200,409])
    x=call(admin,'/api/live')[1]
    self.assertEqual(len(x['served']),1)
    self.assertEqual(sum(d['served'] for d in x['devices']),1)
    self.assertEqual(sum(call(c,'/api/my-device')[1]['total'] for c in [a,b]),1)
    self.assertEqual(x['requests'][-1]['status'],'served')
    self.assertEqual(call(a,'/api/check',{'token':'token-one'})[1]['status'],'used')
    call(a,'/api/logout',{});x=call(admin,'/api/live')[1]
    self.assertFalse(next(d for d in x['devices'] if d['username']=='phone1')['online'])
    # Cookie-backed device persists across logouts, rather than duplicating totals.
    call(a,'/api/login',{'username':'phone1','password':'staffpass123','device_name':'phone1'})
    self.assertEqual(len(call(admin,'/api/live')[1]['devices']),3)
   finally:
    httpd.shutdown();httpd.server_close()

if __name__=='__main__':unittest.main()
