"""Tests for the ClientProfiler collector.

Run with: python3 src/pybind/mgr/cephfs_profiler/tests/test_collector.py
"""

import importlib.util
import json
import os
import sys
import time
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
_collector_mod = _load_module('cephfs_profiler.collector', os.path.join(_profiler_dir, 'collector.py'))

ClientProfiler = _collector_mod.ClientProfiler
ClientSnapshot = _types_mod.ClientSnapshot
ClientDelta = _types_mod.ClientDelta


def make_mock_module():
    module = MagicMock()
    module.log = MagicMock()
    return module


def make_perf_data(fs_name="cephfs", client_id="client.12345",
                   read_ops=100, read_bytes=102400,
                   write_ops=50, write_bytes=51200,
                   cap_hits=200, cap_misses=10,
                   dentry_hits=150, dentry_misses=5,
                   opened_files=10, opened_inodes=20,
                   avg_read_lat=1.5, avg_write_lat=3.0,
                   avg_meta_lat=0.5):
    counters = [None] * 16
    counters[0] = [cap_hits, cap_misses]
    counters[1] = 0
    counters[2] = 0
    counters[3] = 0
    counters[4] = [dentry_hits, dentry_misses]
    counters[5] = opened_files
    counters[6] = 0
    counters[7] = opened_inodes
    counters[8] = [read_ops, read_bytes]
    counters[9] = [write_ops, write_bytes]
    counters[10] = avg_read_lat
    counters[11] = 0.1
    counters[12] = avg_write_lat
    counters[13] = 0.2
    counters[14] = avg_meta_lat
    counters[15] = 0.05

    return {
        "version": 2,
        "global_counters": [],
        "client_metadata": {
            fs_name: {
                client_id: {
                    "hostname": "worker-1",
                    "root": "/",
                    "mount_point": "/mnt/cephfs",
                    "IP": "192.168.1.100",
                }
            }
        },
        "global_metrics": {
            fs_name: {
                client_id: counters
            }
        },
    }


class TestParseSnapshots(unittest.TestCase):
    def test_basic_parse(self):
        module = make_mock_module()
        profiler = ClientProfiler(module, ring_size=100)

        raw = make_perf_data(read_ops=100, write_ops=50, cap_hits=200)
        snapshots = profiler._parse_snapshots(raw)

        self.assertEqual(len(snapshots), 1)
        key = ("cephfs", "client.12345")
        self.assertIn(key, snapshots)

        snap = snapshots[key]
        self.assertEqual(snap.read_ops, 100)
        self.assertEqual(snap.write_ops, 50)
        self.assertEqual(snap.cap_hits, 200)
        self.assertEqual(snap.metadata["hostname"], "worker-1")

    def test_empty_data(self):
        module = make_mock_module()
        profiler = ClientProfiler(module, ring_size=100)

        raw = {"version": 2, "global_metrics": {}, "client_metadata": {}}
        snapshots = profiler._parse_snapshots(raw)
        self.assertEqual(len(snapshots), 0)

    def test_multiple_clients(self):
        module = make_mock_module()
        profiler = ClientProfiler(module, ring_size=100)

        data1 = make_perf_data(client_id="client.1", read_ops=100)
        data2 = make_perf_data(client_id="client.2", read_ops=200)
        data1["global_metrics"]["cephfs"]["client.2"] = \
            data2["global_metrics"]["cephfs"]["client.2"]
        data1["client_metadata"]["cephfs"]["client.2"] = \
            data2["client_metadata"]["cephfs"]["client.2"]

        snapshots = profiler._parse_snapshots(data1)
        self.assertEqual(len(snapshots), 2)


