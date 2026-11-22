"""Signed local *test-only* QRs. Never substitute for live TV26E2 credentials.

Every token has the distinct TV26TEST1 prefix and a short expiration.
The server handles these in a separate demo redemption table. The independent
HMAC key is held on the event laptop and NEVER sent to any browser.
"""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import time

ROOT = Path(__file__).resolve().parent
SECRET_PATH = ROOT / 'data' / 'local-test-hmac.key'
PREFIX = 'TV26TEST1'

class InvalidTestQR(ValueError):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _unb64(value: str) -> bytes:
    if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise InvalidTestQR('Local test QR encoding is invalid.')
    raw = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
    if _b64(raw) != value:
        raise InvalidTestQR('Local test QR encoding is not canonical.')
    return raw


def _secret(create=False):
    if create:
        SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(SECRET_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'wb') as f:
                f.write(secrets.token_bytes(32))
    try:
        key = SECRET_PATH.read_bytes()
        if len(key) == 32:
            return key
    except OSError:
        pass
    raise InvalidTestQR('Local test key is unavailable. Generate a new test QR from Admin → Test QR.')


def make(meal='veg'):
    if meal not in ('veg', 'non_veg'):
        raise InvalidTestQR('Choose Veg or Non-Veg.')
    current = int(time.time())
    fields = {
        'scope': 'LOCAL_SCANNER_TEST_ONLY', 'v': 1,
        'id': secrets.token_hex(16),
        'name': 'TECHVISTRA TEST STUDENT',
        'reg': 'TV26-TEST-001', 'dept': 'DEMO ONLY', 'section': 'TEST',
        'meal': meal, 'kind': 'test', 'iat': current, 'exp': current + 30 * 60,
    }
    encoded = _b64(json.dumps(fields, separators=(',', ':'), sort_keys=True).encode('utf-8'))
    body = f'{PREFIX}.{encoded}'
    signature = _b64(hmac.new(_secret(create=True), body.encode('ascii'), hashlib.sha256).digest())
    return f'{body}.{signature}', fields


def verify(token):
    if not isinstance(token, str) or len(token) > 1500:
        raise InvalidTestQR('Invalid local test QR length.')
    parts = token.strip().split('.')
    if len(parts) != 3 or parts[0] != PREFIX:
        raise InvalidTestQR('Not a local test QR.')
    try:
        body = '.'.join(parts[:2])
        actual = _unb64(parts[2])
        expected = hmac.new(_secret(), body.encode('ascii'), hashlib.sha256).digest()
        if not hmac.compare_digest(actual, expected):
            raise InvalidTestQR('Local test QR signature invalid.')
        fields = json.loads(_unb64(parts[1]))
        current = int(time.time())
        if not isinstance(fields, dict) or fields.get('scope') != 'LOCAL_SCANNER_TEST_ONLY' or fields.get('v') != 1 or fields.get('kind') != 'test':
            raise InvalidTestQR('Not an authorized local scanner test QR.')
        if not isinstance(fields.get('iat'), int) or not isinstance(fields.get('exp'), int) or not (current - 3600 < fields['iat'] <= current + 30 and fields['iat'] < fields['exp'] <= fields['iat'] + 1800):
            raise InvalidTestQR('Invalid local test QR time window.')
        if fields['exp'] < current:
            raise InvalidTestQR('Local test QR expired. Generate another QR from Admin → Test QR.')
        if not isinstance(fields.get('id'), str) or not re.fullmatch(r'[0-9a-f]{32}', fields['id']):
            raise InvalidTestQR('Local test QR has an invalid identifier.')
        if fields.get('meal') not in ('veg', 'non_veg') or fields.get('reg') != 'TV26-TEST-001' or fields.get('name') != 'TECHVISTRA TEST STUDENT':
            raise InvalidTestQR('Local test QR identity is invalid.')
        return fields
    except InvalidTestQR:
        raise
    except (ValueError, TypeError, UnicodeError, KeyError, OverflowError):
        raise InvalidTestQR('Local test QR could not be verified.')
