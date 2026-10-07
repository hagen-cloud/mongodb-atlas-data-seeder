import contextlib
import io
import json
import os
import random
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from bson import ObjectId
from faker import Faker

from seeder import __main__ as cli
from seeder import config, generator, guardrails, monitor, partition, sizing, writer

ROOT = Path(__file__).parents[1]


def load_example(name='config.test.yaml'):
    with patch.dict(os.environ, {}, clear=True):
        return config.load_config(str(ROOT / 'config' / name))


class ConfigurationTests(unittest.TestCase):
    def test_all_examples_resolve_templates(self):
        for name in ('config.example.yaml', 'config.test.yaml', 'config.fast.yaml'):
            with self.subTest(name=name):
                cfg = load_example(name)
                self.assertTrue(all(database.schema for database in cfg.databases))
                self.assertEqual((cfg.shard_index, cfg.shard_total), (0, 1))

    def test_environment_overrides_and_index_precedence(self):
        with patch.dict(os.environ, {'JOB_COMPLETION_INDEX': '2', 'SEEDER_SHARD_INDEX': '7', 'SEEDER_SHARD_TOTAL': '5'}, clear=True):
            cfg = config.load_config(str(ROOT / 'config/config.test.yaml'))
        self.assertEqual((cfg.shard_index, cfg.shard_total), (2, 5))
        with patch.dict(os.environ, {'SEEDER_SHARD_INDEX': '3'}, clear=True):
            cfg = config.load_config(str(ROOT / 'config/config.test.yaml'))
        self.assertEqual(cfg.shard_index, 3)

    def test_template_directory_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            for database in load_example().databases:
                Path(temporary, database.template).write_text(json.dumps({'schema': {'fixture': {'type': 'int', 'min': 1, 'max': 1}}}))
            with patch.dict(os.environ, {'SEEDER_CONFIG': str(ROOT / 'config/config.test.yaml'), 'SEEDER_TEMPLATES_DIR': temporary}, clear=True):
                cfg = config.load_config()
            self.assertEqual(cfg.templates_dir, temporary)
            self.assertTrue(all('fixture' in database.schema for database in cfg.databases))


