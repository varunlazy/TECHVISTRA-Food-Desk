#!/usr/bin/env python3
"""TECHVISTRA '26 offline food desk: standard library LAN server + SQLite."""
import base64
import csv
import hashlib
import hmac
import io
import ipaddress
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import ssl
import socket
import sqlite3
import sys
import traceback
import threading
import time
import tempfile
import subprocess
import platform
from datetime import datetime, timezone
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse, quote
from offline_qr import decode as decode_secure_qr, InvalidPass, IST
from local_test_qr import make as make_local_test_qr, verify as verify_local_test_qr, InvalidTestQR, PREFIX as LOCAL_TEST_PREFIX

BASE = Path(__file__).resolve().parent
DATA = BASE / 'data'
DATA.mkdir(exist_ok=True)
DB = DATA / 'fooddesk.sqlite3'
PORT = int(os.getenv('FOODDESK_PORT', '8787'))
HOST = os.getenv('FOODDESK_HOST', '0.0.0.0')
TLS_CERT = os.getenv('FOODDESK_TLS_CERT', '').strip()
TLS_KEY = os.getenv('FOODDESK_TLS_KEY', '').strip()
AUTO_HTTPS = False
PHONE_SETUP_PORT = int(os.getenv('FOODDESK_SETUP_PORT', str(PORT + 1)))
LOOPBACK_PORT = int(os.getenv('FOODDESK_ADMIN_PORT', str(PORT + 2)))
SCHEME = 'https' if TLS_CERT and TLS_KEY else 'http'
SESSION_HOURS = 12
LOCK = threading.Lock()
# The OPTIONAL server-side webcam is used only by a browser running on the
# event laptop. Camera frames never leave the laptop except to its own browser.
LOCAL_CAMERA_LOCK = threading.Lock()
LOCAL_CAMERA = {'capture': None, 'owner': None, 'last_activity': 0, 'decoder': None}
FAILS = {}
RESTORE_PIN_SALT = '282eca7d2c1a00d9f2f9a0aea9e4e4c5'
RESTORE_PIN_HASH = '68d38bdc435eb8102345371cc18c6b66b62352d10b8334378285250818cbe0f6'
MAX_BODY = 8 * 1024 * 1024
REQUIRED_COLS = ['register_number', 'student_name', 'department', 'section', 'email', 'food_type', 'attendance_status', 'qr_token']


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def format_ist(value):
    if not value:
        return ''
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            return 'Time unavailable'
        return stamp.astimezone(IST).strftime('%d %b %Y, %I:%M:%S %p IST')
    except (ValueError, TypeError):
        return 'Time unavailable'