class TestDiff(unittest.TestCase):
    def _make_snap(self, ts=1000.0, read_ops=100, write_ops=50,
                   cap_hits=200, cap_misses=10, dentry_hits=150,
                   dentry_misses=5, read_bytes=102400, write_bytes=51200):
        return ClientSnapshot(
            timestamp=ts, client_id="client.1", fs_name="cephfs",
            metadata={},
            read_ops=read_ops, read_bytes=read_bytes,
            write_ops=write_ops, write_bytes=write_bytes,
            cap_hits=cap_hits, cap_misses=cap_misses,
            dentry_hits=dentry_hits, dentry_misses=dentry_misses,
        )

    def test_normal_diff(self):
        module = make_mock_module()
        profiler = ClientProfiler(module)

        old = self._make_snap(ts=1000.0, read_ops=100, write_ops=50)
        new = self._make_snap(ts=1060.0, read_ops=200, write_ops=80)

        delta = profiler._diff(old, new)
        self.assertIsNotNone(delta)
        self.assertEqual(delta.d_read_ops, 100)
        self.assertEqual(delta.d_write_ops, 30)
        self.assertAlmostEqual(delta.interval_secs, 60.0)

    def test_counter_reset_returns_none(self):
        module = make_mock_module()
        profiler = ClientProfiler(module)

        old = self._make_snap(ts=1000.0, read_ops=100)
        new = self._make_snap(ts=1060.0, read_ops=10)

        delta = profiler._diff(old, new)
        self.assertIsNone(delta)

    def test_write_counter_reset(self):
        module = make_mock_module()
        profiler = ClientProfiler(module)

        old = self._make_snap(ts=1000.0, write_ops=100)
        new = self._make_snap(ts=1060.0, write_ops=5)

        delta = profiler._diff(old, new)
        self.assertIsNone(delta)

    def test_cap_counter_reset(self):
        module = make_mock_module()
        profiler = ClientProfiler(module)

        old = self._make_snap(ts=1000.0, cap_hits=200)
        new = self._make_snap(ts=1060.0, cap_hits=5)

        delta = profiler._diff(old, new)
        self.assertIsNone(delta)

    def test_zero_interval_returns_none(self):
        module = make_mock_module()
        profiler = ClientProfiler(module)

        old = self._make_snap(ts=1000.0)
        new = self._make_snap(ts=1000.0)

        delta = profiler._diff(old, new)
        self.assertIsNone(delta)

    def test_wall_hour(self):
        module = make_mock_module()
        profiler = ClientProfiler(module)

        old = self._make_snap(ts=1705312200.0, read_ops=100)
        new = self._make_snap(ts=1705312260.0, read_ops=200)

        delta = profiler._diff(old, new)
        self.assertIsNotNone(delta)
        self.assertIn(delta.wall_hour, range(24))


class TestRingBuffer(unittest.TestCase):
    def test_ring_buffer_capacity(self):
        module = make_mock_module()
        module.remote.return_value = (0, json.dumps(make_perf_data(read_ops=0)), "")
        profiler = ClientProfiler(module, ring_size=5, client_ttl=9999)

        profiler.tick()

        for i in range(1, 8):
            data = make_perf_data(read_ops=i * 10, write_ops=i * 5,
                                  cap_hits=i * 20, dentry_hits=i * 15)
            module.remote.return_value = (0, json.dumps(data), "")
            profiler.tick()

        deltas = profiler.get_deltas("cephfs", "client.12345")
        self.assertLessEqual(len(deltas), 5)
        self.assertGreater(len(deltas), 0)


class TestEviction(unittest.TestCase):
    def test_stale_client_evicted(self):
        module = make_mock_module()
        profiler = ClientProfiler(module, ring_size=100, client_ttl=1)

        data = make_perf_data(read_ops=100)
        module.remote.return_value = (0, json.dumps(data), "")
        profiler.tick()

        data2 = make_perf_data(read_ops=200, cap_hits=300, dentry_hits=200)
        module.remote.return_value = (0, json.dumps(data2), "")
        profiler.tick()

        self.assertEqual(len(profiler.get_active_clients()), 1)

        time.sleep(1.1)
        empty = {"version": 2, "global_metrics": {}, "client_metadata": {}}
        module.remote.return_value = (0, json.dumps(empty), "")
        profiler.tick()

        self.assertEqual(len(profiler.get_active_clients()), 0)


class TestFetchErrors(unittest.TestCase):
    def test_stats_module_not_enabled(self):
        module = make_mock_module()
        module.remote.side_effect = ImportError("No module named 'stats'")
        profiler = ClientProfiler(module)

        profiler.tick()
        self.assertEqual(profiler._error_count, 1)
        self.assertEqual(len(profiler.get_active_clients()), 0)

    def test_stats_module_returns_error(self):
        module = make_mock_module()
        module.remote.return_value = (-1, "", "some error")
        profiler = ClientProfiler(module)

        profiler.tick()
        self.assertEqual(profiler._error_count, 1)


class TestStatus(unittest.TestCase):
    def test_status_empty(self):
        module = make_mock_module()
        profiler = ClientProfiler(module)
        status = profiler.get_status()
        self.assertEqual(status["active_clients"], 0)
        self.assertEqual(status["total_polls"], 0)

    def test_status_with_data(self):
        module = make_mock_module()
        data = make_perf_data(read_ops=100)
        module.remote.return_value = (0, json.dumps(data), "")
        profiler = ClientProfiler(module, ring_size=100, client_ttl=9999)

        profiler.tick()
        data2 = make_perf_data(read_ops=200, cap_hits=300, dentry_hits=200)
        module.remote.return_value = (0, json.dumps(data2), "")
        profiler.tick()

        status = profiler.get_status()
        self.assertEqual(status["active_clients"], 1)
        self.assertEqual(status["total_polls"], 2)
        self.assertIsNotNone(status["last_poll_time"])


