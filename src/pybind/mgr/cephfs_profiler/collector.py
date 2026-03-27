"""
ClientProfiler: polls the stats module, computes diffs, stores in ring buffers.
"""

import json
import time
import logging
from collections import deque
from datetime import datetime
from threading import Lock
from typing import Dict, List, Optional, Sequence, Tuple

from .types import ClientSnapshot, ClientDelta

logger = logging.getLogger(__name__)

# Counter indices in global_metrics arrays (from stats/fs/perf_stats.py)
IDX_CAP_HIT = 0
IDX_DENTRY_LEASE = 4
IDX_OPENED_FILES = 5
IDX_OPENED_INODES = 7
IDX_READ_IO_SIZES = 8
IDX_WRITE_IO_SIZES = 9
IDX_AVG_READ_LAT = 10
IDX_STDEV_READ_LAT = 11
IDX_AVG_WRITE_LAT = 12
IDX_STDEV_WRITE_LAT = 13
IDX_AVG_META_LAT = 14
IDX_STDEV_META_LAT = 15

ClientKey = Tuple[str, str]  # (fs_name, client_id)


class ClientProfiler:
    """Collects client metrics via stats module, computes diffs, stores in ring buffers."""

    def __init__(self, module, ring_size: int = 1440, client_ttl: float = 300.0):
        self.module = module
        if ring_size < 1:
            logger.warning("ring_buffer_size %d is invalid, clamping to 1", ring_size)
            ring_size = 1
        self.ring_size = ring_size
        self.client_ttl = client_ttl

        self._lock = Lock()
        self._prev: Dict[ClientKey, ClientSnapshot] = {}
        self._deltas: Dict[ClientKey, deque] = {}
        self._first_seen: Dict[ClientKey, float] = {}
        self._last_seen: Dict[ClientKey, float] = {}
        self._metadata: Dict[ClientKey, Dict] = {}
        self._last_poll_time: Optional[float] = None
        self._poll_count: int = 0
        self._error_count: int = 0

    def update_ring_size(self, new_size: int) -> None:
        """Resize all existing ring buffers to new capacity.

        Python deque maxlen is immutable after creation, so we must
        rebuild each buffer with the new maxlen.
        """
        if new_size < 1:
            logger.warning("ring_buffer_size %d is invalid, clamping to 1", new_size)
            new_size = 1
        with self._lock:
            self.ring_size = new_size
            for key, old_buf in self._deltas.items():
                self._deltas[key] = deque(old_buf, maxlen=new_size)

    def tick(self) -> None:
        """Called each poll interval. Fetches stats, diffs, stores."""
        raw = self._fetch_perf_data()
        if raw is None:
            self._error_count += 1
            return

        snapshots = self._parse_snapshots(raw)
        now = time.time()

        with self._lock:
            for key, snap in snapshots.items():
                prev = self._prev.get(key)
                if prev is not None:
                    delta = self._diff(prev, snap)
                    if delta is not None:
                        buf = self._deltas.setdefault(
                            key, deque(maxlen=self.ring_size))
                        buf.append(delta)

                self._prev[key] = snap
                self._last_seen[key] = now
                if key not in self._first_seen:
                    self._first_seen[key] = now
                self._metadata[key] = snap.metadata

            self._evict_stale(now)

        self._last_poll_time = now
        self._poll_count += 1

    def _fetch_perf_data(self) -> Optional[dict]:
        """Call into stats module via remote() to get perf data."""
        try:
            retval, data_json, err = self.module.remote(
                'stats', 'handle_command', '',
                {'prefix': 'fs perf stats'})
            if retval != 0:
                logger.warning("stats module returned %d: %s", retval, err)
                return None
            return json.loads(data_json)
        except ImportError:
            logger.error("stats module is not enabled; "
                         "enable it with: ceph mgr module enable stats")
            return None
        except Exception as e:
            logger.error("Failed to fetch perf data: %s", e)
            return None

    def _parse_snapshots(self, raw: dict) -> Dict[ClientKey, ClientSnapshot]:
        """Parse raw stats JSON into ClientSnapshot objects."""
        snapshots = {}
        now = time.time()

        global_metrics = raw.get("global_metrics", {})
        client_metadata = raw.get("client_metadata", {})

        for fs_name, clients in global_metrics.items():
            fs_meta = client_metadata.get(fs_name, {})
            for client_id, counters in clients.items():
                if not counters or len(counters) < 16:
                    continue

                meta = fs_meta.get(client_id, {})
                metadata = {
                    "hostname": meta.get("hostname", ""),
                    "root": meta.get("root", ""),
                    "mount_point": meta.get("mount_point", ""),
                    "IP": meta.get("IP", ""),
                }

                snap = ClientSnapshot(
                    timestamp=now,
                    client_id=client_id,
                    fs_name=fs_name,
                    metadata=metadata,
                    cap_hits=self._safe_int(counters[IDX_CAP_HIT], 0),
                    cap_misses=self._safe_int(counters[IDX_CAP_HIT], 1),
                    dentry_hits=self._safe_int(counters[IDX_DENTRY_LEASE], 0),
                    dentry_misses=self._safe_int(counters[IDX_DENTRY_LEASE], 1),
                    read_ops=self._safe_int(counters[IDX_READ_IO_SIZES], 0),
                    read_bytes=self._safe_int(counters[IDX_READ_IO_SIZES], 1),
                    write_ops=self._safe_int(counters[IDX_WRITE_IO_SIZES], 0),
                    write_bytes=self._safe_int(counters[IDX_WRITE_IO_SIZES], 1),
                    opened_files=self._safe_scalar(counters[IDX_OPENED_FILES]),
                    opened_inodes=self._safe_scalar(counters[IDX_OPENED_INODES]),
                    avg_read_lat=self._safe_float(counters[IDX_AVG_READ_LAT]),
                    stdev_read_lat=self._safe_float(counters[IDX_STDEV_READ_LAT]),
                    avg_write_lat=self._safe_float(counters[IDX_AVG_WRITE_LAT]),
                    stdev_write_lat=self._safe_float(counters[IDX_STDEV_WRITE_LAT]),
                    avg_meta_lat=self._safe_float(counters[IDX_AVG_META_LAT]),
                    stdev_meta_lat=self._safe_float(counters[IDX_STDEV_META_LAT]),
                )
                snapshots[(fs_name, client_id)] = snap

        return snapshots

    @staticmethod
    def _safe_int(counter, index: int) -> int:
        """Extract an int from a counter value which may be a list or scalar."""
        if isinstance(counter, (list, tuple)):
            if index < len(counter):
                return int(counter[index])
            return 0
        return int(counter) if index == 0 else 0

    @staticmethod
    def _safe_scalar(counter) -> int:
        """Extract a scalar int from a counter which may be a list or scalar."""
        if isinstance(counter, (list, tuple)):
            return int(counter[0]) if counter else 0
        return int(counter)

    @staticmethod
    def _safe_float(counter) -> float:
        """Extract a float from a counter which may be a list or scalar."""
        if isinstance(counter, (list, tuple)):
            return float(counter[0]) if counter else 0.0
        return float(counter)

    def _diff(self, old: ClientSnapshot, new: ClientSnapshot) -> Optional[ClientDelta]:
        """Compute diff between two snapshots. Returns None if counter reset detected."""
        d_read_ops = new.read_ops - old.read_ops
        d_read_bytes = new.read_bytes - old.read_bytes
        d_write_ops = new.write_ops - old.write_ops
        d_write_bytes = new.write_bytes - old.write_bytes
        d_cap_hits = new.cap_hits - old.cap_hits
        d_cap_misses = new.cap_misses - old.cap_misses
        d_dentry_hits = new.dentry_hits - old.dentry_hits
        d_dentry_misses = new.dentry_misses - old.dentry_misses

        # Counter reset detection: any cumulative counter going negative
        if (d_read_ops < 0 or d_read_bytes < 0 or
                d_write_ops < 0 or d_write_bytes < 0 or
                d_cap_hits < 0 or d_cap_misses < 0 or
                d_dentry_hits < 0 or d_dentry_misses < 0):
            logger.debug("Counter reset detected for %s/%s, discarding delta",
                         new.fs_name, new.client_id)
            return None

        interval = new.timestamp - old.timestamp
        if interval <= 0:
            return None

        wall_hour = datetime.fromtimestamp(new.timestamp).hour

        return ClientDelta(
            timestamp=new.timestamp,
            interval_secs=interval,
            wall_hour=wall_hour,
            d_read_ops=d_read_ops,
            d_read_bytes=d_read_bytes,
            d_write_ops=d_write_ops,
            d_write_bytes=d_write_bytes,
            d_cap_hits=d_cap_hits,
            d_cap_misses=d_cap_misses,
            d_dentry_hits=d_dentry_hits,
            d_dentry_misses=d_dentry_misses,
            avg_read_lat=new.avg_read_lat,
            avg_write_lat=new.avg_write_lat,
            avg_meta_lat=new.avg_meta_lat,
            opened_files=new.opened_files,
            opened_inodes=new.opened_inodes,
        )

    def _evict_stale(self, now: float) -> None:
        """Remove clients that haven't been seen for client_ttl seconds."""
        stale_keys = [
            k for k, t in self._last_seen.items()
            if now - t > self.client_ttl
        ]
        for key in stale_keys:
            self._prev.pop(key, None)
            self._deltas.pop(key, None)
            self._first_seen.pop(key, None)
            self._last_seen.pop(key, None)
            self._metadata.pop(key, None)
            logger.debug("Evicted stale client: %s/%s", key[0], key[1])

    # --- Public accessors (thread-safe) ---

    def get_deltas(self, fs_name: str, client_id: str) -> List[ClientDelta]:
        """Return a copy of the delta ring buffer for a specific client."""
        with self._lock:
            buf = self._deltas.get((fs_name, client_id))
            if buf is None:
                return []
            return list(buf)

    def get_all_deltas(self) -> Dict[ClientKey, List[ClientDelta]]:
        """Return copies of all delta ring buffers."""
        with self._lock:
            return {k: list(v) for k, v in self._deltas.items()}

    def get_active_clients(self) -> List[ClientKey]:
        """Return list of (fs_name, client_id) tuples for active clients."""
        with self._lock:
            return list(self._deltas.keys())

    def get_metadata(self, fs_name: str, client_id: str) -> Dict:
        """Return metadata for a specific client."""
        with self._lock:
            return dict(self._metadata.get((fs_name, client_id), {}))

    def get_first_seen(self, fs_name: str, client_id: str) -> Optional[float]:
        with self._lock:
            return self._first_seen.get((fs_name, client_id))

    def get_last_seen(self, fs_name: str, client_id: str) -> Optional[float]:
        with self._lock:
            return self._last_seen.get((fs_name, client_id))

    def get_status(self) -> Dict:
        """Return profiler status summary."""
        with self._lock:
            clients = {}
            for key, buf in self._deltas.items():
                clients[f"{key[0]}/{key[1]}"] = len(buf)
            return {
                "active_clients": len(self._deltas),
                "total_polls": self._poll_count,
                "total_errors": self._error_count,
                "last_poll_time": (datetime.fromtimestamp(self._last_poll_time).isoformat()
                                   if self._last_poll_time else None),
                "ring_buffer_size": self.ring_size,
                "client_ttl": self.client_ttl,
                "clients": clients,
            }

    def reset(self, fs_name: Optional[str] = None,
              client_id: Optional[str] = None) -> int:
        """Clear profiling data. Returns number of clients cleared."""
        with self._lock:
            if fs_name and client_id:
                key = (fs_name, client_id)
                found = any(key in d for d in [
                    self._deltas, self._prev, self._first_seen,
                    self._last_seen, self._metadata])
                self._deltas.pop(key, None)
                self._prev.pop(key, None)
                self._first_seen.pop(key, None)
                self._last_seen.pop(key, None)
                self._metadata.pop(key, None)
                return 1 if found else 0
            elif fs_name:
                all_dicts = [self._deltas, self._prev, self._first_seen,
                             self._last_seen, self._metadata]
                keys_to_remove = set()
                for d in all_dicts:
                    keys_to_remove.update(k for k in d if k[0] == fs_name)
                for key in keys_to_remove:
                    for d in all_dicts:
                        d.pop(key, None)
                return len(keys_to_remove)
            else:
                count = len(set(self._deltas) | set(self._prev) |
                            set(self._first_seen))
                self._deltas.clear()
                self._prev.clear()
                self._first_seen.clear()
                self._last_seen.clear()
                self._metadata.clear()
                return count
