"""Tests for the PersistenceManager.

Run with: python3 src/pybind/mgr/cephfs_profiler/tests/test_persistence.py
"""

import importlib.util
import json
import os
import sys
import unittest
from unittest.mock import MagicMock

_profiler_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_module(name, filepath):
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_types_mod = _load_module('cephfs_profiler.types', os.path.join(_profiler_dir, 'types.py'))
_persistence_mod = _load_module('cephfs_profiler.persistence', os.path.join(_profiler_dir, 'persistence.py'))

PersistenceManager = _persistence_mod.PersistenceManager
ClientPortrait = _types_mod.ClientPortrait
HourlyActivity = _types_mod.HourlyActivity


def make_mock_module():
    module = MagicMock()
    module._store = {}

    def set_store(key, val):
        if val is None:
            module._store.pop(key, None)
        else:
            module._store[key] = val
    module.set_store = set_store

    def get_store(key, default=None):
        return module._store.get(key, default)
    module.get_store = get_store

    def get_store_prefix(prefix):
        return {k: v for k, v in module._store.items() if k.startswith(prefix)}
    module.get_store_prefix = get_store_prefix

    return module


def make_portrait(client_id="client.1", fs_name="cephfs"):
    return ClientPortrait(
        client_id=client_id,
        fs_name=fs_name,
        hostname="worker-1",
        workload_classification="read-heavy",
        total_read_ops=1000,
        total_write_ops=100,
        avg_read_throughput_MBps=10.0,
        hourly_activity=HourlyActivity(),
        last_seen="2024-01-15T14:00:00",
    )


class TestSaveAndLoad(unittest.TestCase):
    def test_save_and_load(self):
        module = make_mock_module()
        portrait = make_portrait()

        # Use a recent date so it's within the load window
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        PersistenceManager.save_daily_portrait(module, portrait, today)

        history = PersistenceManager.load_history(module, "cephfs", "client.1", days=30)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["client_id"], "client.1")
        self.assertEqual(history[0]["workload_classification"], "read-heavy")

    def test_load_empty(self):
        module = make_mock_module()
        history = PersistenceManager.load_history(module, "cephfs", "client.1")
        self.assertEqual(len(history), 0)

    def test_multiple_days(self):
        module = make_mock_module()
        portrait = make_portrait()

        PersistenceManager.save_daily_portrait(module, portrait, "2024-01-14")
        PersistenceManager.save_daily_portrait(module, portrait, "2024-01-15")
        PersistenceManager.save_daily_portrait(module, portrait, "2024-01-16")

        history = PersistenceManager.load_history(module, "cephfs", "client.1", days=99999)
        self.assertEqual(len(history), 3)


class TestPrune(unittest.TestCase):
    def test_prune_old_records(self):
        module = make_mock_module()
        portrait = make_portrait()

        PersistenceManager.save_daily_portrait(module, portrait, "2020-01-01")
        PersistenceManager.save_daily_portrait(module, portrait, "2020-01-02")
        PersistenceManager.save_daily_portrait(module, portrait, "2099-12-31")

        deleted = PersistenceManager.prune_old(module, retention_days=30)
        self.assertEqual(deleted, 2)

        history = PersistenceManager.load_history(module, "cephfs", "client.1", days=99999)
        self.assertEqual(len(history), 1)

    def test_prune_nothing(self):
        module = make_mock_module()
        deleted = PersistenceManager.prune_old(module, retention_days=30)
        self.assertEqual(deleted, 0)


class TestReset(unittest.TestCase):
    def test_reset_specific_client(self):
        module = make_mock_module()
        p1 = make_portrait(client_id="client.1")
        p2 = make_portrait(client_id="client.2")

        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        PersistenceManager.save_daily_portrait(module, p1, today)
        PersistenceManager.save_daily_portrait(module, p2, today)

        deleted = PersistenceManager.reset_history(module, "cephfs", "client.1")
        self.assertEqual(deleted, 1)

        h2 = PersistenceManager.load_history(module, "cephfs", "client.2")
        self.assertEqual(len(h2), 1)

    def test_reset_all(self):
        module = make_mock_module()
        p1 = make_portrait(client_id="client.1")
        p2 = make_portrait(client_id="client.2")

        PersistenceManager.save_daily_portrait(module, p1, "2024-01-15")
        PersistenceManager.save_daily_portrait(module, p2, "2024-01-15")

        deleted = PersistenceManager.reset_history(module)
        self.assertEqual(deleted, 2)

    def test_reset_by_fs(self):
        module = make_mock_module()
        p1 = make_portrait(client_id="client.1", fs_name="fs1")
        p2 = make_portrait(client_id="client.1", fs_name="fs2")

        PersistenceManager.save_daily_portrait(module, p1, "2024-01-15")
        PersistenceManager.save_daily_portrait(module, p2, "2024-01-15")

        deleted = PersistenceManager.reset_history(module, fs_name="fs1")
        self.assertEqual(deleted, 1)


class TestPersistTime(unittest.TestCase):
    def test_save_and_get_persist_time(self):
        module = make_mock_module()

        PersistenceManager.save_persist_time(module, "2024-01-15T00:00:00")
        result = PersistenceManager.get_last_persist_time(module)
        self.assertEqual(result, "2024-01-15T00:00:00")

    def test_no_persist_time(self):
        module = make_mock_module()
        result = PersistenceManager.get_last_persist_time(module)
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
