"""Tests for the PortraitBuilder.

Run with: python3 src/pybind/mgr/cephfs_profiler/tests/test_portrait.py
"""

import os
import sys
import importlib.util
import unittest

# Direct import of pure-Python modules, bypassing __init__.py
_profiler_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_module(name, filepath):
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_types_mod = _load_module('cephfs_profiler.types', os.path.join(_profiler_dir, 'types.py'))
_portrait_mod = _load_module('cephfs_profiler.portrait', os.path.join(_profiler_dir, 'portrait.py'))

ClientDelta = _types_mod.ClientDelta
HourlyActivity = _types_mod.HourlyActivity
PortraitBuilder = _portrait_mod.PortraitBuilder


def make_delta(ts=1000.0, interval=60.0, wall_hour=14,
               d_read_ops=100, d_read_bytes=102400,
               d_write_ops=10, d_write_bytes=10240,
               d_cap_hits=50, d_cap_misses=5,
               d_dentry_hits=30, d_dentry_misses=2,
               avg_read_lat=1.5, avg_write_lat=3.0, avg_meta_lat=0.5,
               opened_files=10, opened_inodes=20):
    return ClientDelta(
        timestamp=ts, interval_secs=interval, wall_hour=wall_hour,
        d_read_ops=d_read_ops, d_read_bytes=d_read_bytes,
        d_write_ops=d_write_ops, d_write_bytes=d_write_bytes,
        d_cap_hits=d_cap_hits, d_cap_misses=d_cap_misses,
        d_dentry_hits=d_dentry_hits, d_dentry_misses=d_dentry_misses,
        avg_read_lat=avg_read_lat, avg_write_lat=avg_write_lat,
        avg_meta_lat=avg_meta_lat,
        opened_files=opened_files, opened_inodes=opened_inodes,
    )


class TestWorkloadClassification(unittest.TestCase):
    def test_idle(self):
        portrait = PortraitBuilder.build("client.1", "cephfs", {}, [])
        self.assertEqual(portrait.workload_classification, "idle")

    def test_read_heavy(self):
        deltas = [make_delta(d_read_ops=100, d_write_ops=5, d_cap_hits=5, d_cap_misses=0)]
        portrait = PortraitBuilder.build("client.1", "cephfs", {}, deltas)
        self.assertEqual(portrait.workload_classification, "read-heavy")

    def test_write_heavy(self):
        deltas = [make_delta(d_read_ops=5, d_write_ops=100, d_cap_hits=5, d_cap_misses=0)]
        portrait = PortraitBuilder.build("client.1", "cephfs", {}, deltas)
        self.assertEqual(portrait.workload_classification, "write-heavy")

    def test_metadata_heavy(self):
        deltas = [make_delta(d_read_ops=5, d_write_ops=5, d_cap_hits=200, d_cap_misses=50)]
        portrait = PortraitBuilder.build("client.1", "cephfs", {}, deltas)
        self.assertEqual(portrait.workload_classification, "metadata-heavy")

    def test_balanced(self):
        deltas = [make_delta(d_read_ops=50, d_write_ops=50, d_cap_hits=10, d_cap_misses=0)]
        portrait = PortraitBuilder.build("client.1", "cephfs", {}, deltas)
        self.assertEqual(portrait.workload_classification, "balanced")

    def test_read_biased(self):
        deltas = [make_delta(d_read_ops=60, d_write_ops=40, d_cap_hits=10, d_cap_misses=0)]
        portrait = PortraitBuilder.build("client.1", "cephfs", {}, deltas)
        self.assertEqual(portrait.workload_classification, "read-biased")

    def test_write_biased(self):
        deltas = [make_delta(d_read_ops=40, d_write_ops=60, d_cap_hits=10, d_cap_misses=0)]
        portrait = PortraitBuilder.build("client.1", "cephfs", {}, deltas)
        self.assertEqual(portrait.workload_classification, "write-biased")


class TestThroughput(unittest.TestCase):
    def test_average_throughput(self):
        deltas = [
            make_delta(interval=60.0, d_read_bytes=60 * 1024 * 1024,
                       d_write_bytes=30 * 1024 * 1024),
            make_delta(interval=60.0, d_read_bytes=60 * 1024 * 1024,
                       d_write_bytes=30 * 1024 * 1024),
        ]
        portrait = PortraitBuilder.build("client.1", "cephfs", {}, deltas)
        self.assertAlmostEqual(portrait.avg_read_throughput_MBps, 1.0, places=1)
        self.assertAlmostEqual(portrait.avg_write_throughput_MBps, 0.5, places=1)

    def test_peak_throughput(self):
        deltas = [
            make_delta(interval=60.0, d_read_bytes=60 * 1024 * 1024),
            make_delta(interval=60.0, d_read_bytes=300 * 1024 * 1024),
        ]
        portrait = PortraitBuilder.build("client.1", "cephfs", {}, deltas)
        self.assertAlmostEqual(portrait.peak_read_throughput_MBps, 5.0, places=1)


