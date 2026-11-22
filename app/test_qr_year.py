"""Verify that year is read only from authenticated encrypted QR contents."""
import base64,json,tempfile,unittest
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import offline_qr

class QRYear(unittest.TestCase):
 def test_authenticated_year(self):
  old=offline_qr.CONFIG
  with tempfile.TemporaryDirectory() as tmp:
   key=AESGCM.generate_key(bit_length=256);private=ec.generate_private_key(ec.SECP256R1())
   offline_qr.CONFIG=Path(tmp)/'qr.json'
   offline_qr.CONFIG.write_text(json.dumps({'aes_key_b64':base64.b64encode(key).decode(),'public_pem':private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()}))
   now=datetime.now(ZoneInfo('Asia/Kolkata'))
   def encode(year):
    payload={'v':2,'scope':'TV26_HOSP_FOOD','kind':'live','id':'a'*32,'meal':'veg','reg':'231191101179','name':'Test Student','day':now.strftime('%Y-%m-%d'),'exp':int((now+timedelta(hours=1)).timestamp())}
    if year is not None:payload['year']=year
    b64=lambda data:base64.urlsafe_b64encode(data).rstrip(b'=').decode()
    nonce=b'123456789012';ct=AESGCM(key).encrypt(nonce,json.dumps(payload).encode(),b'TV26E2')
    signed='TV26E2.'+b64(nonce)+'.'+b64(ct)
    r,s=decode_dss_signature(private.sign(signed.encode(),ec.ECDSA(hashes.SHA256())))
    return signed+'.'+b64(r.to_bytes(32,'big')+s.to_bytes(32,'big'))
   try:
    for year in (2,3,4):self.assertEqual(offline_qr.decode(encode(year))['year'],year)
    for year in (None,True,1,5,'2',2.0):
     with self.assertRaises(offline_qr.InvalidPass):offline_qr.decode(encode(year))
    token=encode(2);parts=token.split('.');parts[2]=('A' if parts[2][0]!='A' else 'B')+parts[2][1:]
    with self.assertRaises(offline_qr.InvalidPass):offline_qr.decode('.'.join(parts))
   finally:offline_qr.CONFIG=old

if __name__=='__main__':unittest.main()