class TestReset(unittest.TestCase):
    def test_reset_specific(self):
        module = make_mock_module()
        profiler = ClientProfiler(module, ring_size=100, client_ttl=9999)

        data = make_perf_data(read_ops=100)
        module.remote.return_value = (0, json.dumps(data), "")
        profiler.tick()
        data2 = make_perf_data(read_ops=200, cap_hits=300, dentry_hits=200)
        module.remote.return_value = (0, json.dumps(data2), "")
        profiler.tick()

        cleared = profiler.reset("cephfs", "client.12345")
        self.assertEqual(cleared, 1)
        self.assertEqual(len(profiler.get_active_clients()), 0)

    def test_reset_all(self):
        module = make_mock_module()
        profiler = ClientProfiler(module, ring_size=100, client_ttl=9999)

        data = make_perf_data(read_ops=100)
        module.remote.return_value = (0, json.dumps(data), "")
        profiler.tick()
        data2 = make_perf_data(read_ops=200, cap_hits=300, dentry_hits=200)
        module.remote.return_value = (0, json.dumps(data2), "")
        profiler.tick()

        cleared = profiler.reset()
        self.assertEqual(cleared, 1)


class TestRingBufferResize(unittest.TestCase):
    def test_update_ring_size_shrinks(self):
        """Verify update_ring_size() rebuilds existing deques with new maxlen."""
        module = make_mock_module()
        module.remote.return_value = (0, json.dumps(make_perf_data(read_ops=0)), "")
        profiler = ClientProfiler(module, ring_size=100, client_ttl=9999)

        profiler.tick()
        # Generate deltas (some may be lost to timing, so just ensure we have enough)
        for i in range(1, 15):
            data = make_perf_data(read_ops=i * 10, write_ops=i * 5,
                                  cap_hits=i * 20, dentry_hits=i * 15)
            module.remote.return_value = (0, json.dumps(data), "")
            time.sleep(0.01)  # ensure distinct timestamps
            profiler.tick()

        deltas_before = profiler.get_deltas("cephfs", "client.12345")
        self.assertGreaterEqual(len(deltas_before), 5)

        # Shrink ring size to 3
        profiler.update_ring_size(3)
        deltas_after = profiler.get_deltas("cephfs", "client.12345")
        self.assertEqual(len(deltas_after), 3)
        # Should keep the most recent 3
        self.assertEqual(deltas_after[-1].d_read_ops, deltas_before[-1].d_read_ops)

    def test_update_ring_size_expands(self):
        """Verify update_ring_size() allows buffer to grow."""
        module = make_mock_module()
        module.remote.return_value = (0, json.dumps(make_perf_data(read_ops=0)), "")
        profiler = ClientProfiler(module, ring_size=3, client_ttl=9999)

        profiler.tick()
        for i in range(1, 6):
            data = make_perf_data(read_ops=i * 10, write_ops=i * 5,
                                  cap_hits=i * 20, dentry_hits=i * 15)
            module.remote.return_value = (0, json.dumps(data), "")
            profiler.tick()

        # Only 3 kept due to original maxlen
        self.assertEqual(len(profiler.get_deltas("cephfs", "client.12345")), 3)

        # Expand and add more
        profiler.update_ring_size(100)
        for i in range(6, 11):
            data = make_perf_data(read_ops=i * 10, write_ops=i * 5,
                                  cap_hits=i * 20, dentry_hits=i * 15)
            module.remote.return_value = (0, json.dumps(data), "")
            profiler.tick()

        # Should now have 3 (kept) + 5 (new) = 8
        self.assertEqual(len(profiler.get_deltas("cephfs", "client.12345")), 8)


