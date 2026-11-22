"""TechVistra TV26E2: offline signature verification + authenticated decryption.

No student CSV, network, or private signing key needed on the laptop.
The AES key and PEM verification key are held in data/offline-qr-private.json.
"""
import base64
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
# Current Indian Standard Time uses a fixed offset; no OS timezone database needed.
IST = timezone(timedelta(hours=5, minutes=30), 'IST')

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'data' / 'offline-qr-private.json'

class InvalidPass(ValueError):
    pass


def _unb64(text):
    try:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', text):
            raise InvalidPass('QR encoding is invalid.')
        decoded = base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))
        if base64.urlsafe_b64encode(decoded).rstrip(b'=').decode('ascii') != text:
            raise InvalidPass('QR encoding is noncanonical.')
        return decoded
    except Exception:
        raise InvalidPass('QR encoding is invalid.')


def decode(token):
    """Return verified student fields, or fail closed with an invalid QR error."""
    if not isinstance(token, str) or len(token) > 2400:
        raise InvalidPass('QR text is too long or invalid.')
    fields = token.strip().split('.')
    if len(fields) != 4 or fields[0] != 'TV26E2':
        raise InvalidPass('Expected TECHVISTRA encrypted QR (TV26E2).')
    if not CONFIG.is_file():
        raise InvalidPass('Offline QR verification has not been configured on this laptop.')
    try:
        from cryptography.exceptions import InvalidSignature, InvalidTag
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise InvalidPass('Install the cryptography package before event day.')
    try:
        settings = json.loads(CONFIG.read_text(encoding='utf-8'))
        key = base64.b64decode(settings['aes_key_b64'], validate=True)
        public = serialization.load_pem_public_key(settings['public_pem'].encode('ascii'))
        nonce, ct, sig = (_unb64(p) for p in fields[1:])
        if len(key) != 32 or len(nonce) != 12 or len(ct) < 17 or len(sig) != 64:
            raise InvalidPass('QR contents have invalid lengths.')
        if not isinstance(public, ec.EllipticCurvePublicKey) or not isinstance(public.curve, ec.SECP256R1):
            raise InvalidPass('QR verification public key must be P-256.')
        r, s = (int.from_bytes(sig[:32], 'big'), int.from_bytes(sig[32:], 'big'))
        signed = '.'.join(fields[:3]).encode('ascii')
        public.verify(encode_dss_signature(r, s), signed, ec.ECDSA(hashes.SHA256()))
        payload = json.loads(AESGCM(key).decrypt(nonce, ct, b'TV26E2'))
    except (InvalidSignature, InvalidTag):
        raise InvalidPass('Invalid or possibly fake QR: signature or encrypted content does not match the issuer. Do not serve food.')
    except InvalidPass:
        raise
    except Exception:
        raise InvalidPass('QR cannot be decrypted or verified. Check offline setup.')
    if not isinstance(payload, dict):
        raise InvalidPass('QR data format is invalid.')
    if payload.get('v') != 2 or payload.get('scope') != 'TV26_HOSP_FOOD':
        raise InvalidPass('QR format does not belong to this food service.')
    if payload.get('kind') not in ('live', 'demo'):
        raise InvalidPass('QR mode is not recognized.')
    if not isinstance(payload.get('id'), str) or not re.fullmatch('[a-f0-9]{32}', payload['id']):
        raise InvalidPass('QR pass ID is invalid.')
    if payload.get('kind') == 'live' and (type(payload.get('year')) is not int or payload['year'] not in (2,3,4)):
        raise InvalidPass('QR must include a valid student year (2, 3 or 4). Request a newly issued pass.')
    if payload.get('meal') not in ('veg','non_veg'):
        raise InvalidPass('QR meal preference is invalid.')
    if not isinstance(payload.get('reg'), str) or not re.fullmatch(r'[A-Za-z0-9._/-]{4,90}', payload['reg']):
        raise InvalidPass('QR register number is invalid.')
    if not isinstance(payload.get('name'), str) or not (0 < len(payload['name']) <= 150):
        raise InvalidPass('QR student name is invalid.')
    if not isinstance(payload.get('exp'), int) or not isinstance(payload.get('day'), str):
        raise InvalidPass('QR expiry data is invalid.')
    today = datetime.now(IST)
    if payload['day'] != today.strftime('%Y-%m-%d') or not today.timestamp() <= payload['exp']:
        raise InvalidPass('Expired QR or wrong service day.')
    return {k:payload.get(k) for k in ('kind','id','name','reg','dept','section','meal','day','exp','year')}
