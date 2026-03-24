"""
performance stats for ceph filesystem (for now...)
"""

import json
from typing import List, Dict

from .cli import StatsCLICommand

from mgr_module import MgrModule, Option, NotifyType

from .fs.perf_stats import FSPerfStats
from .fs.hotspot_dirs import FSHotspotDirs

class Module(MgrModule):
    CLICommand = StatsCLICommand
    COMMANDS = [
        {
            "cmd": "fs perf stats "
                   "name=mds_rank,type=CephString,req=false "
                   "name=client_id,type=CephString,req=false "
                   "name=client_ip,type=CephString,req=false ",
            "desc": "retrieve ceph fs performance stats",
            "perm": "r"
        },
        {
            "cmd": "fs hotspot dirs "
                   "name=fs_name,type=CephString,req=false "
                   "name=mds_rank,type=CephInt,req=false "
                   "name=limit,type=CephInt,req=false ",
            "desc": "retrieve hotspot directory data across MDS ranks",
            "perm": "r"
        },
        {
            "cmd": "fs hotspot files "
                   "name=fs_name,type=CephString,req=false "
                   "name=mds_rank,type=CephInt,req=false "
                   "name=limit,type=CephInt,req=false ",
            "desc": "retrieve hotspot file data across MDS ranks",
            "perm": "r"
        },
    ]
    MODULE_OPTIONS: List[Option] = []
    NOTIFY_TYPES = [NotifyType.command, NotifyType.fs_map]

    def __init__(self, *args, **kwargs):
        super(Module, self).__init__(*args, **kwargs)
        self.fs_perf_stats = FSPerfStats(self)
        self.fs_hotspot_dirs = FSHotspotDirs(self)

    def notify(self, notify_type: NotifyType, notify_id):
        if notify_type == NotifyType.command:
            self.fs_perf_stats.notify_cmd(notify_id)
        elif notify_type == NotifyType.fs_map:
            self.fs_perf_stats.notify_fsmap()

    def handle_command(self, inbuf, cmd):
        prefix = cmd['prefix']
        if prefix.startswith('fs perf stats'):
            return self.fs_perf_stats.get_perf_data(cmd)
        elif prefix.startswith('fs hotspot dirs'):
            return self.fs_hotspot_dirs.get_hotspot_data(cmd)
        elif prefix.startswith('fs hotspot files'):
            return self.fs_hotspot_dirs.get_hotspot_files_data(cmd)
        raise NotImplementedError(cmd['prefix'])
