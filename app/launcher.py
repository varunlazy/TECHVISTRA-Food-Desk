"""Shared checks for the four platform entry points. No downloads during open."""
from pathlib import Path
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
import traceback
import ssl
import sqlite3
ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

def main():
    setup = '--setup' in sys.argv
    if sys.version_info < (3,10):
        raise SystemExit('Python 3.10 or newer is required. Run Install & Setup again.')
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if setup:
        if python.exists():
            probe = subprocess.run([str(python), '-c', 'import sys; assert sys.version_info >= (3,10)'], capture_output=True)
            if probe.returncode:
                backup = ROOT / ('.venv-backup-' + str(time.time_ns()))
                (ROOT / '.venv').rename(backup)
                print('Preserved unusable Python environment at ' + str(backup))
        elif (ROOT / '.venv').exists():
            (ROOT / '.venv').rename(ROOT / ('.venv-backup-' + str(time.time_ns())))
        if not python.exists():
            subprocess.run([sys.executable,'-m','venv',str(ROOT/'.venv')],check=True)
        subprocess.run([str(python),'-m','ensurepip','--upgrade'],check=True)
        subprocess.run([str(python),'-m','pip','install','--retries','2','--timeout','30','-r',str(ROOT/'requirements.txt')],check=True)
    if not python.exists():
        raise SystemExit('Setup missing. Run the Install & Setup file first while connected to internet.')
    # On macOS bin/python is a symlink to system Python. Resolving that
    # executable erases the environment identity; sys.prefix retains it.
    if Path(sys.prefix).absolute() != (ROOT / '.venv').absolute():
        args = [str(python), str(Path(__file__).absolute()), '--open']
        if '--check-only' in sys.argv:
            args.append('--check-only')
        return subprocess.run(args).returncode
    try:
        import cryptography, cv2, numpy, qrcode
    except (ImportError, OSError) as exc:
        raise RuntimeError('QR/HTTPS dependency check failed: ' + str(exc) +
                           '. Run Install and Setup with internet to repair this environment.') from exc
    from configure_secure_qr import ensure_configuration
    ensure_configuration(check_only='--check-only' in sys.argv)
    from server import local_ips, init_db, db
    from local_https import ensure_certificates
    print('Using Python environment: ' + sys.prefix)
    init_db()
    with db() as conn:
        if conn.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise SystemExit('Database check failed. Restore a known-good backup before serving food.')
    # Detect an already-running desk through the authenticated app's public session route.
    url='http://127.0.0.1:8789/'
    try:
        with urllib.request.urlopen(url+'api/session',timeout=2) as response:
            status=json.load(response)
        if 'setup_required' in status:
            print('Food desk already running. Opening laptop dashboard.')
            webbrowser.open(url)
            return 0
    except (OSError,ValueError):
        pass
    for port in (8787,8788,8789):
        with socket.socket() as probe:
            # Match ThreadingHTTPServer: recently closed connections must not block restart.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try: probe.bind(('0.0.0.0',port))
            except OSError: raise SystemExit(f'Port {port} is busy. Close the other application or existing desk, then retry.')
    profile=ensure_certificates(local_ips())
    print('Database OK; QR/photo decoder OK; HTTPS certificates OK.')
    print('Phone certificate fingerprint: '+profile['fingerprint'])
    if '--check-only' in sys.argv:
        print('CHECK PASSED. QR configuration, dependencies, database, ports and HTTPS are ready.')
        return 0
    print('Keep this window open. Press Ctrl+C to stop. Keep the laptop awake.')
    # Launch only after the server answers; keep errors visible in this console.
    import threading
    def open_ready():
        for _ in range(60):
            try:
                with urllib.request.urlopen(url+'api/session',timeout=1): pass
                if not webbrowser.open(url):
                    print('Open this address manually: ' + url)
                return
            except OSError: time.sleep(.5)
        print('Server did not become ready. Review the error above.')
    threading.Thread(target=open_ready,daemon=True).start()
    from server import main as serve
    serve()

def run():
    try:
        return main() or 0
    except KeyboardInterrupt:
        print('Food desk stopped. Saved records remain in app/data.')
        return 0
    except (Exception, SystemExit) as exc:
        if isinstance(exc, SystemExit) and exc.code in (None, 0):
            return 0
        detail = str(exc)
        if isinstance(exc, PermissionError):
            advice = 'Extract the whole ZIP into a writable folder such as Downloads. Keep app beside the four launch files.'
        elif isinstance(exc, sqlite3.DatabaseError):
            advice = 'Stop all desk windows. Preserve app/data and restore a known-good database backup. Setup will not delete your records.'
        elif isinstance(exc, ssl.SSLError):
            advice = 'Check laptop date/time and the certificate files in app/data. Keep private keys and existing data; see the log for the failing file.'
        elif isinstance(exc, subprocess.CalledProcessError):
            advice = 'Review the package-install message above. Check internet, available disk space and Python 3.10+. Rerun Install and Setup. Saved data is preserved.'
        elif 'configuration' in detail.lower() or 'qr setup' in detail.lower():
            advice = 'Run Setup Website QR and import the matching JSON. Then run Check and Open again.'
        elif 'busy' in detail.lower() or 'address already in use' in detail.lower():
            advice = 'Close another Food Desk window or the application using the reported port, then run Check and Open. Do not delete app/data.'
        else:
            advice = 'Run Install and Setup with internet to repair dependencies. If it still fails, share the error log below.'
        print('\nFood Desk could not start: ' + detail + '\n' + advice)
        try:
            log = ROOT / 'data' / 'startup-error.log'
            log.parent.mkdir(exist_ok=True)
            with log.open('a', encoding='utf-8') as stream:
                stream.write('\n' + time.strftime('%Y-%m-%d %H:%M:%S') + '\n' + traceback.format_exc())
            print('Error log: ' + str(log))
        except OSError:
            print('The error log could not be saved. Copy the message from this window.')
        return 1

if __name__=='__main__':
    sys.exit(run())
