"""Complete CLI lifecycle against an explicitly enabled loopback-only MongoDB."""

import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

import yaml
from pymongo import MongoClient

from seeder import sizing

ROOT = Path(__file__).parents[1]
URI = os.environ.get('HC_SEEDER_LOCAL_MONGODB_URI', '')


@unittest.skipUnless(URI, 'set HC_SEEDER_LOCAL_MONGODB_URI for disposable local integration')
class LocalMongoDBTests(unittest.TestCase):
    def test_cli_inserts_stops_and_can_resume_already_reached_target(self):
        self.assertRegex(URI, r'^mongodb://127\.0\.0\.1:[0-9]+/?$')
        database = 'hc_seeder_test_' + uuid.uuid4().hex
        client = MongoClient(URI, serverSelectionTimeoutMS=10000)
        client.admin.command('ping')
        try:
            with tempfile.TemporaryDirectory(prefix='hc-seeder-test-') as temporary:
                path = Path(temporary)
                (path / 'templates').mkdir()
                (path / 'templates/fixture.json').write_text('{"schema":{"payload":{"type":"string","length":512}}}')
                raw = {
                    'env': 'test', 'target': {'size': '128KB', 'metric': 'dataSize', 'overshoot': 1, 'check_interval_s': 0.1},
                    'write': {'procs': 1, 'threads': 2, 'batch_size': 10, 'compressors': ''},
                    'safety': {'require_env': 'test', 'prod_host_blocklist': ['prod']},
                    'databases': [{'name': database, 'collection': 'fixture', 'weight': 1, 'template': 'fixture.json'}],
                }
                config_path = path / 'config.yaml'
                config_path.write_text(yaml.safe_dump(raw))
                environment = dict(os.environ)
                for key in list(environment):
                    if key.startswith(('SEEDER_', 'MONGODB_')) or key == 'JOB_COMPLETION_INDEX':
                        environment.pop(key)
                environment.update(MONGODB_URI=URI, SEEDER_SHARD_TOTAL='1', JOB_COMPLETION_INDEX='0')
                for _ in range(2):
                    result = subprocess.run([sys.executable, '-m', 'seeder', '--config', str(config_path)], env=environment, cwd=ROOT, capture_output=True, text=True, timeout=45, check=False)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('complete final_dataSize=', result.stderr)
                self.assertGreater(client[database].fixture.count_documents({}), 0)
                self.assertGreaterEqual(sizing.measure(client, [database], 'dataSize'), 128 * 1024)
        finally:
            # Only the unique database created by this test is removed.
            client.drop_database(database)
            client.close()


if __name__ == '__main__':
    unittest.main()
