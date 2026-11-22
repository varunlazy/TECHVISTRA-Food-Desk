#!/usr/bin/env python3
"""Private TV26E2 setup: import one JSON file or enter website values locally."""
import base64
import getpass
import json
import os
from pathlib import Path
import shlex
import sys
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'data' / 'offline-qr-private.json'


class SetupError(ValueError):
    """A safe diagnostic that never echoes the secret encryption key."""


def setup_failure(exc):
    if isinstance(exc, SetupError):
        return str(exc)
    if isinstance(exc, ImportError):
        return 'Cryptography is missing or cannot load in this Python. Run Install and Setup, then use Setup Website QR.'
    if isinstance(exc, PermissionError):
        return 'Cannot read or write setup files. Use a writable folder and close files locking the configuration.'
    if isinstance(exc, FileNotFoundError):
        return 'File not found. Check the JSON or PEM path on THIS laptop. Mac /Users paths do not work on Windows.'
    if isinstance(exc, OSError):
        return 'File access failed. Check file paths and keep the app drive connected and writable.'
    return 'Setup validation failed. Check the JSON, 32-byte base64 AES key and P-256 public PEM.'


def read_public_pem(path):
    path = Path(path).expanduser()
    if not path.is_file():
        raise SetupError('Public PEM not found. Use the actual PEM path on THIS laptop, not a Mac /Users path on Windows.')
    if path.stat().st_size > 65536:
        raise SetupError('Public PEM file is too large. Select the website public key file.')
    try:
        return path.read_text(encoding='utf-8-sig').strip()
    except UnicodeError:
        raise SetupError('Public key file must be a text PEM file.') from None


def load_settings(source):
    source = Path(source).expanduser().resolve()
    if source.suffix.lower() != '.json':
        raise SetupError('JSON import needs a .json file. To use an AES key and .pem file, choose MANUAL.')
    if source.stat().st_size > 65536:
        raise ValueError('Setup JSON is too large.')
    try:
        settings = json.loads(source.read_text(encoding='utf-8-sig'))
    except (json.JSONDecodeError, UnicodeError):
        raise SetupError('Invalid JSON. Windows paths in JSON must use forward slashes or doubled backslashes.') from None
    if isinstance(settings, dict):
        pem = settings.get('public_pem')
        if isinstance(pem, str) and not pem.strip().startswith('-----BEGIN PUBLIC KEY-----'):
            pem_path = Path(pem.strip()).expanduser()
            if not pem_path.is_absolute():
                pem_path = source.parent / pem_path
            settings['public_pem'] = read_public_pem(pem_path)
    return validate_settings(settings)


def validate_settings(settings):
    if not isinstance(settings, dict):
        raise SetupError('Expected a JSON object containing aes_key_b64 and public_pem.')
    key = settings.get('aes_key_b64')
    pem = settings.get('public_pem')
    try:
        valid_key = isinstance(key,str) and len(base64.b64decode(key.strip(), validate=True)) == 32
    except ValueError:
        valid_key = False
    if not valid_key:
        raise SetupError('AES key is missing or invalid. Paste the matching website base64 key; it must decode to exactly 32 bytes.')
    if not isinstance(pem, str):
        raise SetupError('Missing public_pem in JSON.')
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    try:
        public = serialization.load_pem_public_key(pem.strip().encode('ascii'))
    except (ValueError, UnicodeError):
        raise SetupError('Invalid public PEM contents. Select the website BEGIN PUBLIC KEY file, not a certificate or private key.') from None
    if not isinstance(public, ec.EllipticCurvePublicKey) or not isinstance(public.curve, ec.SECP256R1):
        raise SetupError('Wrong key type. Website verification needs a P-256 public key, not RSA or another curve.')
    return {'aes_key_b64': key.strip(), 'public_pem': pem.strip() + '\n'}


