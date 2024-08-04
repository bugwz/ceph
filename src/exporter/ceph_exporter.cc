#include "common/ceph_argparse.h"
#include "common/config.h"
#include "exporter/DaemonMetricCollector.h"
#include "exporter/http_server.h"
#include "global/global_context.h"
#include "global/global_init.h"

#include <boost/thread/thread.hpp>
#include <iostream>
#include <map>
#include <string>

#define dout_context g_ceph_context

static void usage()
{
    std::cout
        << "usage: ceph-exporter [options]\n"
        << "options:\n"
           "  --sock-dir:     The path to ceph daemons socket files dir\n"
           "  --addrs:        Host ip address where exporter is deployed\n"
           "  --port:         Port to deploy exporter on. Default is 9926\n"
           "  --prio-limit:   Only perf counters greater than or equal to prio-limit are fetched. Default: 5\n"
           "  --stats-period: Time to wait before sending requests again to exporter server (seconds). Default: 5s"
        << std::endl;
    generic_server_usage();
}

int main(int argc, char** argv)
{

    auto args = argv_to_vec(argc, argv);
    if (args.empty()) {
        std::cerr << argv[0] << ": -h or --help for usage" << std::endl;
        exit(1);
    }
    if (ceph_argparse_need_usage(args)) {
        usage();
        exit(0);
    }

    auto cct = global_init(NULL, args, CEPH_ENTITY_TYPE_CLIENT, CODE_ENVIRONMENT_DAEMON, 0);
    std::string val;
    for (auto i = args.begin(); i != args.end();) {
        if (ceph_argparse_double_dash(args, i)) {
            break;
        }
        else if (ceph_argparse_witharg(args, i, &val, "--sock-dir", (char*)NULL)) {
            cct->_conf.set_val("exporter_sock_dir", val);
        }
        else if (ceph_argparse_witharg(args, i, &val, "--addrs", (char*)NULL)) {
            cct->_conf.set_val("exporter_addr", val);
        }
        else if (ceph_argparse_witharg(args, i, &val, "--port", (char*)NULL)) {
            cct->_conf.set_val("exporter_http_port", val);
        }
        else if (ceph_argparse_witharg(args, i, &val, "--prio-limit", (char*)NULL)) {
            cct->_conf.set_val("exporter_prio_limit", val);
        }
        else if (ceph_argparse_witharg(args, i, &val, "--stats-period", (char*)NULL)) {
            cct->_conf.set_val("exporter_stats_period", val);
        }
        else {
            ++i;
        }
    }
    common_init_finish(g_ceph_context);

    // http server 线程， 用于响应 http 请求的 exporter 数据请求
    // 注意： 这里导出的数据是 ceph 组件粒度的数据信息，资源 exporter 的端口为 9926 ，
    //       这个数据不同于 prometheus 模块中导出来的数据，那么模块的 exporter 的端口为 9283
    boost::thread server_thread(http_server_thread_entrypoint);
    DaemonMetricCollector& collector = collector_instance();
    collector.main();
    server_thread.join();
}
