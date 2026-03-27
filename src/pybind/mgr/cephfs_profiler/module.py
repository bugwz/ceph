"""
CephFS Client Profiler MGR Module

A zero-intrusion module that profiles CephFS client I/O behavior by polling
the existing stats module, computing diffs on cumulative counters, and
generating multi-dimensional client portraits.

Enable with: ceph mgr module enable cephfs_profiler
"""

import errno
import json
from datetime import datetime
from threading import Event
from typing import Any, List, Optional, TYPE_CHECKING

from mgr_module import HandleCommandResult, MgrModule, Option

from .cli import CephfsProfilerCLICommand
from .collector import ClientProfiler
from .persistence import PersistenceManager
from .portrait import PortraitBuilder


class Module(MgrModule):
    CLICommand = CephfsProfilerCLICommand

    MODULE_OPTIONS = [
        Option(name='poll_interval',
               type='secs',
               default=60,
               desc='How often to poll stats module for client metrics (seconds)',
               runtime=True),
        Option(name='ring_buffer_size',
               type='int',
               default=1440,
               desc='Max number of delta records per client (1440 = 24h at 60s)',
               runtime=True),
        Option(name='client_ttl',
               type='secs',
               default=300,
               desc='Seconds of inactivity before evicting a client',
               runtime=True),
        Option(name='classification_threshold',
               type='float',
               default=0.7,
               desc='Threshold for workload type classification (0.0-1.0)',
               runtime=True),
        Option(name='daily_persist_hour',
               type='int',
               default=0,
               desc='Hour of day (0-23) to persist daily summaries',
               runtime=True),
        Option(name='retention_days',
               type='int',
               default=30,
               desc='Number of days to retain daily portrait summaries',
               runtime=True),
    ]

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.run = True
        self.event = Event()
        self.config_notify()

        self.profiler = ClientProfiler(
            self,
            ring_size=self.ring_buffer_size,
            client_ttl=self.client_ttl,
        )
        self._last_persist_date: Optional[str] = None

        if TYPE_CHECKING:
            self.poll_interval = 60
            self.ring_buffer_size = 1440
            self.client_ttl = 300
            self.classification_threshold = 0.7
            self.daily_persist_hour = 0
            self.retention_days = 30

    def config_notify(self) -> None:
        """Called when config options change."""
        for opt in self.MODULE_OPTIONS:
            setattr(self, opt['name'], self.get_module_option(opt['name']))
            self.log.debug('option %s = %s', opt['name'], getattr(self, opt['name']))

        # Clamp daily_persist_hour to 0-23
        if not (0 <= self.daily_persist_hour <= 23):
            self.log.warning("daily_persist_hour %d out of range, clamping to 0-23",
                             self.daily_persist_hour)
            self.daily_persist_hour = max(0, min(23, self.daily_persist_hour))

        # Clamp retention_days to >= 1
        if self.retention_days < 1:
            self.log.warning("retention_days %d is invalid, clamping to 1",
                             self.retention_days)
            self.retention_days = 1

        # Update profiler settings if it exists
        if hasattr(self, 'profiler'):
            self.profiler.update_ring_size(self.ring_buffer_size)
            self.profiler.client_ttl = self.client_ttl

    def serve(self) -> None:
        """Background polling loop."""
        self.log.info("cephfs_profiler starting (poll_interval=%s, ring_size=%s)",
                      self.poll_interval, self.ring_buffer_size)
        while self.run:
            try:
                self.profiler.tick()
                self._maybe_persist_daily()
            except Exception:
                self.log.exception("Error in profiler tick")

            self.event.wait(self.poll_interval or 60)
            self.event.clear()

    def shutdown(self) -> None:
        """Stop the background loop."""
        self.log.info("cephfs_profiler stopping")
        self.run = False
        self.event.set()

    def _maybe_persist_daily(self) -> None:
        """Persist daily portraits once per day at the configured hour."""
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        if self._last_persist_date == today:
            return
        if now.hour < self.daily_persist_hour:
            return

        self.log.info("Persisting daily portrait summaries for %s", today)
        for key in self.profiler.get_active_clients():
            fs_name, client_id = key
            deltas = self.profiler.get_deltas(fs_name, client_id)
            meta = self.profiler.get_metadata(fs_name, client_id)
            first_seen = self.profiler.get_first_seen(fs_name, client_id)
            last_seen = self.profiler.get_last_seen(fs_name, client_id)

            portrait = PortraitBuilder.build(
                client_id, fs_name, meta, deltas,
                first_seen=first_seen, last_seen=last_seen,
                classification_threshold=self.classification_threshold)

            PersistenceManager.save_daily_portrait(self, portrait, today)

        PersistenceManager.prune_old(self, self.retention_days)
        PersistenceManager.save_persist_time(self, now.isoformat())
        self._last_persist_date = today

    # ---- CLI Commands ----

    @CephfsProfilerCLICommand.Read('cephfs profiler status')
    def cmd_status(self) -> HandleCommandResult:
        """Show profiler module status."""
        status = self.profiler.get_status()
        status["config"] = {
            "poll_interval": self.poll_interval,
            "ring_buffer_size": self.ring_buffer_size,
            "client_ttl": self.client_ttl,
            "classification_threshold": self.classification_threshold,
            "daily_persist_hour": self.daily_persist_hour,
            "retention_days": self.retention_days,
        }
        return HandleCommandResult(stdout=json.dumps(status, indent=2))

    @CephfsProfilerCLICommand.Read('cephfs profiler portrait')
    def cmd_portrait(self,
                     fs_name: Optional[str] = None,
                     client_id: Optional[str] = None) -> HandleCommandResult:
        """Show client behavior portrait. Specify --fs-name and --client-id for a single client."""
        if fs_name and client_id:
            return self._portrait_single(fs_name, client_id)
        return self._portrait_all(fs_name)

    def _portrait_single(self, fs_name: str, client_id: str) -> HandleCommandResult:
        deltas = self.profiler.get_deltas(fs_name, client_id)
        if not deltas:
            return HandleCommandResult(
                retval=-errno.ENOENT,
                stderr=f"No profiling data for {fs_name}/{client_id}")

        meta = self.profiler.get_metadata(fs_name, client_id)
        first_seen = self.profiler.get_first_seen(fs_name, client_id)
        last_seen = self.profiler.get_last_seen(fs_name, client_id)

        portrait = PortraitBuilder.build(
            client_id, fs_name, meta, deltas,
            first_seen=first_seen, last_seen=last_seen,
            classification_threshold=self.classification_threshold)

        return HandleCommandResult(stdout=json.dumps(portrait.to_dict(), indent=2))

    def _portrait_all(self, fs_name: Optional[str] = None) -> HandleCommandResult:
        results = []
        for key in self.profiler.get_active_clients():
            fs, cid = key
            if fs_name and fs != fs_name:
                continue
            deltas = self.profiler.get_deltas(fs, cid)
            meta = self.profiler.get_metadata(fs, cid)
            first_seen = self.profiler.get_first_seen(fs, cid)
            last_seen = self.profiler.get_last_seen(fs, cid)

            portrait = PortraitBuilder.build(
                cid, fs, meta, deltas,
                first_seen=first_seen, last_seen=last_seen,
                classification_threshold=self.classification_threshold)
            results.append(portrait.to_dict())

        return HandleCommandResult(stdout=json.dumps(results, indent=2))

    @CephfsProfilerCLICommand.Read('cephfs profiler list')
    def cmd_list(self, fs_name: Optional[str] = None) -> HandleCommandResult:
        """List all profiled clients with summary classification."""
        summaries = []
        for key in self.profiler.get_active_clients():
            fs, cid = key
            if fs_name and fs != fs_name:
                continue
            deltas = self.profiler.get_deltas(fs, cid)
            meta = self.profiler.get_metadata(fs, cid)
            first_seen = self.profiler.get_first_seen(fs, cid)
            last_seen = self.profiler.get_last_seen(fs, cid)

            portrait = PortraitBuilder.build(
                cid, fs, meta, deltas,
                first_seen=first_seen, last_seen=last_seen,
                classification_threshold=self.classification_threshold)
            summaries.append(PortraitBuilder.build_summary(portrait))

        return HandleCommandResult(stdout=json.dumps(summaries, indent=2))

    @CephfsProfilerCLICommand.Read('cephfs profiler top')
    def cmd_top(self, metric: Optional[str] = None,
                count: Optional[int] = None) -> HandleCommandResult:
        """Show top-N clients by metric (throughput, ops, latency). Default: throughput, top 10."""
        metric = metric or "throughput"
        n = count or 10

        valid_metrics = ["throughput", "ops", "latency"]
        if metric not in valid_metrics:
            return HandleCommandResult(
                retval=-errno.EINVAL,
                stderr=f"Invalid metric '{metric}'. Choose from: {valid_metrics}")

        portraits = []
        for key in self.profiler.get_active_clients():
            fs, cid = key
            deltas = self.profiler.get_deltas(fs, cid)
            meta = self.profiler.get_metadata(fs, cid)
            portrait = PortraitBuilder.build(
                cid, fs, meta, deltas,
                classification_threshold=self.classification_threshold)
            portraits.append(portrait)

        # Sort by chosen metric
        if metric == "throughput":
            portraits.sort(
                key=lambda p: p.avg_read_throughput_MBps + p.avg_write_throughput_MBps,
                reverse=True)
        elif metric == "ops":
            portraits.sort(
                key=lambda p: p.total_read_ops + p.total_write_ops,
                reverse=True)
        elif metric == "latency":
            portraits.sort(
                key=lambda p: max(p.avg_read_lat_ms, p.avg_write_lat_ms),
                reverse=True)

        top_n = [PortraitBuilder.build_summary(p) for p in portraits[:n]]
        return HandleCommandResult(stdout=json.dumps(top_n, indent=2))

    @CephfsProfilerCLICommand.Read('cephfs profiler timeseries')
    def cmd_timeseries(self, fs_name: str,
                       client_id: str) -> HandleCommandResult:
        """Return raw timeseries delta data for a specific client."""
        deltas = self.profiler.get_deltas(fs_name, client_id)
        if not deltas:
            return HandleCommandResult(
                retval=-errno.ENOENT,
                stderr=f"No profiling data for {fs_name}/{client_id}")

        result = {
            "client_id": client_id,
            "fs_name": fs_name,
            "count": len(deltas),
            "deltas": [d.to_dict() for d in deltas],
        }
        return HandleCommandResult(stdout=json.dumps(result, indent=2))

    @CephfsProfilerCLICommand.Read('cephfs profiler history')
    def cmd_history(self, fs_name: str, client_id: str,
                    days: Optional[int] = None) -> HandleCommandResult:
        """Show stored daily portrait history for a client."""
        days = days or 30
        history = PersistenceManager.load_history(self, fs_name, client_id, days)
        if not history:
            return HandleCommandResult(
                retval=-errno.ENOENT,
                stderr=f"No stored history for {fs_name}/{client_id}")

        result = {
            "client_id": client_id,
            "fs_name": fs_name,
            "days_requested": days,
            "records": len(history),
            "history": history,
        }
        return HandleCommandResult(stdout=json.dumps(result, indent=2))

    @CephfsProfilerCLICommand.Write('cephfs profiler reset')
    def cmd_reset(self, fs_name: Optional[str] = None,
                  client_id: Optional[str] = None) -> HandleCommandResult:
        """Clear profiling data. Optionally specify --fs-name and --client-id."""
        if client_id and not fs_name:
            return HandleCommandResult(
                retval=-errno.EINVAL,
                stderr="--fs-name is required when --client-id is specified")

        # Clear in-memory data
        cleared = self.profiler.reset(fs_name, client_id)

        # Clear persisted history
        deleted = PersistenceManager.reset_history(self, fs_name, client_id)

        return HandleCommandResult(
            stdout=json.dumps({
                "cleared_clients": cleared,
                "deleted_history_records": deleted,
            }, indent=2))
