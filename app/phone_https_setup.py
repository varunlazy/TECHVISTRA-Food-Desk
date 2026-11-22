#!/usr/bin/env python3
"""LAN onboarding page: PUBLIC CA certificate only, never the application.

Runs on port 8788 (HTTP) solely so an untrusted phone can download the public
certificate before connecting to the main HTTPS server on port 8787.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
from io import BytesIO
import plistlib
import uuid
from urllib.parse import urlparse
import ipaddress

from local_https import CA_PEM, CA_DER, fingerprint


def private_ip(value):
    try:
        ip = ipaddress.ip_address(value)
        return ip.is_private or ip.is_link_local or ip.is_loopback
    except ValueError:
        return False


def make_setup_server(host, port, https_port, addresses):
    allowed = [str(v) for v in addresses if private_ip(v)]
    fingerprint_str = fingerprint()

    class Setup(BaseHTTPRequestHandler):
        server_version = 'TechvistraPhoneSetup/1.0'

        def log_message(self, fmt, *args):
            print('Phone setup:', self.client_address[0], fmt % args)

        def send(self, data, kind, filename=None):
            self.send_response(200)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; base-uri 'none'; form-action 'none'")
            if filename:
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == '/TECHVISTRA-Phone-CA.mobileconfig':
                cert = CA_DER.read_bytes()
                ca_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, 'techvistra-ca-' + fingerprint_str))
                profile = {
                    'PayloadType': 'Configuration', 'PayloadVersion': 1,
                    'PayloadIdentifier': 'org.techvistra.fooddesk.phoneca.profile',
                    'PayloadUUID': str(uuid.uuid5(uuid.NAMESPACE_DNS, 'techvistra-profile-' + fingerprint_str)),
                    'PayloadDisplayName': 'TECHVISTRA Offline Phone CA',
                    'PayloadDescription': 'Private event-laptop CA for local HTTPS QR scanning. Remove after the event.',
                    'PayloadOrganization': 'TECHVISTRA 26', 'PayloadRemovalDisallowed': False,
                    'PayloadContent': [{
                        'PayloadType': 'com.apple.security.root', 'PayloadVersion': 1,
                        'PayloadIdentifier': 'org.techvistra.fooddesk.phoneca', 'PayloadUUID': ca_uuid,
                        'PayloadDisplayName': 'TECHVISTRA Offline Phone CA',
                        'PayloadCertificateFileName': 'TECHVISTRA-Phone-CA.cer',
                        'PayloadContent': cert,
                    }],
                }
                return self.send(plistlib.dumps(profile), 'application/x-apple-aspen-config')
            if path == '/TECHVISTRA-Phone-CA.cer':
                return self.send(CA_DER.read_bytes(), 'application/x-x509-ca-cert', 'TECHVISTRA-Phone-CA.cer')
            if path == '/TECHVISTRA-Phone-CA.crt':
                return self.send(CA_PEM.read_bytes(), 'application/x-x509-ca-cert', 'TECHVISTRA-Phone-CA.crt')
            if path == '/scanner-qr.png' or path == '/setup-qr.png':
                try:
                    import qrcode
                    ip = allowed[0] if allowed else '127.0.0.1'
                    text = f'https://{ip}:{https_port}/' if path == '/scanner-qr.png' else f'http://{ip}:{port}/'
                    qr = qrcode.QRCode(box_size=6, border=3)
                    qr.add_data(text)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color='#122b52', back_color='white')
                    buf = BytesIO(); img.save(buf, format='PNG')
                    return self.send(buf.getvalue(), 'image/png')
                except ImportError:
                    return self.send(b'QR generator not installed', 'text/plain; charset=utf-8')
            if path not in ('/', '/index.html'):
                self.send_error(404, 'Setup resources only')
                return
            safe_ips = ''.join(f'<li><a href="https://{escape(ip)}:{https_port}/">https://{escape(ip)}:{https_port}/</a></li>' for ip in allowed)
            page = '''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TECHVISTRA Phone QR Setup</title>
<style>*{box-sizing:border-box}body{font:16px/1.55 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:0;background:#eef3fd;color:#172b47}
main{max-width:660px;margin:auto;padding:24px 16px 48px}header{background:#122b52;color:white;padding:24px;border-radius:18px}
h1{font-size:24px;line-height:1.2;margin:8px 0}h2{font-size:19px;margin:12px 0}section{background:white;border-radius:15px;margin-top:16px;padding:18px 20px;box-shadow:0 3px 20px #001d3a0c}
a.btn{display:block;text-align:center;background:#1955d4;color:white;border-radius:12px;padding:13px;text-decoration:none;font-weight:700;margin:12px 0}
small{color:#596b82}code{overflow-wrap:anywhere}li{margin:7px 0}img{max-width:180px;border-radius:8px;border:1px solid #dae3f3}</style></head><body><main>
<header><small style="color:#bed0ef">OFFLINE • NO INTERNET REQUIRED</small><h1>TECHVISTRA '26<br>Phone Live QR Scanner</h1>Connect this phone to the SAME private Wi-Fi as the food-desk laptop.</header>
<section><h2>1. Install the trusted event certificate</h2><p>Download the PUBLIC certificate on each staff phone. This is required once per phone.</p>
<a class="btn" href="/TECHVISTRA-Phone-CA.mobileconfig">Install iPhone certificate profile</a>
<a class="btn" href="/TECHVISTRA-Phone-CA.crt">Download certificate · Android</a>
<small><b>Check the certificate fingerprint</b> against the event laptop BEFORE trusting it. A private CA can issue trusted certificates; only install on authorized staff devices.</small>
<p><code>%%FINGERPRINT%%</code></p></section>
<section><h2>2. Trust certificate on your phone</h2>
<p><b>iPhone (Safari):</b> Allow the configuration-profile download (the profile is unsigned). Open Settings → General → VPN &amp; Device Management → Downloaded Profile, then Install. Next open Settings → General → About → Certificate Trust Settings and enable full trust for TECHVISTRA Offline Phone CA.</p>
<p><b>Android (Chrome):</b> Download the .crt file. Open Settings → Security &amp; privacy → More security settings → Encryption &amp; credentials → Install a certificate → CA certificate (names vary by Android version). Select the downloaded file and confirm. You may need a device screen lock.</p>
<p><small>Some managed phones disallow installing a user CA. Those devices require an administrator or the native scanner app.</small></p></section>
<section><h2>3. Start the LIVE camera scanner</h2><img src="/scanner-qr.png" alt="QR link to the secure scanner">
<ul>%%ADDRESSES%%</ul><p>Open the HTTPS address, sign in as a counter staff member, tap <b>Start live camera</b>, and allow camera access.</p>
<p><small>If you see a certificate warning, DO NOT bypass it. Confirm certificate trust, laptop date/time, and Wi-Fi IP address. Do not log in on plain HTTP.</small></p></section>
<section><h2>After the event</h2><p>Remove the TECHVISTRA Offline Phone CA from each staff device's trusted certificates. Keep the laptop's private CA key and server key secret.</p>
<small>This HTTP page only shares the PUBLIC certificate and setup instructions, never student records or passwords.</small></section>
</main></body></html>'''
            page = page.replace('%%FINGERPRINT%%', escape(fingerprint_str)).replace('%%ADDRESSES%%', safe_ips)
            self.send(page.encode('utf-8'), 'text/html; charset=utf-8')

        def do_POST(self):
            self.send_error(405, 'Read-only setup page')

    server = ThreadingHTTPServer((host, port), Setup)
    server.daemon_threads = True
    return server