def save_settings(settings, destination=CONFIG):
    settings = validate_settings(settings)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destination.parent, delete=False) as f:
            temporary = Path(f.name)
            os.chmod(temporary, 0o600)
            json.dump(settings, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def configuration_status(destination=None):
    destination = CONFIG if destination is None else Path(destination)
    try:
        if not destination.is_file():
            return {'website_qr_configured': False, 'message': 'QR configuration is missing. Run Setup Website QR and import your JSON.'}
        # Stored settings must contain the PEM itself, so the source file can be removed.
        validate_settings(json.loads(destination.read_text(encoding='utf-8-sig')))
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        settings = json.loads(destination.read_text(encoding='utf-8-sig'))
        aes = AESGCM(base64.b64decode(settings['aes_key_b64']))
        nonce = os.urandom(12)
        assert aes.decrypt(nonce, aes.encrypt(nonce, b'configuration-check', b'TV26E2'), b'TV26E2') == b'configuration-check'
        return {'website_qr_configured': True, 'message': 'Configuration and local encryption check passed. Scan a fresh website QR to confirm the website keys match.'}
    except ImportError:
        return {'website_qr_configured': False, 'message': 'QR library is missing. Run Install and Setup, then Setup Website QR.'}
    except Exception:
        return {'website_qr_configured': False, 'message': 'QR configuration is invalid or unreadable. Run Setup Website QR again with the matching JSON and PEM.'}


def ensure_configuration(check_only=False):
    while True:
        status = configuration_status()
        print(status['message'])
        if status['website_qr_configured']:
            return
        if check_only:
            raise RuntimeError('QR configuration check failed. Run Setup Website QR, then check again.')
        try:
            answer = input('Set up QR configuration now? [Enter = setup / Q = quit]: ').strip()
        except EOFError:
            raise RuntimeError('QR setup requires an interactive terminal. Run Setup Website QR.') from None
        if answer.lower() == 'q':
            raise SystemExit('QR configuration is required. Run Setup Website QR before opening the desk.')
        try:
            main()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit('QR setup cancelled. Run Setup Website QR before opening the desk.')
        except Exception as exc:
            print('Configuration setup failed: ' + setup_failure(exc))


def main():
    print('TECHVISTRA Website QR · private laptop setup')
    print('Use the SAME private setup JSON on all three food laptops. Never upload it publicly.')
    print('Python:', sys.executable)
    from cryptography.hazmat.primitives import serialization
    if len(sys.argv) == 3 and sys.argv[1] == '--file':
        source = Path(sys.argv[2]).expanduser()
    else:
        mode = input('Press Enter to import ONE setup JSON, or type MANUAL for separate values: ').strip()
        source = None
        if mode and mode.upper() != 'MANUAL':
            raise SetupError('Press Enter for JSON or type MANUAL here. Paste the AES key only at the hidden encryption-key prompt.')
        if mode.upper() != 'MANUAL':
            value = input('Drag the private setup JSON here, then press Enter: ').strip()
            if os.name == 'nt':
                source = Path(value.strip('"')).expanduser()
            else:
                parts = shlex.split(value)
                if len(parts) != 1:
                    raise ValueError('Choose one setup JSON file.')
                source = Path(parts[0]).expanduser()
    if source is not None:
        settings = load_settings(source)
    else:
        key = getpass.getpass('Matching website encryption key (hidden): ').strip()
        pem = read_public_pem(input('Path to public PEM: ').strip().strip('"'))
        settings = validate_settings({'aes_key_b64': key, 'public_pem': pem})
    if CONFIG.exists() and input('Replace existing QR setup? Type REPLACE: ').strip() != 'REPLACE':
        print('Cancelled. Existing setup preserved.')
        return
    save_settings(settings)
    print('SUCCESS: QR verification configured locally. No server restart needed.')
    print('Configuration saved to:', CONFIG)
    status = configuration_status()
    print(status['message'])
    if not status['website_qr_configured']:
        raise ValueError('Configuration check failed. Set up configuration again.')
    print('Next: test a fresh real student QR. Matching the website keys is confirmed by a successful scan.')


if __name__ == '__main__':
    environment_python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if environment_python.is_file() and Path(sys.prefix).absolute() != (ROOT / '.venv').absolute():
        sys.exit(subprocess.call([str(environment_python), str(Path(__file__).absolute()), *sys.argv[1:]]))
    while True:
        try:
            main()
            break
        except (KeyboardInterrupt, EOFError):
            print('Setup cancelled. Existing configuration was preserved.')
            sys.exit(1)
        except Exception as exc:
            print('Setup failed: ' + setup_failure(exc))
            try:
                if input('Set up configuration again? [Enter = retry / Q = quit]: ').strip().lower() == 'q':
                    sys.exit(1)
            except (EOFError, KeyboardInterrupt):
                sys.exit(1)
