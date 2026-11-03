"""Offline bootstrap/export regressions using fake Docker, no daemon or internet."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class OfflineDeliveryTest(unittest.TestCase):
    def test_keys_use_loaded_backend_without_network_or_host_python(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'.env.example').write_text('DOCTUS_VERSION=pilot-test\nMASTER_ENCRYPTION_KEY=\nSESSION_SECRET_KEY=\nDEPLOYER_TOKEN=\n')
            script = '\n'.join([
                '. "$HELPER"',
                'docker() { printf "%s\\n" "$*" > "$CALLS"; echo test-fernet-key; }',
                'openssl() { echo test-random-key; }',
                'bootstrap_env "$TEST_ROOT"',
                'bootstrap_env "$TEST_ROOT"',
            ])
            calls=root/'calls'
            result=subprocess.run(['sh','-c',script],env={**os.environ,'HELPER':str(ROOT/'scripts/lib/env-bootstrap.sh'),'TEST_ROOT':temp,'CALLS':str(calls)},capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            command=calls.read_text()
            self.assertIn('--pull=never --network none',command)
            self.assertIn('doctus-backend-api:pilot-test',command)
            self.assertNotIn('pip install',command)
            self.assertIn('MASTER_ENCRYPTION_KEY=test-fernet-key',(root/'.env').read_text())

    def test_export_failure_stops_before_shipping_checksums(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'scripts').mkdir();(root/'bin').mkdir()
            shutil.copy(ROOT/'scripts/build-offline-bundle.sh',root/'scripts/build-offline-bundle.sh')
            docker=root/'bin/docker'
            docker.write_text('#!/bin/sh\ncase "$1" in save) exit 42;; compose) case "$2" in config) echo test-image;; esac;; esac\n')
            docker.chmod(0o755)
            result=subprocess.run(['sh',str(root/'scripts/build-offline-bundle.sh'),'test','--remote-inference'],env={**os.environ,'PATH':str(root/'bin')+os.pathsep+os.environ['PATH']},capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse((root/'dist/doctus-offline-bundle-test/SHA256SUMS').exists())


    def test_existing_master_key_is_never_rotated_for_a_missing_optional_key(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'.env').write_text('DOCTUS_VERSION=old\nMASTER_ENCRYPTION_KEY=existing-key\nSESSION_SECRET_KEY=existing-session\nDEPLOYER_TOKEN=\n')
            script='\n'.join(['. "$HELPER"','docker() { echo "unexpected Docker call" >&2; return 99; }','openssl() { echo new-deployer-token; }','bootstrap_env "$TEST_ROOT" delivered-version'])
            result=subprocess.run(['sh','-c',script],env={**os.environ,'HELPER':str(ROOT/'scripts/lib/env-bootstrap.sh'),'TEST_ROOT':temp},capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('MASTER_ENCRYPTION_KEY=existing-key',(root/'.env').read_text())
            self.assertIn('SESSION_SECRET_KEY=existing-session',(root/'.env').read_text())
            self.assertIn('DEPLOYER_TOKEN=new-deployer-token',(root/'.env').read_text())

    def test_existing_database_without_master_key_requires_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'data/postgres').mkdir(parents=True)
            (root/'data/postgres/PG_VERSION').write_text('16')
            (root/'.env').write_text('MASTER_ENCRYPTION_KEY=\nSESSION_SECRET_KEY=\nDEPLOYER_TOKEN=\n')
            result=subprocess.run(['sh','-c','. "$HELPER"; bootstrap_env "$TEST_ROOT"'],env={**os.environ,'HELPER':str(ROOT/'scripts/lib/env-bootstrap.sh'),'TEST_ROOT':temp},capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('restore the original .env',result.stderr)
