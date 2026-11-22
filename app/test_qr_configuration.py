import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import configure_secure_qr as setup

class ConfigurationChecks(unittest.TestCase):
    def test_missing_and_invalid(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'config.json'
            self.assertFalse(setup.configuration_status(p)['website_qr_configured'])
            p.write_text('{broken')
            self.assertFalse(setup.configuration_status(p)['website_qr_configured'])

    def test_valid_keys_and_pem_path(self):
        import base64
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        pem = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'key.pem').write_text(pem)
            source = root/'source.json'
            source.write_text(json.dumps({'aes_key_b64':base64.b64encode(b'x'*32).decode(), 'public_pem':'key.pem'}))
            settings = setup.load_settings(source)
            setup.save_settings(settings, root/'data'/'config.json')
            self.assertTrue(setup.configuration_status(root/'data'/'config.json')['website_qr_configured'])

    def test_failed_setup_retries(self):
        with patch.object(setup, 'configuration_status', side_effect=[{'website_qr_configured':False,'message':'missing'}, {'website_qr_configured':False,'message':'invalid'}, {'website_qr_configured':True,'message':'passed'}]), patch.object(setup, 'main', side_effect=[ValueError(), None]) as run, patch('builtins.input', return_value=''), contextlib.redirect_stdout(io.StringIO()):
            setup.ensure_configuration()
            self.assertEqual(run.call_count, 2)

    def test_check_only_does_not_prompt(self):
        with patch.object(setup, 'configuration_status', return_value={'website_qr_configured':False,'message':'missing'}), patch('builtins.input') as prompt, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError): setup.ensure_configuration(check_only=True)
            prompt.assert_not_called()

if __name__ == '__main__': unittest.main()
