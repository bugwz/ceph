import json
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


class FSHotspotDirs:
    """Aggregates hotspot directory data across multiple MDS ranks."""

    def __init__(self, module):
        self.module = module

    def _get_active_mds_ranks(self, fs_name=None):
        """Enumerate active MDS ranks from the filesystem map.

        Returns a list of (fs_name, rank, gid) tuples for all active MDS ranks.
        """
        fsmap = self.module.get('fs_map')
        results = []
        for fs in fsmap.get('filesystems', []):
            mds_map = fs['mdsmap']
            name = mds_map['fs_name']
            if fs_name and name != fs_name:
                continue
            for gid_key, mds_info in mds_map.get('info', {}).items():
                if mds_info.get('state', '').startswith('up:active'):
                    results.append((name, mds_info['rank'], mds_info['gid']))
        return results

    def _query_rank(self, gid, command):
        """Send a command to a single MDS rank via tell_command.

        Returns (success, parsed_data_or_error_string).
        """
        cmd_dict = {'prefix': command, 'format': 'json'}
        try:
            r, outb, outs = self.module.tell_command(
                'mds', str(gid), cmd_dict)
            if r != 0:
                return False, outs or "command returned {}".format(r)
            return True, json.loads(outb)
        except Exception as e:
            log.warning("Failed to query MDS gid %s cmd '%s': %s",
                        gid, command, e)
            return False, str(e)

    def _aggregate_dirs(self, per_rank_data, limit):
        """Merge hotspot dirs from multiple ranks into a unified top-N list.

        For duplicate paths across ranks, use max(score) as the sort key and
        record all contributing ranks with their individual scores.
        """
        path_map = {}
        for rank_str, rank_data in per_rank_data.items():
            if rank_data.get('status') != 'ok':
                continue
            rank = int(rank_str)
            for entry in rank_data.get('hotspot_dirs', []):
                path = entry.get('path', '')
                score = entry.get('score', 0.0)
                if path not in path_map:
                    path_map[path] = {
                        'path': path,
                        'dirfrag': entry.get('dirfrag', ''),
                        'max_score': score,
                        'total_score': score,
                        'reporting_ranks': {rank: score},
                        'pop_me': entry.get('pop_me', {}),
                    }
                else:
                    existing = path_map[path]
                    existing['reporting_ranks'][rank] = score
                    existing['total_score'] += score
                    if score > existing['max_score']:
                        existing['max_score'] = score
                        existing['dirfrag'] = entry.get('dirfrag', '')
                        existing['pop_me'] = entry.get('pop_me', {})

        aggregated = sorted(
            path_map.values(),
            key=lambda x: x['max_score'],
            reverse=True)[:limit]

        for entry in aggregated:
            entry['reporting_ranks'] = [
                {'rank': r, 'score': s}
                for r, s in sorted(entry['reporting_ranks'].items())
            ]
        return aggregated

    def _aggregate_files(self, per_rank_data, limit):
        """Merge hotspot files from multiple ranks into a unified top-N list."""
        path_map = {}
        for rank_str, rank_data in per_rank_data.items():
            if rank_data.get('status') != 'ok':
                continue
            rank = int(rank_str)
            for entry in rank_data.get('hotspot_files', []):
                path = entry.get('path', '')
                score = entry.get('score', 0.0)
                if path not in path_map:
                    path_map[path] = {
                        'path': path,
                        'ino': entry.get('ino', 0),
                        'max_score': score,
                        'total_score': score,
                        'reporting_ranks': {rank: score},
                        'pop_rd': entry.get('pop_rd', 0.0),
                        'pop_wr': entry.get('pop_wr', 0.0),
                    }
                else:
                    existing = path_map[path]
                    existing['reporting_ranks'][rank] = score
                    existing['total_score'] += score
                    if score > existing['max_score']:
                        existing['max_score'] = score
                        existing['ino'] = entry.get('ino', 0)
                        existing['pop_rd'] = entry.get('pop_rd', 0.0)
                        existing['pop_wr'] = entry.get('pop_wr', 0.0)

        aggregated = sorted(
            path_map.values(),
            key=lambda x: x['max_score'],
            reverse=True)[:limit]

        for entry in aggregated:
            entry['reporting_ranks'] = [
                {'rank': r, 'score': s}
                for r, s in sorted(entry['reporting_ranks'].items())
            ]
        return aggregated

    def _collect_and_aggregate(self, cmd, tell_cmd, data_key, aggregate_fn):
        """Common logic for collecting data from MDS ranks and aggregating."""
        fs_name = cmd.get('fs_name', None)
        mds_rank_filter = cmd.get('mds_rank', None)
        limit = int(cmd.get('limit', 20))

        if mds_rank_filter is not None:
            mds_rank_filter = int(mds_rank_filter)

        active_ranks = self._get_active_mds_ranks(fs_name)
        if mds_rank_filter is not None:
            active_ranks = [
                (n, r, g) for n, r, g in active_ranks
                if r == mds_rank_filter
            ]

        by_fs = {}
        for name, rank, gid in active_ranks:
            by_fs.setdefault(name, []).append((rank, gid))

        result = {
            'timestamp': datetime.now(timezone.utc).strftime(
                '%Y-%m-%dT%H:%M:%SZ'),
            'filesystems': {},
        }

        for name, ranks in sorted(by_fs.items()):
            fs_result = {'per_rank': {}, 'aggregated': []}
            for rank, gid in sorted(ranks):
                ok, data = self._query_rank(gid, tell_cmd)
                if ok:
                    items = data.get(data_key, [])
                    fs_result['per_rank'][str(rank)] = {
                        'status': 'ok',
                        data_key: items,
                    }
                else:
                    fs_result['per_rank'][str(rank)] = {
                        'status': 'error',
                        'error': data,
                    }

            fs_result['aggregated'] = aggregate_fn(
                fs_result['per_rank'], limit)
            result['filesystems'][name] = fs_result

        return 0, json.dumps(result, indent=2), ""

    def get_hotspot_data(self, cmd):
        """Entry point for 'fs hotspot dirs' command."""
        return self._collect_and_aggregate(
            cmd, 'dump hot dirs', 'hotspot_dirs',
            self._aggregate_dirs)

    def get_hotspot_files_data(self, cmd):
        """Entry point for 'fs hotspot files' command."""
        return self._collect_and_aggregate(
            cmd, 'dump hot files', 'hotspot_files',
            self._aggregate_files)
