"""Signed QR integration: forgery rejection, one collection, durable duplicate time."""
import base64
import concurrent.futures
from datetime import datetime, timedelta
import http.cookiejar
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from zoneinfo import ZoneInfo
import offline_qr
import server

class SecureScan(unittest.TestCase):
 def test_signed_collection_and_forgery(self):
  old_db, old_config = server.DB, offline_qr.CONFIG
  with tempfile.TemporaryDirectory() as tmp:
   server.DB = Path(tmp)/'desk.sqlite3'
   offline_qr.CONFIG = Path(tmp)/'qr.json'
   key = AESGCM.generate_key(bit_length=256)
   private = ec.generate_private_key(ec.SECP256R1())
   offline_qr.CONFIG.write_text(json.dumps({'aes_key_b64':base64.b64encode(key).decode(), 'public_pem':private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()}))
   server.init_db()
   httpd = ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
   threading.Thread(target=httpd.serve_forever,daemon=True).start()
   url='http://127.0.0.1:'+str(httpd.server_port)
   def client():return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
   def call(c,path,body):
    req=urllib.request.Request(url+path,data=json.dumps(body).encode(),headers={'X-FoodDesk':'local-app','Content-Type':'application/json'})
    try:
     with c.open(req) as r:return r.status,json.load(r)
    except urllib.error.HTTPError as e:return e.code,json.load(e)
   b64=lambda value:base64.urlsafe_b64encode(value).rstrip(b'=').decode()
   def token(signer=private, meal='veg', pass_id='a'*32):
    now=datetime.now(ZoneInfo('Asia/Kolkata'))
    fields={'v':2,'scope':'TV26_HOSP_FOOD','kind':'live','id':pass_id,'meal':meal,'reg':'SECURE-001','name':'Security Test','year':2,'day':now.strftime('%Y-%m-%d'),'exp':int((now+timedelta(hours=1)).timestamp())}
    nonce=os.urandom(12)
    signed='TV26E2.'+b64(nonce)+'.'+b64(AESGCM(key).encrypt(nonce,json.dumps(fields).encode(),b'TV26E2'))
    r,s=decode_dss_signature(signer.sign(signed.encode(),ec.ECDSA(hashes.SHA256())))
    return signed+'.'+b64(r.to_bytes(32,'big')+s.to_bytes(32,'big'))
   try:
    admin=client();a=client();b=client()
    self.assertEqual(call(admin,'/api/setup',{'password':'administrator123'})[0],200)
    for c in [admin,a,b]:self.assertEqual(call(c,'/api/login',{'username':'admin','password':'administrator123'})[0],200)
    self.assertEqual(call(admin,'/api/distribution',{'open':True,'year':'2','quantities':{'VEG':5,'NON-VEG':0}})[0],200)
    genuine=token()
    parts=genuine.split('.');ct=bytearray(base64.urlsafe_b64decode(parts[2]+'='*(-len(parts[2])%4)));ct[0]^=1;parts[2]=b64(ct)
    fake_signer=ec.generate_private_key(ec.SECP256R1())
    for fake in ['made-up-student-qr', '.'.join(parts), token(fake_signer), token(fake_signer,meal='non_veg')]:
     self.assertEqual(call(a,'/api/check',{'token':fake})[1]['status'],'invalid')
     self.assertNotEqual(call(a,'/api/redeem',{'token':fake})[0],200)
    with server.db() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM students').fetchone()[0],0)
    self.assertEqual(call(a,'/api/check',{'token':genuine})[1]['status'],'valid')
    with concurrent.futures.ThreadPoolExecutor() as pool:
     results=list(pool.map(lambda c:call(c,'/api/redeem',{'token':genuine}),[a,b]))
    self.assertEqual(sorted(r[0] for r in results),[200,409])
    saved=next(data['student']['redeemed_at'] for code,data in results if code==200)
    for candidate in [genuine,token()]:
     data=call(a,'/api/check',{'token':candidate})[1]
     self.assertEqual(data['status'],'used');self.assertEqual(data['student']['redeemed_at'],saved)
     self.assertIn(server.format_ist(saved),data['message'])
    # Reinitialization/reopening DB must preserve history, not reset it.
    server.init_db()
    call(admin,'/api/distribution',{'open':False})
    data=call(b,'/api/redeem',{'token':genuine})[1]
    self.assertEqual(data['status'],'used');self.assertEqual(data['student']['redeemed_at'],saved)
    with server.db() as conn:
     self.assertEqual(conn.execute('SELECT COUNT(*) FROM students WHERE redeemed=1').fetchone()[0],1)
     self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit WHERE action='served'").fetchone()[0],1)
   finally:
    httpd.shutdown();httpd.server_close();server.DB=old_db;offline_qr.CONFIG=old_config

if __name__=='__main__':unittest.main()
