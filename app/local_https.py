#!/usr/bin/env python3
"""Private, offline, per-laptop CA and LAN HTTPS certificate for staff devices.

Only the CA's *public* certificate is shared with phones. The CA signing key
and TLS server key stay in data/phone_https on the event laptop.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import os
from pathlib import Path
import tempfile

BASE = Path(__file__).resolve().parent
CERT_DIR = BASE / 'data' / 'phone_https'
CA_KEY = CERT_DIR / 'ca-private.key'  # never serve, upload or distribute
CA_PEM = CERT_DIR / 'TECHVISTRA-Phone-CA.crt'
CA_DER = CERT_DIR / 'TECHVISTRA-Phone-CA.cer'
LEAF_KEY = CERT_DIR / 'server-private.key'
LEAF_CERT = CERT_DIR / 'server.crt'


def _crypto():
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
        return x509, hashes, serialization, ec, NameOID, ExtendedKeyUsageOID
    except ImportError as exc:
        raise RuntimeError(
            'Phone HTTPS needs cryptography. Run the Install and Setup file for your operating system with internet.'
        ) from exc


def _safe_write(path: Path, data: bytes, private=True):
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    # Restrict directories and private keys on POSIX. Windows: store only on
    # your private laptop account and do not share the data directory.
    if os.name != 'nt':
        CERT_DIR.chmod(0o700)
    fd, tmp = tempfile.mkstemp(prefix='.create-', dir=str(CERT_DIR))
    try:
        if os.name != 'nt':
            os.fchmod(fd, 0o600 if private else 0o644)
        with os.fdopen(fd, 'wb') as fh:
            fh.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _ips(lan_ips):
    ips = {ipaddress.ip_address('127.0.0.1'), ipaddress.ip_address('::1')}
    for value in lan_ips:
        try:
            ip = ipaddress.ip_address(value)
            if ip.is_private or ip.is_link_local:
                ips.add(ip)
        except ValueError:
            pass
    return sorted(ips, key=lambda item: (item.version, item.packed))


def fingerprint():
    """Fingerprint for user to verify against the event laptop display."""
    x509, hashes, *_ = _crypto()
    cert = x509.load_pem_x509_certificate(CA_PEM.read_bytes())
    digest = cert.fingerprint(hashes.SHA256()).hex().upper()
    return ':'.join(digest[i:i+2] for i in range(0, len(digest), 2))


def ensure_certificates(lan_ips):
    """Create one CA per laptop, renew server leaf after IP changes/expiry.

    Do not rotate an existing CA silently: doing so would invalidate all
    previously enrolled staff phones and could conceal a wrong-key incident.
    """
    x509, hashes, serialization, ec, NameOID, ExtendedKeyUsageOID = _crypto()
    now = datetime.now(timezone.utc)
    desired_ips = _ips(lan_ips)
    ca_exists = CA_PEM.exists() or CA_KEY.exists()
    if ca_exists and not (CA_PEM.exists() and CA_KEY.exists()):
        raise RuntimeError('Phone HTTPS CA is incomplete. Restore BOTH CA files from your private laptop backup; do not replace the CA during the event.')
    created_ca = False
    if not ca_exists:
        ca_private = ec.generate_private_key(ec.SECP256R1())
        ca_subject = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'TECHVISTRA 26 Food Desk'),
            x509.NameAttribute(NameOID.COMMON_NAME, 'TECHVISTRA Offline Phone CA'),
        ])
        ca_cert = (x509.CertificateBuilder()
            .subject_name(ca_subject).issuer_name(ca_subject)
            .public_key(ca_private.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=5*365))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                key_encipherment=False, data_encipherment=False, key_agreement=False,
                key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_private.public_key()), critical=False)
            .sign(ca_private, hashes.SHA256()))
        _safe_write(CA_KEY, ca_private.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        _safe_write(CA_PEM, ca_cert.public_bytes(serialization.Encoding.PEM), private=False)
        _safe_write(CA_DER, ca_cert.public_bytes(serialization.Encoding.DER), private=False)
        created_ca = True
    else:
        ca_cert = x509.load_pem_x509_certificate(CA_PEM.read_bytes())
        ca_private = serialization.load_pem_private_key(CA_KEY.read_bytes(), password=None)
        if ca_cert.public_key().public_numbers() != ca_private.public_key().public_numbers():
            raise RuntimeError('Phone HTTPS CA private key does not match CA certificate; restore a correct backup.')
        if ca_cert.not_valid_after_utc <= now + timedelta(days=30):
            raise RuntimeError('Phone HTTPS CA will expire soon. Plan a deliberate CA rotation and re-enrollment of all phones.')
        if not CA_DER.exists():
            _safe_write(CA_DER, ca_cert.public_bytes(serialization.Encoding.DER), private=False)

    regenerate = created_ca or not (LEAF_CERT.exists() and LEAF_KEY.exists())
    if not regenerate:
        try:
            existing = x509.load_pem_x509_certificate(LEAF_CERT.read_bytes())
            existing_ips = set(existing.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress))
            existing_dns = set(existing.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName))
            regenerate = (not set(desired_ips).issubset(existing_ips) or 'localhost' not in existing_dns
                          or existing.not_valid_after_utc < now + timedelta(days=14)
                          or existing.issuer != ca_cert.subject)
            if not regenerate:
                existing_key = serialization.load_pem_private_key(LEAF_KEY.read_bytes(), password=None)
                regenerate = existing_key.public_key().public_numbers() != existing.public_key().public_numbers()
        except Exception:
            regenerate = True

    if regenerate:
        server_private = ec.generate_private_key(ec.SECP256R1())
        san = [x509.DNSName('localhost')] + [x509.IPAddress(value) for value in desired_ips]
        server_cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'TECHVISTRA Food Desk Laptop')]))
            .issuer_name(ca_cert.subject).public_key(server_private.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(hours=1)).not_valid_after(now + timedelta(days=180))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                key_encipherment=False, data_encipherment=False, key_agreement=False,
                key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_private.public_key()), critical=False)
            .sign(ca_private, hashes.SHA256()))
        _safe_write(LEAF_KEY, server_private.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        _safe_write(LEAF_CERT, server_cert.public_bytes(serialization.Encoding.PEM), private=False)

    return {'cert': str(LEAF_CERT), 'key': str(LEAF_KEY), 'ca_pem': str(CA_PEM),
            'ca_der': str(CA_DER), 'fingerprint': fingerprint(),
            'created_ca': created_ca, 'renewed_server': regenerate,
            'ips': [str(ip) for ip in desired_ips]}
