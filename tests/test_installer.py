import importlib.util
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/install-server.py'
spec = importlib.util.spec_from_file_location('installer', SCRIPT)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def test_private_key_stays_out_of_client_export(self):
        server, client = installer.build_configs(
            '203.0.113.10', 'www.cloudflare.com', 443, 'Demo',
            'SYNTHETIC_PRIVATE_VALUE', 'SYNTHETIC_PUBLIC_VALUE',
            '00000000-0000-4000-8000-000000000001', '0011223344556677')
        self.assertNotIn('SYNTHETIC_PRIVATE_VALUE', json.dumps(client))
        self.assertEqual(server['inbounds'][0]['settings']['clients'][0]['id'], client['uuid'])
        self.assertEqual(server['inbounds'][0]['streamSettings']['realitySettings']['shortIds'],
                         [client['reality-opts']['short-id']])
        self.assertTrue(client['reality-opts']['support-x25519mlkem768'])

    def test_both_xray_key_output_formats(self):
        for label in ['Public key', 'Password (PublicKey)']:
            self.assertEqual(installer.parse_keys(f'Private key: TEST_PRIVATE\n{label}: TEST_PUBLIC\n'),
                             ('TEST_PRIVATE', 'TEST_PUBLIC'))

    def test_checksum_requires_a_complete_matching_sha256(self):
        digest = hashlib.sha256(b'fixture').hexdigest()
        self.assertTrue(installer.checksum_matches(b'fixture', 'SHA256= ' + digest))
        self.assertFalse(installer.checksum_matches(b'changed', 'SHA256= ' + digest))
        self.assertFalse(installer.checksum_matches(b'fixture', '0' + digest))

    def test_dry_run_works_without_root_or_network(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--server', '203.0.113.10', '--dry-run'],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['port'], 443)

    def test_rejects_url_instead_of_server_address(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--server', 'https://example.com', '--dry-run'],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
