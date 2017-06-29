'''
Task to deploy clusters with DeepSea
'''
import logging
import time

from teuthology import misc
from teuthology.orchestra import run
from teuthology.salt import Salt
from teuthology.task import Task
from teuthology.job_status import get_status
from util import get_remote_for_role

log = logging.getLogger(__name__)

class DeepSea(Task):
    """
    Automated DeepSea integration testing via teuthology: set up a Salt
    cluster, clone the DeepSea git repo, run DeepSea integration test(s) 

    The number of machines in the cluster is determined by the roles stanza, as
    usual. One, and only one, of the machines must have a role of type
    "master", e.g.  master.1 or master.a (the part following the dot is not
    significant, but must be there).

    The task starts the Salt Master daemon on the master node, and Salt Minion
    daemons on all the nodes (including the master node), and ensures that the
    minions are properly linked to the master. TODO: The role types are stored
    in the role grain on the minions.

    After that, the DeepSea git repo is cloned to the master node in
    accordance with the "repo" and "branch" options, if given (see below).

    Finally, the task iterates over the list of commands given in the "exec"
    property, executing each one inside the 'qa/' directory of the DeepSea repo
    clone.

    Possible options for this task are:

        repo: (DeepSea git repo, defaults to https://github.com/SUSE/DeepSea.git)
        branch: (DeepSea git branch, defaults to master)
        exec: (list of commands, relative to qa/ of the DeepSea repo)

    Example:

        tasks
        - deepsea:
            exec:
            - suites/basic/health-ok.sh

    :param ctx: the argparse.Namespace object
    :param config: the config dict
    """
    def __init__(self, ctx, config):
        super(DeepSea, self).__init__(ctx, config)

        log.debug("Initial config is {}".format(config))

        # make sure self.config dict has values for important keys
        if config is None:
            config = {}
        assert isinstance(config, dict), \
            'deepsea task only accepts a dict for configuration'
        self.config["repo"] = config.get('repo', 'https://github.com/SUSE/DeepSea.git')
        self.config["branch"] = config.get('branch', 'master')
        self.config["exec"] = config.get('exec', ['suites/basic/health-ok.sh'])
        assert isinstance(self.config["exec"], list), \
            'exec property of deepsea yaml must be a list'

        log.debug("Munged config is {}".format(config))

        # prepare the list of commands to be executed on the master node
        self.exec_cmd = []
        assert len(self.config["exec"]) > 0, \
            'deepsea exec list must have at least one element'
        for cmd in self.config["exec"]:
            self.exec_cmd.append('cd DeepSea/qa ; ' + cmd)

        # determine the role id of the master role
        if(misc.num_instances_of_type(self.cluster, 'master') != 1):
            raise ConfigError('deepsea requires a single master role')
        id_ = next(misc.all_roles_of_type(self.ctx.cluster, 'master'))
        master_role = '.'.join(['master', str(id_)])

        # set remote name for salt to pick it up. Setting the remote itself will
        # crash the reporting tool since it doesn't know how to turn the object
        # into a string
        self.config["master_remote"] = get_remote_for_role(self.ctx,
                master_role).name
        self.log.info("master remote: {}".format(self.config["master_remote"]))
        self.salt = Salt(self.ctx, self.config)

    def setup(self):
        super(DeepSea, self).setup()

        self.log.info("DeepSea repo: {}".format(self.config["repo"]))
        self.log.info("DeepSea branch: {}".format(self.config["branch"]))

        self.salt.master_remote.run(args=[
            'git',
            'clone',
            '--depth',
            '1',
            '--branch',
            self.config["branch"],
            self.config["repo"],
            ])

        self.log.info("printing DeepSea branch name and sha1...")
        self.salt.master_remote.run(args=[
            'cd',
            'DeepSea',
            run.Raw(';'),
            'git',
            'rev-parse',
            '--abbrev-ref',
            'HEAD',
            run.Raw(';'),
            'git',
            'rev-parse',
            'HEAD',
            ])

        self.log.info("Running \"make install\" in DeepSea clone...")
        self.salt.master_remote.run(args=[
            'cd',
            'DeepSea',
            run.Raw(';'),
            'sudo',
            'make',
            'install',
            ])

        self.log.info("installing deepsea dependencies...")
        self.salt.master_remote.run(args = [
            'sudo',
            'zypper',
            '--non-interactive',
            'install',
            '--no-recommends',
            run.Raw('$(rpmspec --requires -q -v DeepSea/deepsea.spec | grep manual | awk \'{print $2}\')')
            ])

        self.log.info("listing minion keys...")
        self.salt.master_remote.run(args = ['sudo', 'salt-key', '-L'])

        self.log.info("iterating over all the test nodes...")
        for _remote, roles_for_host in self.ctx.cluster.remotes.iteritems():
            self.log.info("minion configuration for {}".format(_remote.hostname))
            _remote.run(args = ['sudo', 'systemctl', 'status',
                'salt-minion.service'])
            _remote.run(args = ['sudo', 'cat', '/etc/salt/minion_id'])
            _remote.run(args = ['sudo', 'cat', '/etc/salt/minion.d/master.conf'])

        self.salt.ping_minions()

    def begin(self):
        super(DeepSea, self).begin()
        for cmd in self.exec_cmd:
            self.log.info(
                "command to be executed on master node: {}".format(cmd)
                )
            self.salt.master_remote.run(args=[
                'sudo', 'sh', '-c',
                cmd
                ])

    def purge_osds(self):
        # replace this hack with DeepSea purge when it's ready
        for _remote, _ in self.ctx.cluster.remotes.iteritems():
            self.log.info("stopping OSD services on {}"
                .format(_remote.hostname))
            _remote.run(args=[
                'sudo', 'sh', '-c',
                'systemctl stop ceph-osd.target ; sleep 10'
                ])
            self.log.info("unmounting OSD data devices on {}"
                .format(_remote.hostname))
            _remote.run(args=[
                'sudo', 'sh', '-c',
                'for f in vdb2 vdc2 ; do test -b /dev/$f && umount /dev/$f || true ; done'
                ])

    def gather_nfs_ganesha_log(self):
        self.log.info("gathering NFS-Ganesha log")
        self.log.info("summary: {}".format(self.ctx.summary))

    def end(self):
        self.purge_osds()
        self.gather_nfs_ganesha_log()
        super(DeepSea, self).end()

task = DeepSea