class TestResetThorough(unittest.TestCase):
    def test_reset_clears_last_seen_and_metadata(self):
        """Verify reset clears _last_seen and _metadata, not just _deltas."""
        module = make_mock_module()
        profiler = ClientProfiler(module, ring_size=100, client_ttl=9999)

        data = make_perf_data(read_ops=100)
        module.remote.return_value = (0, json.dumps(data), "")
        profiler.tick()
        data2 = make_perf_data(read_ops=200, cap_hits=300, dentry_hits=200)
        module.remote.return_value = (0, json.dumps(data2), "")
        profiler.tick()

        # Verify state exists before reset
        self.assertIsNotNone(profiler.get_last_seen("cephfs", "client.12345"))
        self.assertTrue(profiler.get_metadata("cephfs", "client.12345"))

        profiler.reset("cephfs", "client.12345")

        # After reset, all state should be gone
        self.assertIsNone(profiler.get_last_seen("cephfs", "client.12345"))
        self.assertEqual(profiler.get_metadata("cephfs", "client.12345"), {})
        self.assertEqual(profiler.get_deltas("cephfs", "client.12345"), [])

    def test_reset_client_with_only_snapshot_no_delta(self):
        """Verify reset works for client that has only an initial snapshot (no deltas yet)."""
        module = make_mock_module()
        profiler = ClientProfiler(module, ring_size=100, client_ttl=9999)

        # Only one tick: creates _prev snapshot but no delta
        data = make_perf_data(read_ops=100)
        module.remote.return_value = (0, json.dumps(data), "")
        profiler.tick()

        # No deltas yet, but client state exists
        self.assertEqual(len(profiler.get_deltas("cephfs", "client.12345")), 0)
        self.assertIsNotNone(profiler.get_last_seen("cephfs", "client.12345"))

        # Reset should still find and clear it
        cleared = profiler.reset("cephfs", "client.12345")
        self.assertEqual(cleared, 1)
        self.assertIsNone(profiler.get_last_seen("cephfs", "client.12345"))

    def test_reset_all_clears_everything(self):
        """Verify full reset clears _last_seen and _metadata too."""
        module = make_mock_module()
        profiler = ClientProfiler(module, ring_size=100, client_ttl=9999)

        data = make_perf_data(read_ops=100)
        module.remote.return_value = (0, json.dumps(data), "")
        profiler.tick()
        data2 = make_perf_data(read_ops=200, cap_hits=300, dentry_hits=200)
        module.remote.return_value = (0, json.dumps(data2), "")
        profiler.tick()

        profiler.reset()

        self.assertEqual(len(profiler.get_active_clients()), 0)
        self.assertIsNone(profiler.get_last_seen("cephfs", "client.12345"))
        self.assertEqual(profiler.get_metadata("cephfs", "client.12345"), {})

    def test_reset_nonexistent_client(self):
        """Verify reset of non-existent client returns 0."""
        module = make_mock_module()
        profiler = ClientProfiler(module, ring_size=100)

        cleared = profiler.reset("cephfs", "client.99999")
        self.assertEqual(cleared, 0)


class TestResetByFsOnly(unittest.TestCase):
    """Test that reset(fs_name=X) only clears clients on that filesystem."""

    def test_reset_by_fs_only(self):
        module = make_mock_module()
        profiler = ClientProfiler(module, ring_size=100)

        # Create perf data for two different filesystems
        data_fs1 = make_perf_data(fs_name="fs1", client_id="client.1")
        data_fs2 = make_perf_data(fs_name="fs2", client_id="client.2")

        # Merge both into one response
        merged = {
            "global_metrics": {},
            "client_metadata": {},
        }
        for d in [data_fs1, data_fs2]:
            for fs, clients in d["global_metrics"].items():
                merged["global_metrics"][fs] = clients
            for fs, clients in d["client_metadata"].items():
                merged["client_metadata"][fs] = clients

        module.remote = MagicMock(return_value=(0, json.dumps(merged), ""))

        # Two ticks to generate deltas
        profiler.tick()
        time.sleep(0.01)
        profiler.tick()

        self.assertEqual(len(profiler.get_active_clients()), 2)

        # Reset only fs1
        cleared = profiler.reset(fs_name="fs1")
        self.assertEqual(cleared, 1)

        # fs2 client should still exist
        active = profiler.get_active_clients()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0], ("fs2", "client.2"))
        self.assertTrue(len(profiler.get_deltas("fs2", "client.2")) > 0)

        # fs1 client should be gone
        self.assertEqual(profiler.get_deltas("fs1", "client.1"), [])
        self.assertIsNone(profiler.get_last_seen("fs1", "client.1"))


class TestUpdateRingSizeNegative(unittest.TestCase):
    """Test that negative ring_buffer_size is clamped to 1."""

    def test_negative_ring_size_clamped(self):
        module = make_mock_module()
        profiler = ClientProfiler(module, ring_size=100)

        data = make_perf_data()
        module.remote = MagicMock(return_value=(0, json.dumps(data), ""))

        profiler.tick()
        time.sleep(0.01)
        profiler.tick()

        # Should not raise, should clamp to 1
        profiler.update_ring_size(-5)
        self.assertEqual(profiler.ring_size, 1)

        # Buffer should have at most 1 element
        deltas = profiler.get_deltas("cephfs", "client.12345")
        self.assertLessEqual(len(deltas), 1)

    def test_zero_ring_size_clamped(self):
        module = make_mock_module()
        profiler = ClientProfiler(module, ring_size=100)

        profiler.update_ring_size(0)
        self.assertEqual(profiler.ring_size, 1)

    def test_constructor_negative_ring_size_clamped(self):
        """Verify __init__ also clamps negative ring_size to 1."""
        module = make_mock_module()
        profiler = ClientProfiler(module, ring_size=-10)
        self.assertEqual(profiler.ring_size, 1)

    def test_constructor_zero_ring_size_clamped(self):
        module = make_mock_module()
        profiler = ClientProfiler(module, ring_size=0)
        self.assertEqual(profiler.ring_size, 1)


if __name__ == '__main__':
    unittest.main()