def db():
    conn = sqlite3.connect(DB, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=20000')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def init_db():
    conn = db()
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'counter')),
                counter_name TEXT,
                salt TEXT NOT NULL,
                pass_hash TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                expires REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY,
                reg_no TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                department TEXT NOT NULL DEFAULT '',
                section TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                food_type TEXT NOT NULL CHECK(food_type IN ('VEG','NON-VEG')),
                attendance TEXT NOT NULL CHECK(attendance IN ('present','absent')),
                qr_token TEXT NOT NULL UNIQUE,
                pass_status TEXT NOT NULL DEFAULT 'active' CHECK(pass_status IN ('active','revoked')),
                redeemed INTEGER NOT NULL DEFAULT 0,
                redeemed_at TEXT,
                redeemed_by INTEGER REFERENCES users(id),
                redeemed_counter TEXT,
                imported_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_students_token ON students(qr_token);
            CREATE INDEX IF NOT EXISTS idx_students_filter ON students(attendance, food_type, redeemed);
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS demo_redemptions (
                pass_id TEXT PRIMARY KEY, redeemed_at TEXT NOT NULL, redeemed_by TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS devices (
                user_id INTEGER NOT NULL REFERENCES users(id),
                device_ip TEXT NOT NULL,
                last_seen REAL NOT NULL,
                user_agent TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(user_id,device_ip)
            );
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY,
                at TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                reg_no TEXT,
                description TEXT,
                ip TEXT
            );
        ''')
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS phone_devices (
                id TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id),
                label TEXT NOT NULL, ip TEXT, agent TEXT, last_seen REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS scan_requests (
                id INTEGER PRIMARY KEY, at TEXT NOT NULL, device_id TEXT,
                username TEXT, token_hash TEXT, reg_no TEXT, name TEXT,
                food_type TEXT, status TEXT, message TEXT
            );
            CREATE INDEX IF NOT EXISTS scan_lookup ON scan_requests(token_hash,status);
        """)
        for table, column, definition in [('sessions','device_id','TEXT'), ('students','redeemed_device','TEXT'), ('students','student_year','INTEGER'), ('students','recollection_allowed','INTEGER NOT NULL DEFAULT 0'), ('students','collection_revision','INTEGER NOT NULL DEFAULT 0')]:
            if column not in [r[1] for r in conn.execute('PRAGMA table_info(' + table + ')')]:
                conn.execute('ALTER TABLE ' + table + ' ADD COLUMN ' + column + ' ' + definition)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS collection_archive (
                id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(id),
                reg_no TEXT NOT NULL, name TEXT NOT NULL, food_type TEXT NOT NULL,
                redeemed INTEGER NOT NULL DEFAULT 1, redeemed_at TEXT NOT NULL,
                redeemed_by INTEGER, redeemed_counter TEXT, redeemed_device TEXT
            );
            CREATE VIEW IF NOT EXISTS all_collections AS
                SELECT id,reg_no,name,food_type,redeemed,redeemed_at,redeemed_by,redeemed_counter,redeemed_device FROM students WHERE redeemed=1
                UNION ALL
                SELECT id,reg_no,name,food_type,redeemed,redeemed_at,redeemed_by,redeemed_counter,redeemed_device FROM collection_archive;
        """)
        conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('distribution_open','0')")
        conn.commit()
    finally:
        conn.close()


def is_distribution_open(conn):
    row = conn.execute("SELECT value FROM settings WHERE key='distribution_open'").fetchone()
    return bool(row and row['value'] == '1')


def meal_inventory(conn):
    settings = dict(conn.execute("SELECT key,value FROM settings WHERE key IN ('meal_veg','meal_nonveg')"))
    served = dict(conn.execute("SELECT food_type,COUNT(*) FROM all_collections GROUP BY food_type"))
    return {meal: {'total': int(settings[key]) if key in settings else None,
                   'served': served.get(meal, 0),
                   'remaining': max(0, int(settings[key])-served.get(meal, 0)) if key in settings else None}
            for meal, key in [('VEG','meal_veg'), ('NON-VEG','meal_nonveg')]}


def classroom_setup(conn):
    settings = dict(conn.execute("SELECT key,value FROM settings WHERE key='classroom_year'"))
    return {'year': settings.get('classroom_year','')}


def classroom_error(conn, student_year):
    setup = classroom_setup(conn)
    if not setup['year']:
        return 'Ask the administrator to select this laptop’s year before serving.'
    if type(student_year) is not int or student_year not in (2,3,4):
        return 'Student year missing from this pass. Ask for a newly issued QR containing the year.'
    if str(student_year) != setup['year']:
        labels = {2:'2nd',3:'3rd',4:'4th'}
        return 'Wrong venue — this counter serves ' + labels[int(setup['year'])] + ' year only. This student is in ' + labels[student_year] + ' year. Please go to the ' + labels[student_year] + ' year venue. Do not give food here.'
    return None


def status_snapshot(conn):
    count = conn.execute('SELECT COUNT(*) FROM students').fetchone()[0]
    eligible = conn.execute("SELECT COUNT(*) FROM students WHERE attendance='present' AND pass_status='active' AND (redeemed=0 OR recollection_allowed=1)").fetchone()[0]
    counters = conn.execute("SELECT COUNT(*) FROM users WHERE role='counter' AND active=1").fetchone()[0]
    return {
        'open': is_distribution_open(conn), 'imported': count, 'eligible': eligible,
        'classroom': classroom_setup(conn), 'active_counters': counters, 'ready': bool(count and eligible) or (DATA / 'offline-qr-private.json').is_file()
    }


def hash_pass(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 310000).hex()


def add_user(conn, username, password, role, counter_name=None):
    salt = secrets.token_hex(16)
    cur = conn.execute('INSERT INTO users(username,role,counter_name,salt,pass_hash,created_at) VALUES(?,?,?,?,?,?)',
                       (username, role, counter_name, salt, hash_pass(password, salt), now()))
    return cur.lastrowid


def audit(conn, user, action, reg_no='', description='', ip=''):
    conn.execute('INSERT INTO audit(at,actor,action,reg_no,description,ip) VALUES(?,?,?,?,?,?)',
                 (now(), user or 'system', action, reg_no or '', description[:300], ip[:80]))


def clean_token(text):
    value = (text or '').strip()
    # Website CSV/QR may contain the raw opaque token or a standard TV26 prefix.
    if value.upper().startswith('TV26|'):
        value = value[5:]
    elif value.upper().startswith('TV26:'):
        value = value[5:]
    return value.strip()


def public_student(row, reveal=False):
    if not row:
        return None
    result = {
        'reg_no': row['reg_no'], 'name': row['name'], 'year': row['student_year'], 'department': row['department'],
        'section': row['section'], 'food_type': row['food_type'],
        'attendance': row['attendance'], 'pass_status': row['pass_status'],
        'redeemed': bool(row['redeemed']), 'redeemed_at': row['redeemed_at'],
        'redeemed_counter': row['redeemed_counter'],
        'recollection_allowed': bool(row['recollection_allowed']), 'collection_revision': row['collection_revision']
    }
    if reveal:
        result['email'] = row['email']
    return result


def ensure_encrypted_student(conn, fields):
    """Register a verified LIVE QR from its decrypted data; no CSV required.
    The stable signed pass ID prevents regenerating an encrypted QR to bypass redemption.
    """
    error = classroom_error(conn, fields.get('year'))
    if error:
        raise InvalidPass(error)
    stable_token = 'TV26E2-ID-' + fields['id']
    existing = conn.execute('SELECT * FROM students WHERE qr_token=?', (stable_token,)).fetchone()
    if existing:
        if existing['reg_no'] != fields['reg']:
            raise InvalidPass('Pass identity mismatch. Contact the administrator.')
        if existing['student_year'] is not None and existing['student_year'] != fields['year']:
            raise InvalidPass('Pass year mismatch. Contact the administrator.')
        conn.execute('UPDATE students SET student_year=? WHERE id=?', (fields['year'], existing['id']))
        return conn.execute('SELECT * FROM students WHERE id=?',(existing['id'],)).fetchone()
    taken = conn.execute('SELECT * FROM students WHERE reg_no=?', (fields['reg'],)).fetchone()
    if taken:
        raise InvalidPass('Register number already has a different pass. Ask the administrator to investigate.')
    conn.execute('''INSERT INTO students(reg_no,name,department,section,email,food_type,attendance,qr_token,imported_at)
        VALUES(?,?,?,?,?,?,?,?,?)''', (fields['reg'],fields['name'], fields.get('dept') or '',
          fields.get('section') or '', '', 'VEG' if fields['meal']=='veg' else 'NON-VEG',
          'present', stable_token, now()))
    conn.execute('UPDATE students SET student_year=? WHERE qr_token=?',(fields['year'],stable_token))
    return conn.execute('SELECT * FROM students WHERE qr_token=?',(stable_token,)).fetchone()


def demo_public_student(fields, redeemed=None):
    return {'name':fields['name'],'reg_no':fields['reg'],'department':fields.get('dept') or '',
       'section': fields.get('section') or '', 'food_type':'VEG' if fields['meal']=='veg' else 'NON-VEG',
       'attendance':'present', 'pass_status':'demo', 'demo':True,
       'redeemed':bool(redeemed), 'redeemed_at':redeemed['redeemed_at'] if redeemed else None,
       'redeemed_counter':redeemed['redeemed_by'] if redeemed else None}


def local_ips():
    """Only inspect this laptop's own interfaces, never contact the internet."""
    found = []
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, family=socket.AF_INET):
            found.append(item[4][0])
    except OSError:
        pass
    commands = []
    system = platform.system()
    if system == 'Windows':
        commands = [['ipconfig']]
    elif system == 'Darwin':
        commands = [['ipconfig', 'getifaddr', 'en0'], ['ipconfig', 'getifaddr', 'en1'], ['ifconfig']]
    else:
        commands = [['ip', '-4', 'addr'], ['ifconfig']]
    for cmd in commands:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2, check=False)
            for match in re.findall(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])', result.stdout):
                found.append(match)
        except (OSError, subprocess.TimeoutExpired):
            pass
    output = []
    for addr in found:
        try:
            ip = ipaddress.ip_address(addr)
            if ip.version == 4 and (ip.is_private or ip.is_link_local) and not ip.is_loopback and not ip.is_unspecified:
                if addr not in output:
                    output.append(addr)
        except ValueError:
            continue
    return output


def is_loopback(address):
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def close_local_camera():
    """Called while holding LOCAL_CAMERA_LOCK."""
    capture = LOCAL_CAMERA['capture']
    if capture is not None:
        try:
            capture.release()
        except Exception:
            pass
    LOCAL_CAMERA.update(capture=None, owner=None, decoder=None, last_activity=0)


class Handler(BaseHTTPRequestHandler):
    server_version = 'TechvistraFoodDesk/3.0'

    def log_message(self, fmt, *args):
        print(f'[{self.log_date_time_string()}] {self.client_address[0]} {fmt % args}')

    def reply(self, status, data):
        if getattr(self, 'scan_context', None):
            conn, user, token = self.scan_context
            self.scan_context = None
            student = data.get('student') or {}
            conn.execute('INSERT INTO scan_requests(at,device_id,username,token_hash,reg_no,name,food_type,status,message) VALUES(?,?,?,?,?,?,?,?,?)',
                (now(), user['device_id'], user['username'], hashlib.sha256(token.encode()).hexdigest(),
                 student.get('reg_no',''), student.get('name',''), student.get('food_type',''),
                 'demo' if data.get('test_only') or student.get('demo') else data.get('status','error'), data.get('message',data.get('error',''))))
            conn.commit()
        raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(raw)

    def send_file(self, file, content_type=None):
        try:
            content = file.read_bytes()
        except OSError:
            return self.reply(404, {'error': 'Not found'})
        self.send_response(200)
        self.send_header('Content-Type', content_type or mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(content)

    def parsed(self):
        return urlparse(self.path)

    def device_cookie(self):
        try:
            jar = cookies.SimpleCookie(self.headers.get('Cookie',''))
            value = jar['tv_device'].value if 'tv_device' in jar else ''
            return value if re.fullmatch(r'[a-f0-9]{48}',value) else ''
        except cookies.CookieError:
            return ''

    def get_cookie(self):
        try:
            jar = cookies.SimpleCookie()
            jar.load(self.headers.get('Cookie', ''))
            return jar['tv_session'].value if 'tv_session' in jar else ''
        except (cookies.CookieError, KeyError):
            return ''

    def user(self, conn):
        token = self.get_cookie()
        if not token:
            return None
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        return conn.execute('''SELECT u.id,u.username,u.role,u.counter_name,u.active,s.device_id
            FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=? AND s.expires>? AND u.active=1''', (token_hash, time.time())).fetchone()

    def user_required(self, conn, role=None):
        user = self.user(conn)
        if not user:
            self.reply(401, {'error': 'Please sign in again.'})
            return None
        if role and user['role'] != role:
            self.reply(403, {'error': 'Administrator access required.'})
            return None
        return user

    def json_body(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > MAX_BODY:
                raise ValueError('Request size invalid or too large.')
            return json.loads(self.rfile.read(length).decode('utf-8'))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ValueError(f'Invalid request: {e}')

    def mutation_allowed(self):
        if self.headers.get('X-FoodDesk') != 'local-app':
            return False
        origin = self.headers.get('Origin', '')
        if origin:
            from urllib.parse import urlsplit
            parsed = urlsplit(origin)
            if parsed.netloc.lower() != self.headers.get('Host', '').lower():
                return False
        return True

    def do_GET(self):
        path = self.parsed().path
        if path in ('/', '/admin', '/counter'):
            return self.send_file(BASE / 'static' / 'index.html', 'text/html; charset=utf-8')
        if path.startswith('/static/'):
            rest = path[8:]
            if not re.fullmatch(r'[a-zA-Z0-9_.-]+', rest):
                return self.reply(404, {'error': 'Not found'})
            return self.send_file(BASE / 'static' / rest)
        conn = db()
        try:
            if path == '/api/session':
                count = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
                user = self.user(conn)
                return self.reply(200, {'setup_required': count == 0,
                    'user': dict(user) if user else None, 'server_time': now()})
            user = self.user_required(conn)
            if not user:
                return
            if path == '/api/local-camera/frame':
                # Web browsers on LAN HTTP cannot access their OWN camera. This
                # endpoint instead reads the event laptop's webcam with OpenCV.
                if not is_loopback(self.client_address[0]):
                    return self.reply(403, {'error': 'Laptop webcam is local-only. Use your own camera on HTTPS/localhost, Take QR photo, or a QR reader.'})
                owner = hashlib.sha256(self.get_cookie().encode()).hexdigest()
                with LOCAL_CAMERA_LOCK:
                    if LOCAL_CAMERA['capture'] is None or LOCAL_CAMERA['owner'] != owner:
                        return self.reply(409, {'error': 'Laptop camera is not running in this session.'})
                    if time.monotonic() - LOCAL_CAMERA['last_activity'] > 75:
                        close_local_camera()
                        return self.reply(409, {'error': 'Laptop camera session expired. Start it again.'})
                    cap = LOCAL_CAMERA['capture']
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        close_local_camera()
                        return self.reply(503, {'error': 'Laptop camera stopped supplying frames. Check its privacy permission and reconnect the camera.'})
                    LOCAL_CAMERA['last_activity'] = time.monotonic()
                    import cv2
                    # Decode at camera resolution, display a lower-bandwidth preview.
                    token, _, _ = LOCAL_CAMERA['decoder'].detectAndDecode(frame)
                    height, width = frame.shape[:2]
                    if width > 920:
                        frame = cv2.resize(frame, (920, max(1, round(height * 920 / width))))
                    encoded_ok, jpg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 62])
                    if not encoded_ok:
                        return self.reply(503, {'error': 'Could not produce laptop webcam preview.'})
                    image_data = base64.b64encode(jpg.tobytes()).decode('ascii')
                return self.reply(200, {'image': 'data:image/jpeg;base64,' + image_data, 'token': token or ''})
            if path == '/api/qr-setup-status':
                if user['role'] != 'admin':
                    return self.reply(403, {'error': 'Admin only'})
                from configure_secure_qr import configuration_status
                status = configuration_status()
                try:
                    import cryptography
                    status['cryptography_installed'] = True
                except ImportError:
                    status['cryptography_installed'] = False
                return self.reply(200, status)
            if path == '/api/health':
                return self.reply(200, {'ok': True, 'server_time': now(), 'distribution_open': is_distribution_open(conn)})
            if path == '/api/server-info':
                if user['role'] != 'admin':
                    return self.reply(403, {'error': 'Admin only'})
                addresses = [{'ip': ip, 'url': f'{SCHEME}://{ip}:{PORT}'} for ip in local_ips()] if HOST not in ('127.0.0.1', 'localhost','::1') else []
                devices = [dict(x) for x in conn.execute('''SELECT d.device_ip, d.last_seen, d.user_agent,
                    u.username, u.counter_name, u.role
                    FROM devices d JOIN users u ON u.id=d.user_id
                    WHERE u.active=1 ORDER BY d.last_seen DESC LIMIT 80''')]
                for device in devices:
                    device['online'] = time.time() - device['last_seen'] < 25
                    device['age_seconds'] = max(0, int(time.time() - device['last_seen']))
                    device.pop('last_seen')
                latest_import = conn.execute("SELECT at,description FROM audit WHERE action='csv_import' ORDER BY id DESC LIMIT 1").fetchone()
                return self.reply(200, {'server': 'This laptop', 'port': PORT, 'mode': 'laptop_only' if HOST in ('127.0.0.1', 'localhost','::1') else 'private_lan',
                    'addresses': addresses, 'localhost': f'http://localhost:{LOOPBACK_PORT}' if AUTO_HTTPS else f'{SCHEME}://localhost:{PORT}',
                    'devices': devices, 'gate': status_snapshot(conn),
                    'last_import': dict(latest_import) if latest_import else None,
                    'server_time': now(), 'offline': True, 'tls': SCHEME=='https',
                    'phone_setup_url': f'http://{addresses[0]["ip"]}:{PHONE_SETUP_PORT}/' if AUTO_HTTPS and addresses else None,
                    'phone_ca_fingerprint': __import__('local_https').fingerprint() if AUTO_HTTPS else None})
            if path == '/api/connect-qr':
                if user['role'] != 'admin':
                    return self.reply(403, {'error': 'Admin only'})
                address = parse_qs(self.parsed().query).get('ip', [''])[0]
                if HOST in ('127.0.0.1', 'localhost','::1') or address not in local_ips():
                    return self.reply(400, {'error':'Choose an active local interface address.'})
                try:
                    import qrcode
                    qr=qrcode.QRCode(box_size=7, border=3)
                    qr.add_data(f'{SCHEME}://{address}:{PORT}/')
                    qr.make(fit=True)
                    img=qr.make_image(fill_color='#0e2346', back_color='white')
                    mem=io.BytesIO();img.save(mem,format='PNG');raw=mem.getvalue()
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/png')
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Content-Length', str(len(raw)))
                    self.end_headers()
                    return self.wfile.write(raw)
                except ImportError:
                    return self.reply(503, {'error': 'QR package missing. Install requirements first.'})
            if path == '/api/backup':
                if user['role'] != 'admin':
                    return self.reply(403, {'error': 'Admin only'})
                filename = None
                try:
                    with tempfile.NamedTemporaryFile(prefix='tv_food_backup_', suffix='.sqlite3', delete=False) as tmp:
                        filename = tmp.name
                    target=sqlite3.connect(filename)
                    try:
                        conn.backup(target)
                    finally:
                        target.close()
                    raw=Path(filename).read_bytes()
                    self.send_response(200)
                    self.send_header('Content-Type','application/vnd.sqlite3')
                    self.send_header('Content-Disposition','attachment; filename="TECHVISTRA_food_database_backup.sqlite3"')
                    self.send_header('Cache-Control','no-store')
                    self.send_header('Content-Length',str(len(raw)))
                    self.end_headers()
                    return self.wfile.write(raw)
                finally:
                    if filename:
                        try: os.unlink(filename)
                        except OSError: pass
            if path == '/api/live':
                if user['role'] != 'admin':
                    return self.reply(403, {'error':'Admin only'})
                conn.execute("UPDATE scan_requests SET status='expired',message='No confirmation within 2 minutes' WHERE status='valid' AND at<?", (datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat(timespec='seconds'),))
                conn.commit()
                devices = [dict(r) for r in conn.execute("""SELECT d.*,u.username,u.active,
                    (SELECT COUNT(*) FROM all_collections s WHERE s.redeemed_device=d.id) served,
                    (SELECT COUNT(*) FROM all_collections s WHERE s.redeemed_device=d.id AND food_type='VEG') veg,
                    (SELECT COUNT(*) FROM all_collections s WHERE s.redeemed_device=d.id AND food_type='NON-VEG') nonveg
                    FROM phone_devices d JOIN users u ON u.id=d.user_id ORDER BY d.last_seen DESC""")]
                for device in devices:
                    device['online'] = bool(device['active'] and time.time()-device['last_seen'] < 22)
                requests = [dict(r) for r in conn.execute("SELECT * FROM scan_requests ORDER BY id DESC LIMIT 100")]
                served = [dict(r) for r in conn.execute("""SELECT s.reg_no,s.name,s.food_type,s.redeemed_at,s.redeemed_counter,
                    COALESCE(d.label,'Legacy / unknown device') device FROM all_collections s
                    LEFT JOIN phone_devices d ON d.id=s.redeemed_device WHERE s.redeemed=1
                    ORDER BY s.redeemed_at DESC,s.id DESC LIMIT 100""")]
                return self.reply(200, {'devices':devices,'requests':requests,'served':served,'time':now()})
            if path == '/api/my-device':
                row = conn.execute("SELECT COUNT(*) total, COALESCE(SUM(food_type='VEG'),0) veg, COALESCE(SUM(food_type='NON-VEG'),0) nonveg FROM all_collections WHERE redeemed=1 AND redeemed_device=?", (user['device_id'],)).fetchone()
                return self.reply(200, dict(row))
            if path == '/api/stats':
                if user['role'] != 'admin':
                    return self.reply(403, {'error': 'Admin only'})
                grouped = [dict(x) for x in conn.execute('''SELECT food_type, COUNT(*) total,
                    SUM(CASE WHEN attendance='present' AND pass_status='active' THEN 1 ELSE 0 END) active,
                    SUM(CASE WHEN redeemed=1 THEN 1 ELSE 0 END) served
                    FROM students GROUP BY food_type''').fetchall()]
                for group in grouped:
                    group['served'] = conn.execute('SELECT COUNT(*) FROM all_collections WHERE food_type=?',(group['food_type'],)).fetchone()[0]
                totals = dict(conn.execute('''SELECT COUNT(*) total,
                    COALESCE(SUM(attendance='present'),0) present,
                    COALESCE(SUM(attendance='absent'),0) absent,
                    COALESCE(SUM(attendance='present' AND pass_status='active'),0) eligible,
                    COALESCE(SUM(redeemed),0) served,
                    COALESCE(SUM(attendance='present' AND pass_status='active' AND (redeemed=0 OR recollection_allowed=1)),0) remaining,
                    COALESCE(SUM(pass_status='revoked'),0) revoked FROM students''').fetchone())
                totals['served'] = conn.execute('SELECT COUNT(*) FROM all_collections').fetchone()[0]
                counters = [dict(x) for x in conn.execute('''SELECT u.username,u.counter_name,u.active,
                    (SELECT COUNT(*) FROM all_collections s WHERE s.redeemed_by=u.id) served
                    FROM users u WHERE role='counter' ORDER BY u.username''')]
                return self.reply(200, {'totals': totals, 'meals': grouped, 'counters': counters, 'gate': status_snapshot(conn), 'inventory': meal_inventory(conn)})
            if path == '/api/students':
                if user['role'] != 'admin':
                    return self.reply(403, {'error': 'Admin only'})
                params = parse_qs(self.parsed().query)
                q = (params.get('q', [''])[0] or '').strip()[:100]
                filt = params.get('filter', ['all'])[0]
                where, args = [], []
                if q:
                    where.append('(reg_no LIKE ? OR name LIKE ? OR email LIKE ?)')
                    args.extend([f'%{q}%'] * 3)
                if filt == 'present': where.append("attendance='present'")
                if filt == 'absent': where.append("attendance='absent'")
                if filt == 'redeemed': where.append('redeemed=1')
                if filt == 'pending': where.append("attendance='present' AND pass_status='active' AND (redeemed=0 OR recollection_allowed=1)")
                if filt == 'revoked': where.append("pass_status='revoked'")
                clause = (' WHERE ' + ' AND '.join(where)) if where else ''
                count = conn.execute('SELECT COUNT(*) FROM students' + clause, args).fetchone()[0]
                rows = conn.execute('SELECT * FROM students' + clause + ' ORDER BY reg_no LIMIT 100 OFFSET 0', args).fetchall()
                return self.reply(200, {'students': [public_student(r, True) for r in rows], 'total': count, 'limited': count>100})
            if path == '/api/audit':
                if user['role'] != 'admin':
                    return self.reply(403, {'error': 'Admin only'})
                rows = conn.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 150').fetchall()
                return self.reply(200, {'logs': [dict(r) for r in rows]})
            if path == '/api/export':
                if user['role'] != 'admin':
                    return self.reply(403, {'error': 'Admin only'})
                stream = io.StringIO()
                writer = csv.writer(stream)
                writer.writerow(['register_number','student_name','department','section','email','food_type',
                                 'attendance_status','pass_status','redeemed','redeemed_at','counter','device','redeemed_at_ist','collection_count','restored_for_one_collection'])
                for r in conn.execute("SELECT s.*,d.label device_label,(SELECT COUNT(*) FROM collection_archive a WHERE a.student_id=s.id) archived_collections FROM students s LEFT JOIN phone_devices d ON d.id=s.redeemed_device ORDER BY reg_no"):
                    def safe(v):
                        value = str(v or '')
                        return "'" + value if value.startswith(('=', '+', '-', '@')) else value
                    writer.writerow([safe(r['reg_no']),safe(r['name']),safe(r['department']),safe(r['section']),safe(r['email']),
                        r['food_type'],r['attendance'],r['pass_status'],r['redeemed'],r['redeemed_at'],safe(r['redeemed_counter']),safe(r['device_label']),format_ist(r['redeemed_at']),r['archived_collections']+int(bool(r['redeemed'])),r['recollection_allowed']])
                raw = stream.getvalue().encode('utf-8-sig')
                self.send_response(200)
                self.send_header('Content-Type', 'text/csv; charset=utf-8')
                self.send_header('Content-Disposition','attachment; filename="TECHVISTRA_food_report.csv"')
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Cache-Control','no-store')
                self.end_headers()
                return self.wfile.write(raw)
            if path.startswith('/api/pass-qr/'):
                if user['role'] != 'admin':
                    return self.reply(403, {'error': 'Admin only'})
                reg = path.split('/')[-1]
                student = conn.execute('SELECT * FROM students WHERE reg_no=?', (reg,)).fetchone()
                if not student or student['attendance'] != 'present':
                    return self.reply(404, {'error': 'Eligible student not found'})
                try:
                    import qrcode
                    img = qrcode.make('TV26|' + student['qr_token'])
                    mem = io.BytesIO()
                    img.save(mem, format='PNG')
                    raw = mem.getvalue()
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/png')
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Content-Length', str(len(raw)))
                    self.end_headers()
                    return self.wfile.write(raw)
                except ImportError:
                    return self.reply(503, {'error':'Install qrcode[pil] to generate QR previews.'})
            return self.reply(404, {'error': 'Endpoint not found'})
        finally:
            conn.close()

    def do_POST(self):
        if not self.mutation_allowed():
            return self.reply(403, {'error': 'Unauthorized browser request'})
        try:
            payload = self.json_body()
            if not isinstance(payload, dict):
                raise ValueError('Expected a JSON object')
        except ValueError as e:
            return self.reply(400, {'error': str(e)})
        path = self.parsed().path
        conn = db()
        try:
            if path == '/api/setup':
                if self.client_address[0] not in ('127.0.0.1','::1'):
                    return self.reply(403, {'error':'Initial admin setup must be completed on the main laptop using localhost.'})
                conn.execute('BEGIN IMMEDIATE')
                if conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]:
                    conn.rollback()
                    return self.reply(409, {'error': 'Administrator already configured.'})
                password = str(payload.get('password', ''))
                if len(password) < 12 or len(password) > 128:
                    conn.rollback()
                    return self.reply(400, {'error': 'Use an administrator password of at least 12 characters.'})
                add_user(conn, 'admin', password, 'admin')
                audit(conn, 'system', 'setup', description='Initial administrator created', ip=self.client_address[0])
                conn.commit()
                return self.reply(200, {'ok': True, 'message': 'Administrator created. Sign in now.'})
            if path == '/api/login':
                username = str(payload.get('username', '')).strip().lower()
                password = str(payload.get('password', ''))
                address = self.client_address[0]
                key = (address, username)
                with LOCK:
                    recent = [t for t in FAILS.get(key, []) if time.time()-t<600]
                    FAILS[key] = recent
                    if len(recent) >= 8:
                        return self.reply(429, {'error':'Too many attempts. Try again in ten minutes.'})
                account = conn.execute('SELECT * FROM users WHERE username=? AND active=1', (username,)).fetchone()
                dummy = hash_pass(password, '00'*16)
                ok = bool(account and hmac.compare_digest(hash_pass(password, account['salt']), account['pass_hash']))
                if not ok:
                    with LOCK: FAILS.setdefault(key, []).append(time.time())
                    return self.reply(401, {'error':'Incorrect username or password.'})
                with LOCK: FAILS.pop(key, None)
                if account['role'] == 'admin' and not is_loopback(address):
                    return self.reply(403, {'error':'Administrator login is laptop-only. Use your separate phone staff username and password.'})
                device_id = self.device_cookie() or secrets.token_hex(24)
                label = str(payload.get('device_name','')).strip()[:60] or account['counter_name'] or 'Laptop admin'
                conn.execute("INSERT INTO phone_devices(id,user_id,label,ip,agent,last_seen) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET user_id=excluded.user_id,label=excluded.label,ip=excluded.ip,agent=excluded.agent,last_seen=excluded.last_seen",
                    (device_id,account['id'],label,address,self.headers.get('User-Agent','')[:180],time.time()))
                token = secrets.token_urlsafe(36)
                conn.execute('INSERT INTO sessions(token_hash,user_id,expires,device_id) VALUES(?,?,?,?)',
                             (hashlib.sha256(token.encode()).hexdigest(), account['id'], time.time()+SESSION_HOURS*3600,device_id))
                audit(conn, username, 'login', description='Signed in', ip=address)
                conn.commit()
                self.send_response(200)
                body = json.dumps({'ok':True,'role':account['role']}).encode()
                secure = '; Secure' if isinstance(self.request, __import__('ssl').SSLSocket) else ''
                self.send_header('Set-Cookie', f'tv_device={device_id}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000{secure}')
                self.send_header('Set-Cookie', f'tv_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_HOURS*3600}{secure}')
                self.send_header('Content-Type','application/json')
                self.send_header('Cache-Control','no-store')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
            user = self.user_required(conn)
            if not user:
                return
            if path in ('/api/local-camera/start', '/api/local-camera/stop'):
                if not is_loopback(self.client_address[0]):
                    return self.reply(403, {'error': 'Laptop webcam is restricted to localhost on the main event laptop.'})
                owner = hashlib.sha256(self.get_cookie().encode()).hexdigest()
                with LOCAL_CAMERA_LOCK:
                    active = LOCAL_CAMERA['capture'] is not None
                    if active and (time.monotonic() - LOCAL_CAMERA['last_activity'] > 75):
                        close_local_camera()
                        active = False
                    if path.endswith('/stop'):
                        if active and LOCAL_CAMERA['owner'] == owner:
                            close_local_camera()
                        return self.reply(200, {'ok': True})
                    if active:
                        if LOCAL_CAMERA['owner'] != owner:
                            return self.reply(409, {'error': 'The laptop camera is in use by another local browser session.'})
                        LOCAL_CAMERA['last_activity'] = time.monotonic()
                        return self.reply(200, {'ok': True})
                    try:
                        import cv2
                    except ImportError:
                        return self.reply(503, {'error': 'Install offline QR support first (opencv-python-headless and numpy). Run INSTALL_QR_SUPPORT_MAC_LINUX.sh or INSTALL_QR_SUPPORT_WINDOWS.bat with internet available once.'})
                    index = int(os.getenv('FOODDESK_CAMERA_INDEX', '0'))
                    capture = cv2.VideoCapture(index)
                    if not capture.isOpened():
                        capture.release()
                        return self.reply(503, {'error': 'No laptop webcam accessible. On Mac, allow camera access for Terminal/Python in System Settings → Privacy & Security → Camera. Check if another application is using it.'})
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                    LOCAL_CAMERA.update(capture=capture, owner=owner,
                                        decoder=cv2.QRCodeDetector(), last_activity=time.monotonic())
                    return self.reply(200, {'ok': True})
            if path == '/api/logout':
                conn.execute('UPDATE phone_devices SET last_seen=0 WHERE id=?',(user['device_id'],))
                conn.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(self.get_cookie().encode()).hexdigest(),))
                conn.commit()
                raw = b'{"ok":true}'
                self.send_response(200)
                self.send_header('Set-Cookie','tv_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict')
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(raw)))
                self.end_headers()
                return self.wfile.write(raw)
            if path == '/api/cancel-scan':
                token = clean_token(str(payload.get('token','')))
                conn.execute("UPDATE scan_requests SET status='cancelled' WHERE device_id=? AND token_hash=? AND status='valid'", (user['device_id'],hashlib.sha256(token.encode()).hexdigest()))
                conn.commit()
                return self.reply(200, {'ok':True})
            if path == '/api/heartbeat':
                conn.execute('UPDATE phone_devices SET last_seen=?,ip=? WHERE id=?', (time.time(),self.client_address[0],user['device_id']))
                conn.execute('''INSERT INTO devices(user_id,device_ip,last_seen,user_agent) VALUES(?,?,?,?)
                    ON CONFLICT(user_id,device_ip) DO UPDATE SET last_seen=excluded.last_seen,
                    user_agent=excluded.user_agent''',
                    (user['id'], self.client_address[0], time.time(), self.headers.get('User-Agent','')[:180]))
                conn.commit()
                return self.reply(200, {'ok':True, 'open': is_distribution_open(conn)})
            if path == '/api/local-test-qr/create':
                if user['role'] != 'admin':
                    return self.reply(403, {'error':'Only administrators can create test QRs.'})
                if not is_loopback(self.client_address[0]):
                    return self.reply(403, {'error':'For safety, generate test QRs on the event laptop via its localhost admin dashboard.'})
                try:
                    import qrcode
                    token, fields = make_local_test_qr(str(payload.get('meal','veg')))
                    img = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,
                                        box_size=9, border=4)
                    img.add_data(token)
                    img.make(fit=True)
                    buffer = io.BytesIO()
                    img.make_image(fill_color='black', back_color='white').save(buffer, format='PNG')
                    audit(conn,user['username'],'local_test_qr_created',reg_no=fields['reg'],
                          description=f'30 minute TEST ONLY, {fields["meal"]}; no real meal',ip=self.client_address[0])
                    conn.commit()
                    return self.reply(200, {'token':token,
                        'image':'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode('ascii'),
                        'expires_at':fields['exp'], 'meal':fields['meal'],
                        'message':'TEST ONLY — fake student; cannot authorize any real food.'})
                except ImportError:
                    return self.reply(503, {'error':'QR image support missing. Run the INSTALL_PHONE_HTTPS script once while internet is available to install qrcode[pil].'})
                except InvalidTestQR as exc:
                    return self.reply(400, {'error':str(exc)})
            if path == '/api/check':
                token = clean_token(str(payload.get('token','')))
                self.scan_context = (conn,user,token)
                if not token or len(token) > 2400:
                    return self.reply(400, {'error':'Please scan a valid food pass QR.'})
                if token.startswith(LOCAL_TEST_PREFIX+'.'):
                    try:
                        fields=verify_local_test_qr(token)
                        demo=conn.execute('SELECT * FROM demo_redemptions WHERE pass_id=?',(fields['id'],)).fetchone()
                        return self.reply(200, {'status':'used' if demo else 'valid', 'test_only':True,
                            'message':'TEST ONLY — already simulated; never give food.' if demo else 'TEST ONLY — do not give actual food. You can simulate a one-time redemption.',
                            'student':demo_public_student(fields,demo)})
                    except InvalidTestQR as exc:
                        return self.reply(200,{'status':'invalid','message':str(exc)})
                if token.startswith('TV26E2.'):
                    try:
                        fields=decode_secure_qr(token)
                        if fields['kind']=='demo':
                            if user['role']!='admin':
                                return self.reply(200, {'status':'blocked','message':'DEMO QR — not valid for real food counters.'})
                            test=conn.execute('SELECT * FROM demo_redemptions WHERE pass_id=?',(fields['id'],)).fetchone()
                            return self.reply(200, {'status':'used' if test else 'valid',
                              'message':'Demo was already simulated.' if test else 'DEMO ONLY — never give actual food.',
                              'student':demo_public_student(fields,test)})
                        row=ensure_encrypted_student(conn,fields)
                        conn.commit()
                    except (InvalidPass,sqlite3.IntegrityError) as e:
                        conn.rollback()
                        return self.reply(200, {'status':'invalid','message':str(e)})
                else:
                    row = conn.execute('SELECT * FROM students WHERE qr_token=?', (token,)).fetchone()
                if not row:
                    return self.reply(200, {'status':'invalid','message':'Invalid or possibly fake QR: this pass is not in the approved offline list. Do not give food.'})
                error = classroom_error(conn, row['student_year'])
                if error:
                    return self.reply(200, {'status':'blocked','message':error})
                student = public_student(row)
                if row['redeemed'] and not row['recollection_allowed']:
                    return self.reply(200, {'status':'used','message':'You already collected food at ' + format_ist(row['redeemed_at']) + '. Do not give food again.', 'student':student})
                if row['attendance'] != 'present' or row['pass_status'] != 'active':
                    return self.reply(200, {'status':'blocked','message':'Attendance not approved or pass revoked.', 'student':student})
                if not is_distribution_open(conn):
                    return self.reply(200, {'status':'closed', 'message':'Food distribution is currently closed by the administrator.', 'student':student})
                return self.reply(200, {'status':'valid','student':student})
            if path == '/api/redeem':
                token = clean_token(str(payload.get('token','')))
                if not token or len(token) > 2400:
                    return self.reply(400, {'error':'QR code is required'})
                conn.execute('BEGIN IMMEDIATE')
                row=None
                if token.startswith(LOCAL_TEST_PREFIX+'.'):
                    try:
                        fields=verify_local_test_qr(token)
                        demo=conn.execute('SELECT * FROM demo_redemptions WHERE pass_id=?',(fields['id'],)).fetchone()
                        if demo:
                            conn.rollback()
                            return self.reply(409, {'status':'used','test_only':True,
                                'error':'TEST already simulated at another scan. No food allowed.',
                                'student':demo_public_student(fields,demo)})
                        conn.execute('INSERT INTO demo_redemptions(pass_id,redeemed_at,redeemed_by) VALUES(?,?,?)',
                                     (fields['id'],now(),user['username']))
                        audit(conn,user['username'],'local_test_simulated',reg_no=fields['reg'],
                              description='TEST ONLY — simulated duplicate blocking. Never served food.',ip=self.client_address[0])
                        conn.commit()
                        demo=conn.execute('SELECT * FROM demo_redemptions WHERE pass_id=?',(fields['id'],)).fetchone()
                        return self.reply(200, {'status':'served','demo':True,'test_only':True,
                             'message':'TEST passed: simulated redemption. No food served or counted.',
                             'student':demo_public_student(fields,demo)})
                    except InvalidTestQR as exc:
                        conn.rollback()
                        return self.reply(403, {'status':'invalid','error':str(exc)})
                if token.startswith('TV26E2.'):
                    try:
                        fields=decode_secure_qr(token)
                        if fields['kind']=='demo':
                            if user['role']!='admin':
                                conn.rollback()
                                return self.reply(403,{'status':'blocked','error':'DEMO pass cannot serve real food.'})
                            test=conn.execute('SELECT * FROM demo_redemptions WHERE pass_id=?',(fields['id'],)).fetchone()
                            if test:
                                conn.rollback()
                                return self.reply(409,{'status':'used','error':'Demo already redeemed.',
                                   'student':demo_public_student(fields,test)})
                            conn.execute('INSERT INTO demo_redemptions(pass_id,redeemed_at,redeemed_by) VALUES(?,?,?)',
                                (fields['id'],now(),user['username']))
                            audit(conn,user['username'],'demo_simulated',reg_no=fields['reg'],
                                  description='DEMO QR simulated; no food authorized',ip=self.client_address[0])
                            conn.commit()
                            test=conn.execute('SELECT * FROM demo_redemptions WHERE pass_id=?',(fields['id'],)).fetchone()
                            return self.reply(200,{'status':'served','demo':True,
                                'message':'Demo redeemed — do NOT serve food.',
                                'student':demo_public_student(fields,test)})
                        row=ensure_encrypted_student(conn,fields)
                    except (InvalidPass,sqlite3.IntegrityError) as e:
                        conn.rollback()
                        return self.reply(403, {'status':'invalid','error':str(e)})
                if row is None:
                    row = conn.execute('SELECT * FROM students WHERE qr_token=?', (token,)).fetchone()
                if not row:
                    conn.rollback()
                    return self.reply(404, {'status':'invalid','error':'QR is not recognized.'})
                error = classroom_error(conn, row['student_year'])
                if error:
                    conn.rollback()
                    return self.reply(403, {'status':'blocked','error':error})
                if row['redeemed'] and not row['recollection_allowed']:
                    conn.rollback()
                    return self.reply(409, {'status':'used','error':'You already collected food at ' + format_ist(row['redeemed_at']) + '. Do not give food again.', 'student':public_student(row)})
                if row['attendance'] != 'present' or row['pass_status'] != 'active':
                    conn.rollback()
                    return self.reply(403, {'status':'blocked','error':'This pass is not authorized.', 'student':public_student(row)})
                if not is_distribution_open(conn):
                    conn.rollback()
                    return self.reply(423, {'status':'closed','error':'Distribution closed. Ask the administrator to open food counters.'})
                stock = meal_inventory(conn).get(row['food_type'])
                if stock and stock['remaining'] is not None and stock['remaining'] <= 0:
                    conn.rollback()
                    return self.reply(409, {'status':'blocked','error':'No ' + row['food_type'] + ' meals remaining. Ask the administrator to update meal quantities.'})
                counter = user['counter_name'] if user['role']=='counter' else 'Admin desk'
                timestamp = now()
                if row['redeemed']:
                    conn.execute('''INSERT INTO collection_archive(student_id,reg_no,name,food_type,redeemed_at,redeemed_by,redeemed_counter,redeemed_device)
                        VALUES(?,?,?,?,?,?,?,?)''', (row['id'],row['reg_no'],row['name'],row['food_type'],row['redeemed_at'],row['redeemed_by'],row['redeemed_counter'],row['redeemed_device']))
                updated = conn.execute('''UPDATE students SET redeemed=1, redeemed_at=?, redeemed_by=?, redeemed_counter=?, redeemed_device=?, recollection_allowed=0, collection_revision=collection_revision+1
                    WHERE id=? AND (redeemed=0 OR recollection_allowed=1) AND attendance='present' AND pass_status='active' ''',
                    (timestamp, user['id'], counter, user['device_id'], row['id']))
                if updated.rowcount != 1:
                    conn.rollback()
                    return self.reply(409, {'status':'used','error':'Another counter just redeemed this pass.'})
                conn.execute("UPDATE scan_requests SET status='served',message='Food given' WHERE token_hash=? AND status='valid'", (hashlib.sha256(token.encode()).hexdigest(),))
                audit(conn, user['username'], 'served', reg_no=row['reg_no'], description=f'{row["food_type"]} at {counter}', ip=self.client_address[0])
                conn.commit()
                return self.reply(200, {'status':'served', 'student': public_student(conn.execute('SELECT * FROM students WHERE id=?',(row['id'],)).fetchone())})
            if path == '/api/decode-photo':
                image64 = str(payload.get('image',''))
                if ',' in image64: image64 = image64.split(',',1)[1]
                if len(image64) > 7*1024*1024:
                    return self.reply(413, {'error':'Photo is too large.'})
                try:
                    import cv2
                    import numpy as np
                    img_bytes = base64.b64decode(image64, validate=True)
                    if len(img_bytes) > 5*1024*1024:
                        return self.reply(413, {'error':'Photo is too large.'})
                    img = cv2.imdecode(np.frombuffer(img_bytes,dtype=np.uint8), cv2.IMREAD_COLOR)
                    if img is None:
                        return self.reply(400, {'error':'Could not read image. Take another photo.'})
                    h,w = img.shape[:2]
                    if max(h,w)>1600:
                        scale = 1600/max(h,w)
                        img = cv2.resize(img,(int(w*scale),int(h*scale)))
                    token, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
                    if token:
                        return self.reply(200, {'token':token})
                    return self.reply(422, {'error':'No readable QR was found. Move closer, improve lighting and try again.'})
                except ImportError:
                    return self.reply(503, {'error':'Photo scanning requires opencv-python-headless and numpy installed before the event.'})
                except Exception:
                    return self.reply(400, {'error':'Unable to decode this photo. Try another.'})
            if user['role'] != 'admin':
                return self.reply(403, {'error':'Only administrators can change this setting.'})
            if path == '/api/distribution':
                requested = payload.get('open')
                if not isinstance(requested, bool):
                    return self.reply(400, {'error':'open must be true or false.'})
                conn.execute('BEGIN IMMEDIATE')
                status=status_snapshot(conn)
                if requested:
                    year = payload.get('year')
                    if year not in ('2','3','4'):
                        conn.rollback()
                        return self.reply(400, {'error':'Select this laptop’s year: 2nd, 3rd or 4th.'})
                    previous = classroom_setup(conn)
                    if previous['year'] and previous['year'] != year and conn.execute('SELECT COUNT(*) FROM students WHERE redeemed=1').fetchone()[0]:
                        conn.rollback()
                        return self.reply(409, {'error':'This laptop has already served meals. Keep its assigned year for this event.'})
                    quantities = payload.get('quantities')
                    if not isinstance(quantities, dict) or any(type(quantities.get(k)) is not int or not 0 <= quantities[k] <= 1000000 for k in ('VEG','NON-VEG')):
                        conn.rollback()
                        return self.reply(400, {'error':'Enter whole-number veg and non-veg meal quantities (0–1,000,000). Includes meals already served.'})
                    inventory = meal_inventory(conn)
                    if any(quantities[k] < inventory[k]['served'] for k in inventory) or sum(quantities.values()) == 0:
                        conn.rollback()
                        return self.reply(400, {'error':'Enter at least one meal. Totals cannot be below meals already served.'})
                    for key, value in [('classroom_year',year)]:
                        conn.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)', (key,value))
                    for meal, key in [('VEG','meal_veg'), ('NON-VEG','meal_nonveg')]:
                        conn.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)', (key,str(quantities[meal])))
                conn.execute("UPDATE settings SET value=? WHERE key='distribution_open'",('1' if requested else '0',))
                audit(conn,user['username'],'distribution_opened' if requested else 'distribution_closed',
                    description='Counter redemption gate changed',ip=self.client_address[0])
                conn.commit()
                return self.reply(200,{'ok':True,'open':requested})
            if path == '/api/create-counter':
                username = str(payload.get('username','')).strip().lower()
                display = str(payload.get('counter_name','')).strip()[:50]
                password = str(payload.get('password',''))
                if not re.fullmatch(r'[a-z0-9_-]{3,24}', username):
                    return self.reply(400, {'error':'Username: 3–24 lowercase letters, digits, _ or -.'})
                if not display or len(password) < 8 or len(password)>128:
                    return self.reply(400, {'error':'Provide a counter label and password of at least 8 characters.'})
                try:
                    add_user(conn, username, password, 'counter', display)
                    audit(conn, user['username'],'counter_added',description=username,ip=self.client_address[0])
                    conn.commit()
                    return self.reply(200, {'ok':True})
                except sqlite3.IntegrityError:
                    return self.reply(409, {'error':'Username already exists.'})
            if path == '/api/toggle-counter':
                username = str(payload.get('username','')).strip().lower()
                row = conn.execute("SELECT * FROM users WHERE username=? AND role='counter'",(username,)).fetchone()
                if not row:
                    return self.reply(404, {'error':'Counter not found.'})
                active = 0 if row['active'] else 1
                conn.execute('UPDATE users SET active=? WHERE id=?',(active,row['id']))
                if not active: conn.execute('DELETE FROM sessions WHERE user_id=?',(row['id'],))
                audit(conn,user['username'],'counter_changed',description=f'{username}: {"on" if active else "off"}',ip=self.client_address[0])
                conn.commit()
                return self.reply(200, {'ok':True})
            if path == '/api/change-admin-password':
                old = str(payload.get('old_password',''))
                new = str(payload.get('new_password',''))
                account = conn.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone()
                if not hmac.compare_digest(hash_pass(old,account['salt']),account['pass_hash']):
                    return self.reply(401, {'error':'Current password is incorrect.'})
                if len(new)<12 or len(new)>128:
                    return self.reply(400, {'error':'Use at least 12 characters.'})
                salt=secrets.token_hex(16)
                conn.execute('UPDATE users SET salt=?,pass_hash=? WHERE id=?',(salt,hash_pass(new,salt),user['id']))
                conn.execute('DELETE FROM sessions WHERE user_id=? AND token_hash!=?',(user['id'],hashlib.sha256(self.get_cookie().encode()).hexdigest()))
                audit(conn,user['username'],'password_changed',ip=self.client_address[0])
                conn.commit()
                return self.reply(200,{'ok':True})
            if path in ('/api/revoke', '/api/restore-collection'):
                if not is_loopback(self.client_address[0]):
                    return self.reply(403, {'error':'Pass changes require the administrator on the main laptop.'})
                attempt_key = ('restore-pin', user['id'])
                with LOCK:
                    recent = [t for t in FAILS.get(attempt_key, []) if time.time()-t<600]
                    FAILS[attempt_key] = recent
                    if len(recent) >= 5:
                        return self.reply(429, {'error':'Too many incorrect PIN attempts. Try again in ten minutes.'})
                pin = payload.get('pin', '')
                if not isinstance(pin,str) or len(pin)>128 or not hmac.compare_digest(hash_pass(pin, RESTORE_PIN_SALT), RESTORE_PIN_HASH):
                    with LOCK:
                        FAILS.setdefault(attempt_key, []).append(time.time())
                    return self.reply(403, {'error':'Incorrect administrator PIN. Pass was not changed.'})
                with LOCK:
                    FAILS.pop(attempt_key, None)
            if path == '/api/restore-collection':
                conn.execute('BEGIN IMMEDIATE')
                reg = str(payload.get('reg_no','')).strip()
                row = conn.execute('SELECT * FROM students WHERE reg_no=?',(reg,)).fetchone()
                if not row:
                    conn.rollback()
                    return self.reply(404, {'error':'Student not found.'})
                if row['recollection_allowed']:
                    conn.rollback()
                    return self.reply(409, {'error':'QR is already restored for one collection. Ask the counter to scan it.'})
                if not row['redeemed'] or type(payload.get('revision')) is not int or payload['revision'] != row['collection_revision']:
                    conn.rollback()
                    return self.reply(409, {'error':'Collection status changed. Refresh the student directory and try again.'})
                if row['attendance'] != 'present':
                    conn.rollback()
                    return self.reply(409, {'error':'Student attendance must be approved before restoring the QR.'})
                conn.execute("UPDATE students SET recollection_allowed=1,pass_status='active',collection_revision=collection_revision+1 WHERE id=?",(row['id'],))
                audit(conn,user['username'],'collection_restored',reg_no=reg,
                    description='Admin PIN approved one additional collection. Previous collection: '+format_ist(row['redeemed_at']),ip=self.client_address[0])
                conn.commit()
                return self.reply(200, {'ok':True,'message':'QR restored. The counter may scan this pass for one more collection.'})
            if path == '/api/revoke':
                conn.execute('BEGIN IMMEDIATE')
                reg = str(payload.get('reg_no','')).strip()
                row = conn.execute('SELECT * FROM students WHERE reg_no=?',(reg,)).fetchone()
                if not row: return self.reply(404,{'error':'Student not found.'})
                if row['redeemed']:
                    return self.reply(409,{'error':'Use Restore QR with the administrator PIN to allow one more collection.'})
                new_status = 'active' if row['pass_status']=='revoked' else 'revoked'
                conn.execute('UPDATE students SET pass_status=? WHERE id=?',(new_status,row['id']))
                audit(conn,user['username'],'pass_'+new_status,reg_no=reg,ip=self.client_address[0])
                conn.commit()
                return self.reply(200,{'ok':True,'pass_status':new_status})
            if path == '/api/import':
                return self.handle_import(conn, user, payload)
            return self.reply(404, {'error': 'Endpoint not found.'})
        except sqlite3.OperationalError as ex:
            try: conn.rollback()
            except sqlite3.Error: pass
            return self.reply(503, {'error':'Database busy or unavailable. Retry. ('+str(ex)[:120]+')'})
        except Exception:
            # Return an explicit error rather than dropping the HTTP connection.
            # Do not include the request payload, QR token, PIN or secret keys.
            detail = traceback.format_exc()
            self.scan_context = None
            try: conn.rollback()
            except sqlite3.Error: pass
            reference = secrets.token_hex(4)
            try:
                DATA.mkdir(parents=True,exist_ok=True)
                with (DATA / 'request-error.log').open('a',encoding='utf-8') as stream:
                    stream.write('\n'+now()+' '+reference+' '+path+'\n'+detail)
                advice = 'See app/data/request-error.log on the laptop.'
            except OSError:
                advice = 'The error log could not be saved. Check folder write access.'
            print('Food Desk request failed. Reference: '+reference)
            return self.reply(500, {'status':'unavailable','error':'The laptop could not complete this request. Reference '+reference+'. '+advice+' If this was a collection request, scan again to check whether it was saved.'})
        finally:
            conn.close()

    def handle_import(self, conn, user, payload):
        try:
            csv_text = str(payload.get('csv',''))
            if not csv_text or len(csv_text.encode('utf-8')) > 6*1024*1024:
                return self.reply(400, {'error':'CSV must be 6 MB or less.'})
            csv_text=csv_text.lstrip('\ufeff')
            reader=csv.DictReader(io.StringIO(csv_text))
            if not reader.fieldnames:
                return self.reply(400, {'error':'CSV has no headers.'})
            reader.fieldnames=[(s or '').strip().lower() for s in reader.fieldnames]
            missing=[s for s in REQUIRED_COLS if s not in reader.fieldnames]
            if missing: return self.reply(400, {'error':'Missing columns: '+', '.join(missing)})
            rows=[]; issues=[]; seen_reg=set(); seen_tokens=set()
            for idx, raw in enumerate(reader, 2):
                if idx>10002:
                    return self.reply(400, {'error':'Maximum 10,000 records per import.'})
                if not any(str(v or '').strip() for v in raw.values()): continue
                try:
                    reg=(raw['register_number'] or '').strip()
                    name=(raw['student_name'] or '').strip()
                    dept=(raw['department'] or '').strip()
                    section=(raw['section'] or '').strip()
                    email=(raw['email'] or '').strip()
                    meal=(raw['food_type'] or '').strip().upper().replace(' ','').replace('_','').replace('-','')
                    meal='NON-VEG' if meal in ('NONVEG','NONVEGETARIAN','NV') else ('VEG' if meal in ('VEG','VEGETARIAN','V') else '')
                    attendance=(raw['attendance_status'] or '').strip().lower()
                    token=clean_token(raw['qr_token'] or '')
                    if not re.fullmatch(r'[A-Za-z0-9_-]{3,40}',reg): raise ValueError('invalid register number')
                    if not name or len(name)>120: raise ValueError('student name missing/too long')
                    if len(dept)>80 or len(section)>40 or len(email)>180: raise ValueError('field too long')
                    if not meal: raise ValueError('food_type must be Veg or Non-Veg')
                    if attendance not in ('present','absent'): raise ValueError('attendance_status must be present or absent')
                    if not token and attendance == 'absent':
                        token = None  # absent students need not have an emailed pass
                    elif len(token)<20 or len(token)>256 or not re.fullmatch(r'[a-zA-Z0-9._~+-]+',token):
                        raise ValueError('present students need a secure 20–256 character qr_token')
                    if reg in seen_reg or (token and token in seen_tokens):
                        raise ValueError('duplicate register number or QR token in CSV')
                    seen_reg.add(reg)
                    if token: seen_tokens.add(token)
                    rows.append((reg,name,dept,section,email,meal,attendance,token))
                except (ValueError, KeyError, AttributeError) as e:
                    issues.append(f'Row {idx}: {e}')
            if issues:
                return self.reply(400, {'error':f'Import cancelled: {len(issues)} invalid row(s). Nothing changed.', 'issues':issues[:12]})
            if not rows: return self.reply(400,{'error':'No valid student records.'})
            conn.execute('BEGIN IMMEDIATE')
            created=updated=preserved=0
            for reg,name,dept,section,email,meal,attendance,token in rows:
                existing=conn.execute('SELECT * FROM students WHERE reg_no=?',(reg,)).fetchone()
                if existing:
                    if token is None:
                        token = existing['qr_token']
                    if existing['qr_token'] != token and not existing['qr_token'].startswith('NOQR_ABSENT_'):
                        raise ValueError(f'{reg}: QR token changed for an existing student. Keep the originally emailed token.')
                    # Only permit a never-emailed absent placeholder to be replaced with the real website token.
                    if existing['qr_token'] != token:
                        conn.execute('UPDATE students SET qr_token=? WHERE id=?', (token, existing['id']))
                    # Never erase any serving log or undo a revocation through importing again.
                    conn.execute('''UPDATE students SET name=?,department=?,section=?,email=?,food_type=?,attendance=?,imported_at=?
                        WHERE id=?''',(name,dept,section,email,meal,attendance,now(),existing['id']))
                    updated+=1
                    if existing['redeemed']: preserved+=1
                else:
                    if token is None:
                        token = 'NOQR_ABSENT_' + secrets.token_urlsafe(24)
                    conn.execute('''INSERT INTO students(reg_no,name,department,section,email,food_type,attendance,qr_token,imported_at)
                        VALUES(?,?,?,?,?,?,?,?,?)''',(reg,name,dept,section,email,meal,attendance,token,now()))
                    created+=1
            audit(conn,user['username'],'csv_import',description=f'{created} new, {updated} updated; {preserved} redeemed preserved',ip=self.client_address[0])
            conn.commit()
            return self.reply(200,{'ok':True,'created':created,'updated':updated,'preserved':preserved,
                'message':f'Imported {len(rows)} students. Existing redemptions and revocations preserved.'})
        except (ValueError,sqlite3.IntegrityError) as e:
            conn.rollback()
            return self.reply(409, {'error':'Import cancelled; no partial changes. '+str(e)[:200]})


def main():
    global TLS_CERT, TLS_KEY, SCHEME, AUTO_HTTPS
    auto_https = False
    if HOST not in ('127.0.0.1', 'localhost', '::1') and not TLS_CERT and not TLS_KEY:
        # Never silently serve logins or signed food-pass tokens over plain
        # HTTP on LAN. Users can run localhost-only in HTTP mode instead.
        from local_https import ensure_certificates
        try:
            profile = ensure_certificates(local_ips())
        except (RuntimeError, OSError, ValueError) as exc:
            raise SystemExit('Phone HTTPS setup failed: ' + str(exc))
        TLS_CERT, TLS_KEY = profile['cert'], profile['key']
        SCHEME = 'https'
        auto_https = True
        AUTO_HTTPS = True
        print('   Offline HTTPS certificates ready. CA SHA256: ' + profile['fingerprint'])
        if profile['renewed_server']:
            print('   HTTPS server certificate created/updated for current Wi-Fi IP addresses.')
    if bool(TLS_CERT) != bool(TLS_KEY):
        raise SystemExit('Trusted LAN HTTPS needs both FOODDESK_TLS_CERT and FOODDESK_TLS_KEY.')
    init_db()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    httpd.daemon_threads = True
    if SCHEME == 'https':
        tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            tls_context.load_cert_chain(certfile=TLS_CERT, keyfile=TLS_KEY)
            httpd.socket = tls_context.wrap_socket(httpd.socket, server_side=True)
        except (OSError, ssl.SSLError) as exc:
            httpd.server_close()
            raise SystemExit('Unable to start trusted LAN HTTPS: ' + str(exc))
    print('\n' + '=' * 60)
    print('   TECHVISTRA 26  |  LAPTOP OFFLINE SERVER  |  v7.0')
    print('=' * 60)
    print(f'   This laptop:  {"http://localhost:" + str(LOOPBACK_PORT) if auto_https else SCHEME + "://localhost:" + str(PORT)}')
    if SCHEME == 'https': print('   Trusted HTTPS enabled; phones must trust the local issuing CA.')
    if HOST not in ('127.0.0.1', 'localhost', '::1'):
        for address in local_ips():
            print(f'   Counter phone: {SCHEME}://{address}:{PORT}')
    if auto_https:
        print(f'   PUBLIC certificate setup page (HTTP, no login): port {PHONE_SETUP_PORT}')
        for ip in local_ips():
            print(f'   Phone SETUP: http://{ip}:{PHONE_SETUP_PORT}/')
    print('   LAPTOP ONLY: use a USB QR reader with localhost (NO network).')
    print('   MULTI COUNTER: use a private Wi-Fi router/hotspot (NO internet).')
    print('   Server mode:', 'LAPTOP ONLY - loopback' if HOST in ('127.0.0.1','localhost','::1') else 'PRIVATE LAN - all local adapters')
    print('   First setup must be done on this laptop, using localhost.')
    print('   Press CTRL+C to stop. Keep the laptop awake.')
    print('=' * 60 + '\n')
    setup_server = None
    local_admin = None
    if auto_https:
        # Loopback HTTP remains a trustworthy localhost origin for browsers.
        # Avoids asking the operator to trust the event CA on the laptop itself;
        # the phone-facing application is HTTPS-only. This port is NOT on LAN.
        try:
            local_admin = ThreadingHTTPServer(('127.0.0.1', LOOPBACK_PORT), Handler)
            local_admin.daemon_threads = True
            threading.Thread(target=local_admin.serve_forever, daemon=True,
                             name='localhost-admin-without-cert').start()
            print(f'   Local laptop admin (loopback ONLY): http://localhost:{LOOPBACK_PORT}/')
        except OSError as exc:
            httpd.server_close()
            raise SystemExit(f'Local admin port {LOOPBACK_PORT} unavailable: {exc}')
    if auto_https:
        # Public setup server deliberately has no authentication endpoint,
        # student data or TLS private key access. Never type passwords there.
        try:
            from phone_https_setup import make_setup_server
            setup_server = make_setup_server(HOST, PHONE_SETUP_PORT, PORT, local_ips())
            threading.Thread(target=setup_server.serve_forever, daemon=True,
                             name='public-phone-cert-onboarding').start()
            print(f'   Phone onboarding available on port {PHONE_SETUP_PORT}.')
        except OSError as exc:
            print(f'   WARNING: Phone onboarding port is unavailable: {exc}')
            print('   HTTPS scanner still works; share the public CA certificate by AirDrop/USB.')
    try: httpd.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt: print('\nStopping offline food desk.')
    finally:
        with LOCAL_CAMERA_LOCK:
            close_local_camera()
        httpd.server_close()
        if local_admin:
            local_admin.shutdown()
            local_admin.server_close()
        if setup_server:
            setup_server.shutdown()
            setup_server.server_close()


if __name__ == '__main__':
    main()
