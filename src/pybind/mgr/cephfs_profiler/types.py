"""
Data structures for CephFS client profiling.

ClientSnapshot: point-in-time capture of one client's counters.
ClientDelta: diff between two consecutive snapshots.
ClientPortrait: multi-dimensional behavior analysis result.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


@dataclass
class ClientSnapshot:
    """A frozen point-in-time capture of one client's performance counters."""
    timestamp: float          # time.time() when captured
    client_id: str            # e.g. "client.12345"
    fs_name: str
    metadata: Dict            # {hostname, root, mount_point, IP}

    # Cumulative counters (for diff calculation)
    cap_hits: int = 0
    cap_misses: int = 0
    dentry_hits: int = 0
    dentry_misses: int = 0
    read_ops: int = 0         # read_io_sizes[0]
    read_bytes: int = 0       # read_io_sizes[1]
    write_ops: int = 0        # write_io_sizes[0]
    write_bytes: int = 0      # write_io_sizes[1]

    # Instantaneous values (not diffed)
    opened_files: int = 0
    opened_inodes: int = 0
    avg_read_lat: float = 0.0
    stdev_read_lat: float = 0.0
    avg_write_lat: float = 0.0
    stdev_write_lat: float = 0.0
    avg_meta_lat: float = 0.0
    stdev_meta_lat: float = 0.0


@dataclass
class ClientDelta:
    """Diff between two consecutive ClientSnapshots, representing activity in one interval."""
    timestamp: float          # timestamp of the newer snapshot
    interval_secs: float      # time gap between the two snapshots
    wall_hour: int            # 0-23, hour of day when this delta was recorded

    # Diff increments (non-negative for valid deltas)
    d_read_ops: int = 0
    d_read_bytes: int = 0
    d_write_ops: int = 0
    d_write_bytes: int = 0
    d_cap_hits: int = 0
    d_cap_misses: int = 0
    d_dentry_hits: int = 0
    d_dentry_misses: int = 0

    # Instantaneous values from the newer snapshot
    avg_read_lat: float = 0.0
    avg_write_lat: float = 0.0
    avg_meta_lat: float = 0.0
    opened_files: int = 0
    opened_inodes: int = 0

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class HourlyActivity:
    """24-hour activity distribution."""
    read_ops_by_hour: List[int] = field(default_factory=lambda: [0] * 24)
    write_ops_by_hour: List[int] = field(default_factory=lambda: [0] * 24)
    metadata_ops_by_hour: List[int] = field(default_factory=lambda: [0] * 24)
    peak_hour: int = 0
    active_hours: List[int] = field(default_factory=list)


@dataclass
class ClientPortrait:
    """Multi-dimensional client behavior profile."""
    # Identity
    client_id: str = ""
    fs_name: str = ""
    hostname: str = ""
    mount_point: str = ""
    ip: str = ""
    first_seen: str = ""
    last_seen: str = ""
    profile_window_hours: float = 0.0
    sample_count: int = 0

    # Operation distribution
    total_read_ops: int = 0
    total_write_ops: int = 0
    total_metadata_ops: int = 0
    rw_ratio: float = 0.0        # read / (read + write), 0.0-1.0
    workload_classification: str = "idle"

    # Throughput (MB/s)
    avg_read_throughput_MBps: float = 0.0
    avg_write_throughput_MBps: float = 0.0
    peak_read_throughput_MBps: float = 0.0
    peak_write_throughput_MBps: float = 0.0

    # Average IO size (KB)
    avg_read_size_KB: float = 0.0
    avg_write_size_KB: float = 0.0

    # Latency (ms)
    avg_read_lat_ms: float = 0.0
    avg_write_lat_ms: float = 0.0
    avg_metadata_lat_ms: float = 0.0

    # 24-hour activity pattern
    hourly_activity: Optional[HourlyActivity] = None

    # Cache efficiency
    cap_hit_ratio: float = 0.0
    dentry_lease_hit_ratio: float = 0.0

    def to_dict(self) -> Dict:
        d = asdict(self)
        return d
