"""Meal stock validation and concurrent last-meal integration check."""
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

class InventoryFlow(unittest.TestCase):
 def test_stock(self):
  original=server.DB
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'test.sqlite3';server.init_db()
   h=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
   threading.Thread(target=h.serve_forever,daemon=True).start()
   c=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
   def call(path,body=None):
    req=urllib.request.Request('http://127.0.0.1:'+str(h.server_port)+path,data=json.dumps(body).encode() if body is not None else None,headers={'X-FoodDesk':'local-app','Content-Type':'application/json'})
    try:
     with c.open(req) as r:return r.status,json.load(r)
    except urllib.error.HTTPError as e:return e.code,json.load(e)
   try:
    call('/api/setup',{'password':'administrator123'})
    call('/api/login',{'username':'admin','password':'administrator123'})
    for bad in [None,{'VEG':-1,'NON-VEG':0},{'VEG':1.5,'NON-VEG':0},{'VEG':True,'NON-VEG':0},{'VEG':0,'NON-VEG':0}]:
     self.assertEqual(call('/api/distribution',{'open':True,'year':'2','quantities':bad})[0],400)
    self.assertEqual(call('/api/distribution',{'open':True,'year':'2','quantities':{'VEG':1,'NON-VEG':0}})[0],200)
    with server.db() as conn:
     for n in (1,2):
      conn.execute("INSERT INTO students(reg_no,name,food_type,attendance,qr_token,imported_at) VALUES(?,?,'VEG','present',?,?)",('25'+str(n),'Student '+str(n),'token-'+str(n),server.now()))
     conn.execute('UPDATE students SET student_year=2')
     conn.commit()
    with server.db() as conn:
     conn.execute("INSERT INTO students(reg_no,name,food_type,attendance,qr_token,imported_at) VALUES('241','Wrong year','VEG','present','wrong-year',?)",(server.now(),));conn.execute("UPDATE students SET student_year=3 WHERE qr_token='wrong-year'");conn.commit()
    self.assertEqual(call('/api/check',{'token':'wrong-year'})[1]['status'],'blocked')
    self.assertEqual(call('/api/redeem',{'token':'wrong-year'})[0],403)
    with server.db() as conn:
     with self.assertRaises(server.InvalidPass):
      server.ensure_encrypted_student(conn,{'reg':'241','year':3})
     fields={'id':'b'*32,'reg':'REG-NO-PREFIX','name':'Verified student','meal':'veg','year':2}
     self.assertEqual(server.ensure_encrypted_student(conn,fields)['student_year'],2)
     self.assertEqual(server.ensure_encrypted_student(conn,fields)['student_year'],2)
     conn.commit()
    self.assertEqual(call('/api/stats')[1]['gate']['classroom'],{'year':'2'})
    with concurrent.futures.ThreadPoolExecutor() as pool:
     result=list(pool.map(lambda n:call('/api/redeem',{'token':'token-'+str(n)}),(1,2)))
    self.assertEqual(sorted(r[0] for r in result),[200,409])
    self.assertEqual(call('/api/stats')[1]['inventory']['VEG'],{'total':1,'served':1,'remaining':0})
    self.assertEqual(call('/api/distribution',{'open':True,'year':'2','quantities':{'VEG':0,'NON-VEG':1}})[0],400)
    self.assertEqual(call('/api/distribution',{'open':True,'year':'3','quantities':{'VEG':2,'NON-VEG':0}})[0],409)
    self.assertEqual(call('/api/distribution',{'open':False})[0],200)
   finally:
    h.shutdown();h.server_close();server.DB=original

if __name__=='__main__':unittest.main()