class GuardrailTests(unittest.TestCase):
    def test_missing_uri_is_rejected(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(guardrails.GuardrailError, 'not set'):
            guardrails.check(load_example())

    def test_blocklist_is_case_insensitive(self):
        cfg = load_example()
        with patch.dict(os.environ, {'MONGODB_URI': 'mongodb://PROD.example.invalid:27017'}, clear=True), self.assertRaisesRegex(guardrails.GuardrailError, 'blocklist'):
            guardrails.check(cfg)

    def test_environment_mismatch_is_rejected(self):
        cfg = load_example()
        cfg.env = 'another-test-environment'
        with patch.dict(os.environ, {'MONGODB_URI': 'mongodb://127.0.0.1:27017'}, clear=True), self.assertRaisesRegex(guardrails.GuardrailError, 'does not match'):
            guardrails.check(cfg)

    def test_custom_environment_policy_and_valid_uri(self):
        cfg = load_example()
        cfg.env = ' Sandbox '
        cfg.safety.require_env = 'sandbox'
        uri = 'mongodb://127.0.0.1:27017'
        with patch.dict(os.environ, {'MONGODB_URI': uri}, clear=True):
            self.assertEqual(guardrails.check(cfg), uri)

    def test_cli_aborts_before_creating_clients(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(cli.sys, 'argv', ['seeder', '--config', str(ROOT / 'config/config.test.yaml')]), patch.object(writer, 'build_client') as client:
            with self.assertRaises(SystemExit) as exited:
                cli.main()
            self.assertEqual(exited.exception.code, 2)
            client.assert_not_called()


class GeneratorTests(unittest.TestCase):
    def test_all_supported_field_types_and_nested_schema(self):
        schema = {
            'id': {'type': 'objectId'}, 'integer': {'type': 'int', 'min': 2, 'max': 2},
            'double': {'type': 'double', 'min': 1.5, 'max': 1.5},
            'flag': {'type': 'bool', 'p_true': 1}, 'enum': {'type': 'enum', 'values': ['fixture']},
            'string': {'type': 'string', 'length': 8, 'charset': 'digits'},
            'uuid': {'type': 'uuid'}, 'date': {'type': 'date', 'min': '2020-01-01', 'max': '2020-01-01'},
            'faker': {'type': 'faker', 'method': 'word'},
            'object': {'type': 'object', 'fields': {'child': {'type': 'int', 'min': 1, 'max': 1}}},
            'array': {'type': 'array', 'minItems': 2, 'maxItems': 2, 'of': {'type': 'bool', 'p_true': 0}},
        }
        faker = Faker()
        faker.seed_instance(42)
        doc = generator.generate_document(schema, random.Random(42), faker)
        self.assertIsInstance(doc['id'], ObjectId)
        self.assertEqual((doc['integer'], doc['double'], doc['flag']), (2, 1.5, True))
        self.assertEqual(doc['object'], {'child': 1})
        self.assertEqual(doc['array'], [False, False])
        self.assertTrue(doc['string'].isdigit())
        self.assertEqual(len(doc['string']), 8)
        self.assertEqual(doc['date'].year, 2020)

    def test_seeded_choices_are_repeatable_without_objectids(self):
        schema = {'name': {'type': 'faker', 'method': 'name'}, 'number': {'type': 'int'}}
        documents = []
        for _ in range(2):
            faker = Faker()
            faker.seed_instance(42)
            documents.append(generator.generate_document(schema, random.Random(42), faker))
        self.assertEqual(*documents)

    def test_unknown_type_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown field type'):
            generator.generate_value({'type': 'unsupported'}, random.Random(), Faker())

    def test_bulk_template_size_and_bson_encodability(self):
        from bson import BSON
        cfg = load_example('config.fast.yaml')
        document = generator.generate_document(cfg.databases[0].schema, random.Random(1), Faker())
        self.assertEqual(len(document['payload']), 100000)
        self.assertGreater(len(BSON.encode(document)), 100000)

    def test_cli_dry_run_never_creates_a_database_client(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(cli.sys, 'argv', ['seeder', '--config', str(ROOT / 'config/config.test.yaml'), '--dry-run', '2']), patch.object(writer, 'build_client') as client, contextlib.redirect_stdout(io.StringIO()) as output:
            cli.main()
            client.assert_not_called()
            self.assertIn('generated 2 docs', output.getvalue())


class PartitionAndSizingTests(unittest.TestCase):
    def test_weighted_selection_distribution(self):
        databases = load_example().databases
        rng = random.Random(42)
        selected = [partition.pick_weighted(databases, rng).name for _ in range(10000)]
        fraction = selected.count(databases[0].name) / len(selected)
        self.assertAlmostEqual(fraction, 5 / 8, delta=0.025)

    def test_thread_seed_is_stable_and_distinct_for_operating_dimensions(self):
        seeds = [writer._seed_int(shard, worker, thread) for shard in range(5) for worker in range(8) for thread in range(4)]
        self.assertEqual(len(seeds), len(set(seeds)))
        self.assertEqual(writer._seed_int(2, 3, 4), writer._seed_int(2, 3, 4))

    def test_size_units_and_formatting(self):
        self.assertEqual(sizing.parse_size('1.5 GB'), int(1.5 * 1024 ** 3))
        self.assertEqual(sizing.parse_size(1024), 1024)
        self.assertEqual(sizing.format_size(1024), '1.00KB')
        with self.assertRaises(ValueError):
            sizing.parse_size('not-a-size')

    def test_metrics_deduplicate_databases_and_sum_indexes(self):
        client = MagicMock()
        client.__getitem__.return_value.command.return_value = {'storageSize': 10, 'indexSize': 5, 'dataSize': 30, 'fsUsedSize': 99}
        self.assertEqual(sizing.measure(client, ['a', 'a', 'b'], 'totalSize'), 30)
        self.assertEqual(client.__getitem__.return_value.command.call_count, 2)
        client.reset_mock()
        self.assertEqual(sizing.measure(client, ['a', 'b'], 'fsUsedSize'), 99)
        self.assertEqual(client.__getitem__.return_value.command.call_count, 1)


class WorkerAndMonitorTests(unittest.TestCase):
    def test_client_preserves_connection_and_write_options(self):
        cfg = load_example()
        with patch.dict(os.environ, {'MONGODB_URI': 'mongodb://127.0.0.1:27017'}, clear=True), patch.object(writer, 'MongoClient') as client:
            writer.build_client(cfg)
            self.assertEqual(client.call_args.args, ('mongodb://127.0.0.1:27017',))
            self.assertEqual(client.call_args.kwargs['maxPoolSize'], cfg.write.threads + 1)
            self.assertTrue(client.call_args.kwargs['retryWrites'])

    def test_insert_error_log_omits_payload_and_keeps_backoff(self):
        cfg = load_example()
        cfg.write.batch_size = 1
        client = MagicMock()
        client.__getitem__.return_value.__getitem__.return_value.insert_many.side_effect = RuntimeError('SYNTHETIC_PRIVATE_PAYLOAD')
        stop = threading.Event()
        with patch.object(stop, 'wait', side_effect=lambda seconds: stop.set()) as wait, self.assertLogs('seeder.writer', level='WARNING') as logs:
            writer._thread_loop(client, cfg, stop, 1)
        wait.assert_called_once_with(1.0)
        self.assertIn('RuntimeError', '\n'.join(logs.output))
        self.assertNotIn('SYNTHETIC_PRIVATE_PAYLOAD', '\n'.join(logs.output))

    def test_monitor_stops_at_adjusted_target_and_closes_client(self):
        cfg = load_example()
        cfg.target.size = '100B'
        cfg.target.overshoot = 0.9
        stop = threading.Event()
        client = MagicMock()
        with patch.object(sizing, 'measure', side_effect=[50, 90]), patch.object(stop, 'wait') as wait:
            monitor.run(cfg, stop, lambda: client)
        self.assertTrue(stop.is_set())
        wait.assert_called_once_with(cfg.target.check_interval_s)
        client.close.assert_called_once()

    def test_monitor_closes_client_when_measurement_fails(self):
        cfg = load_example()
        client = MagicMock()
        with patch.object(sizing, 'measure', side_effect=RuntimeError('fixture')), self.assertRaises(RuntimeError):
            monitor.run(cfg, threading.Event(), lambda: client)
        client.close.assert_called_once()

    def test_index_creation_preserves_keys_options_and_client_cleanup(self):
        cfg = load_example()
        cfg.databases[0].indexes = [{'keys': {'fixture': 1}, 'unique': True}]
        client = MagicMock()
        with patch.object(writer, 'build_client', return_value=client):
            cli.ensure_indexes(cfg)
        client.__getitem__.return_value.__getitem__.return_value.create_index.assert_called_once_with([('fixture', 1)], unique=True)
        client.close.assert_called_once()


class ManifestTests(unittest.TestCase):
    def test_indexed_job_shard_dimensions_match(self):
        job = yaml.safe_load((ROOT / 'k8s/job.yaml').read_text())
        spec = job['spec']
        self.assertEqual(spec['completionMode'], 'Indexed')
        self.assertEqual(spec['completions'], spec['parallelism'])
        container = spec['template']['spec']['containers'][0]
        env = {entry['name']: entry for entry in container['env']}
        self.assertEqual(int(env['SEEDER_SHARD_TOTAL']['value']), spec['completions'])
        self.assertIn('secretKeyRef', env['MONGODB_URI']['valueFrom'])

    def test_configmap_contains_loadable_config_and_bulk_template(self):
        content = yaml.safe_load((ROOT / 'k8s/configmap.example.yaml').read_text())
        with tempfile.TemporaryDirectory() as temporary:
            for name, value in content['data'].items():
                Path(temporary, name).write_text(value)
            with patch.dict(os.environ, {'SEEDER_TEMPLATES_DIR': temporary}, clear=True):
                cfg = config.load_config(str(Path(temporary, 'config.yaml')))
            self.assertEqual(cfg.databases[0].schema['payload']['length'], 100000)


if __name__ == '__main__':
    unittest.main()