class TestIOSize(unittest.TestCase):
    def test_avg_io_size(self):
        deltas = [make_delta(d_read_ops=100, d_read_bytes=100 * 128 * 1024)]
        portrait = PortraitBuilder.build("client.1", "cephfs", {}, deltas)
        self.assertAlmostEqual(portrait.avg_read_size_KB, 128.0, places=1)

    def test_zero_ops(self):
        deltas = [make_delta(d_read_ops=0, d_read_bytes=0)]
        portrait = PortraitBuilder.build("client.1", "cephfs", {}, deltas)
        self.assertEqual(portrait.avg_read_size_KB, 0.0)


class TestHourlyActivity(unittest.TestCase):
    def test_peak_hour(self):
        deltas = [
            make_delta(wall_hour=9, d_read_ops=10, d_cap_hits=0, d_cap_misses=0),
            make_delta(wall_hour=14, d_read_ops=100, d_cap_hits=0, d_cap_misses=0),
            make_delta(wall_hour=14, d_read_ops=100, d_cap_hits=0, d_cap_misses=0),
            make_delta(wall_hour=16, d_read_ops=20, d_cap_hits=0, d_cap_misses=0),
        ]
        portrait = PortraitBuilder.build("client.1", "cephfs", {}, deltas)
        self.assertEqual(portrait.hourly_activity.peak_hour, 14)

    def test_active_hours(self):
        deltas = [
            make_delta(wall_hour=9, d_read_ops=50, d_cap_hits=0, d_cap_misses=0),
            make_delta(wall_hour=14, d_read_ops=100, d_cap_hits=0, d_cap_misses=0),
            make_delta(wall_hour=3, d_read_ops=1, d_write_ops=0,
                       d_cap_hits=0, d_cap_misses=0),
        ]
        portrait = PortraitBuilder.build("client.1", "cephfs", {}, deltas)
        self.assertIn(9, portrait.hourly_activity.active_hours)
        self.assertIn(14, portrait.hourly_activity.active_hours)


class TestCacheEfficiency(unittest.TestCase):
    def test_cap_hit_ratio(self):
        deltas = [make_delta(d_cap_hits=90, d_cap_misses=10)]
        portrait = PortraitBuilder.build("client.1", "cephfs", {}, deltas)
        self.assertAlmostEqual(portrait.cap_hit_ratio, 0.9, places=2)

    def test_dentry_hit_ratio(self):
        deltas = [make_delta(d_dentry_hits=95, d_dentry_misses=5)]
        portrait = PortraitBuilder.build("client.1", "cephfs", {}, deltas)
        self.assertAlmostEqual(portrait.dentry_lease_hit_ratio, 0.95, places=2)

    def test_zero_cache_ops(self):
        deltas = [make_delta(d_cap_hits=0, d_cap_misses=0)]
        portrait = PortraitBuilder.build("client.1", "cephfs", {}, deltas)
        self.assertEqual(portrait.cap_hit_ratio, 0.0)


class TestLatency(unittest.TestCase):
    def test_avg_latency(self):
        deltas = [
            make_delta(avg_read_lat=1.0, avg_write_lat=2.0, avg_meta_lat=0.5),
            make_delta(avg_read_lat=3.0, avg_write_lat=4.0, avg_meta_lat=1.5),
        ]
        portrait = PortraitBuilder.build("client.1", "cephfs", {}, deltas)
        self.assertAlmostEqual(portrait.avg_read_lat_ms, 2.0, places=1)
        self.assertAlmostEqual(portrait.avg_write_lat_ms, 3.0, places=1)
        self.assertAlmostEqual(portrait.avg_metadata_lat_ms, 1.0, places=1)


class TestPortraitSerialization(unittest.TestCase):
    def test_to_dict(self):
        deltas = [make_delta()]
        portrait = PortraitBuilder.build("client.1", "cephfs", {"hostname": "h1"}, deltas)
        d = portrait.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["client_id"], "client.1")
        self.assertIn("hourly_activity", d)

    def test_summary(self):
        deltas = [make_delta()]
        portrait = PortraitBuilder.build("client.1", "cephfs", {"hostname": "h1"}, deltas)
        summary = PortraitBuilder.build_summary(portrait)
        self.assertIn("workload", summary)
        self.assertIn("client_id", summary)
        self.assertIn("metadata_ops", summary)


class TestMultipleDeltas(unittest.TestCase):
    def test_aggregation_across_deltas(self):
        deltas = [
            make_delta(d_read_ops=100, d_write_ops=10),
            make_delta(d_read_ops=200, d_write_ops=20),
            make_delta(d_read_ops=300, d_write_ops=30),
        ]
        portrait = PortraitBuilder.build("client.1", "cephfs", {}, deltas)
        self.assertEqual(portrait.total_read_ops, 600)
        self.assertEqual(portrait.total_write_ops, 60)

    def test_profile_window(self):
        deltas = [
            make_delta(interval=3600.0),
            make_delta(interval=3600.0),
        ]
        portrait = PortraitBuilder.build("client.1", "cephfs", {}, deltas)
        self.assertAlmostEqual(portrait.profile_window_hours, 2.0, places=1)


if __name__ == '__main__':
    unittest.main()
