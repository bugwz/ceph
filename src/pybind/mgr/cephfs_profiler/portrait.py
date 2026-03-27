"""
PortraitBuilder: stateless analyzer that builds multi-dimensional client portraits
from a sequence of ClientDelta records.
"""

from datetime import datetime
from typing import Dict, List, Optional, Sequence

from .types import ClientDelta, ClientPortrait, HourlyActivity


class PortraitBuilder:
    """Builds a ClientPortrait from a sequence of ClientDelta records."""

    @staticmethod
    def build(client_id: str, fs_name: str, metadata: Dict,
              deltas: Sequence[ClientDelta],
              first_seen: Optional[float] = None,
              last_seen: Optional[float] = None,
              classification_threshold: float = 0.7) -> ClientPortrait:
        """
        Build a complete multi-dimensional portrait from delta records.

        Args:
            client_id: Client identifier (e.g. "client.12345")
            fs_name: Filesystem name
            metadata: Client metadata dict (hostname, mount_point, IP, etc.)
            deltas: Sequence of ClientDelta records from ring buffer
            first_seen: Timestamp when client was first observed
            last_seen: Timestamp when client was last observed
            classification_threshold: Threshold for workload classification (default 0.7)

        Returns:
            ClientPortrait with all analysis dimensions filled in.
        """
        portrait = ClientPortrait(
            client_id=client_id,
            fs_name=fs_name,
            hostname=metadata.get("hostname", ""),
            mount_point=metadata.get("mount_point", ""),
            ip=metadata.get("IP", ""),
            first_seen=(datetime.fromtimestamp(first_seen).isoformat()
                        if first_seen else ""),
            last_seen=(datetime.fromtimestamp(last_seen).isoformat()
                       if last_seen else ""),
            sample_count=len(deltas),
        )

        if not deltas:
            portrait.workload_classification = "idle"
            portrait.hourly_activity = HourlyActivity()
            return portrait

        # Compute profile window
        total_interval = sum(d.interval_secs for d in deltas)
        portrait.profile_window_hours = total_interval / 3600.0

        # 1. Operation distribution
        total_read_ops = sum(d.d_read_ops for d in deltas)
        total_write_ops = sum(d.d_write_ops for d in deltas)
        # Estimate metadata ops from cap hits + misses (proxy for metadata activity)
        total_metadata_ops = sum(d.d_cap_hits + d.d_cap_misses for d in deltas)

        portrait.total_read_ops = total_read_ops
        portrait.total_write_ops = total_write_ops
        portrait.total_metadata_ops = total_metadata_ops

        total_rw = total_read_ops + total_write_ops
        portrait.rw_ratio = (total_read_ops / total_rw) if total_rw > 0 else 0.0

        # Workload classification
        total_ops = total_read_ops + total_write_ops + total_metadata_ops
        portrait.workload_classification = PortraitBuilder._classify_workload(
            total_read_ops, total_write_ops, total_metadata_ops,
            total_ops, classification_threshold)

        # 2. Throughput analysis
        total_read_bytes = sum(d.d_read_bytes for d in deltas)
        total_write_bytes = sum(d.d_write_bytes for d in deltas)

        if total_interval > 0:
            portrait.avg_read_throughput_MBps = (
                total_read_bytes / total_interval / (1024 * 1024))
            portrait.avg_write_throughput_MBps = (
                total_write_bytes / total_interval / (1024 * 1024))

        # Peak throughput: max single-interval throughput
        peak_read_tp = 0.0
        peak_write_tp = 0.0
        for d in deltas:
            if d.interval_secs > 0:
                r_tp = d.d_read_bytes / d.interval_secs / (1024 * 1024)
                w_tp = d.d_write_bytes / d.interval_secs / (1024 * 1024)
                peak_read_tp = max(peak_read_tp, r_tp)
                peak_write_tp = max(peak_write_tp, w_tp)
        portrait.peak_read_throughput_MBps = peak_read_tp
        portrait.peak_write_throughput_MBps = peak_write_tp

        # 3. Average IO size
        if total_read_ops > 0:
            portrait.avg_read_size_KB = total_read_bytes / total_read_ops / 1024
        if total_write_ops > 0:
            portrait.avg_write_size_KB = total_write_bytes / total_write_ops / 1024

        # 4. Latency profile (average of instantaneous values)
        n = len(deltas)
        portrait.avg_read_lat_ms = sum(d.avg_read_lat for d in deltas) / n
        portrait.avg_write_lat_ms = sum(d.avg_write_lat for d in deltas) / n
        portrait.avg_metadata_lat_ms = sum(d.avg_meta_lat for d in deltas) / n

        # 5. 24-hour activity distribution
        portrait.hourly_activity = PortraitBuilder._build_hourly_activity(deltas)

        # 6. Cache efficiency
        total_cap_hits = sum(d.d_cap_hits for d in deltas)
        total_cap_total = total_cap_hits + sum(d.d_cap_misses for d in deltas)
        portrait.cap_hit_ratio = (
            total_cap_hits / total_cap_total if total_cap_total > 0 else 0.0)

        total_dentry_hits = sum(d.d_dentry_hits for d in deltas)
        total_dentry_total = total_dentry_hits + sum(d.d_dentry_misses for d in deltas)
        portrait.dentry_lease_hit_ratio = (
            total_dentry_hits / total_dentry_total if total_dentry_total > 0 else 0.0)

        return portrait

    @staticmethod
    def _classify_workload(read_ops: int, write_ops: int, meta_ops: int,
                           total_ops: int, threshold: float) -> str:
        """Classify workload based on operation distribution."""
        if total_ops == 0:
            return "idle"

        r = read_ops / total_ops
        w = write_ops / total_ops
        m = meta_ops / total_ops

        if r >= threshold:
            return "read-heavy"
        if w >= threshold:
            return "write-heavy"
        if m >= threshold:
            return "metadata-heavy"
        if r > w:
            return "read-biased"
        if w > r:
            return "write-biased"
        return "balanced"

    @staticmethod
    def _build_hourly_activity(deltas: Sequence[ClientDelta]) -> HourlyActivity:
        """Build 24-hour activity distribution from deltas."""
        activity = HourlyActivity()

        for d in deltas:
            h = d.wall_hour
            activity.read_ops_by_hour[h] += d.d_read_ops
            activity.write_ops_by_hour[h] += d.d_write_ops
            activity.metadata_ops_by_hour[h] += d.d_cap_hits + d.d_cap_misses

        # Total ops per hour
        total_by_hour = [
            activity.read_ops_by_hour[h] + activity.write_ops_by_hour[h] +
            activity.metadata_ops_by_hour[h]
            for h in range(24)
        ]

        peak_val = max(total_by_hour)
        activity.peak_hour = total_by_hour.index(peak_val) if peak_val > 0 else 0

        # Active hours: hours with ops > 10% of peak
        if peak_val > 0:
            threshold = peak_val * 0.1
            activity.active_hours = [
                h for h in range(24) if total_by_hour[h] > threshold
            ]
        else:
            activity.active_hours = []

        return activity

    @staticmethod
    def build_summary(portrait: ClientPortrait) -> Dict:
        """Build a compact summary dict for list view."""
        return {
            "client_id": portrait.client_id,
            "fs_name": portrait.fs_name,
            "hostname": portrait.hostname,
            "ip": portrait.ip,
            "workload": portrait.workload_classification,
            "read_ops": portrait.total_read_ops,
            "write_ops": portrait.total_write_ops,
            "avg_read_tp_MBps": round(portrait.avg_read_throughput_MBps, 2),
            "avg_write_tp_MBps": round(portrait.avg_write_throughput_MBps, 2),
            "rw_ratio": round(portrait.rw_ratio, 3),
            "cap_hit_ratio": round(portrait.cap_hit_ratio, 3),
            "samples": portrait.sample_count,
            "window_hours": round(portrait.profile_window_hours, 2),
        }
