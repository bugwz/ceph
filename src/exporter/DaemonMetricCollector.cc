#include "DaemonMetricCollector.h"

#include "common/admin_socket_client.h"
#include "common/debug.h"
#include "common/hostname.h"
#include "common/perf_counters.h"
#include "common/split.h"
#include "global/global_context.h"
#include "global/global_init.h"
#include "include/common_fwd.h"
#include "util.h"

#include <boost/json/src.hpp>
#include <chrono>
#include <filesystem>
#include <iostream>
#include <map>
#include <memory>
#include <regex>
#include <sstream>
#include <string>
#include <utility>

#define dout_context g_ceph_context
#define dout_subsys  ceph_subsys_ceph_exporter

using json_object = boost::json::object;
using json_value = boost::json::value;
using json_array = boost::json::array;

void DaemonMetricCollector::request_loop(boost::asio::steady_timer& timer)
{
    timer.async_wait([&](const boost::system::error_code& e) {
        std::cerr << e << std::endl;
        // 更新所需的 sockets 列表信息
        update_sockets();

        // 从 socket 中更新获取 metrics 数据
        dump_asok_metrics();

        // 根据 src/common/options 中的可以看出 exporter_stats_period 的默认值为 5 ，
        // 也就是说，每隔 5s 的时间，会执行一次 metrics 数据的获取。
        auto stats_period = g_conf().get_val<int64_t>("exporter_stats_period");
        // time to wait before sending requests again
        // 再次发送请求之前的等待时间
        timer.expires_from_now(std::chrono::seconds(stats_period));

        // 再次触发一次该函数的调用
        request_loop(timer);
    });
}

void DaemonMetricCollector::main()
{
    // time to wait before sending requests again

    boost::asio::io_service io;
    boost::asio::steady_timer timer{io, std::chrono::seconds(0)};
    // DaemonMetricCollector 在执行 main 之后，相当于会循环的调用 request_loop 函数
    request_loop(timer);
    io.run();
}

// 直接读取上次记录的 metrics 数据
// 另一个使用 metrics_mutex 锁的关联函数为 DaemonMetricCollector::dump_asok_metrics()
std::string DaemonMetricCollector::get_metrics()
{
    const std::lock_guard<std::mutex> lock(metrics_mutex);
    return metrics;
}

template<class T>
void add_metric(std::unique_ptr<MetricsBuilder>& builder, T value, std::string name, std::string description,
                std::string mtype, labels_t labels)
{
    builder->add(std::to_string(value), name, description, mtype, labels);
}

void add_double_or_int_metric(std::unique_ptr<MetricsBuilder>& builder, json_value value, std::string name,
                              std::string description, std::string mtype, labels_t labels)
{
    if (value.is_int64()) {
        int64_t v = value.as_int64();
        add_metric(builder, v, name, description, mtype, labels);
    }
    else if (value.is_double()) {
        double v = value.as_double();
        add_metric(builder, v, name, description, mtype, labels);
    }
}

std::string boost_string_to_std(boost::json::string js)
{
    std::string res(js.data());
    return res;
}

std::string quote(std::string value)
{
    return "\"" + value + "\"";
}

// 这里的函数会被 DaemonMetricCollector::request_loop 函数不断掉用
void DaemonMetricCollector::dump_asok_metrics()
{
    BlockTimer timer(__FILE__, __FUNCTION__);

    std::vector<std::pair<std::string, int>> daemon_pids;

    // 从 src/common/options 配置中的信息中可以看出 exporter_sort_metrics 默认值为 true
    // 所以这里会对 metrics 的数据进行排序。
    int failures = 0;
    bool sort = g_conf().get_val<bool>("exporter_sort_metrics");
    if (sort) {
        builder = std::unique_ptr<OrderedMetricsBuilder>(new OrderedMetricsBuilder());
    }
    else {
        builder = std::unique_ptr<UnorderedMetricsBuilder>(new UnorderedMetricsBuilder());
    }

    // 从 src/common/options 配置中的信息可以看出 exporter_sort_metrics 默认值为 5
    // 我们可以通过修改该值来到处更多的监控指标数据
    auto prio_limit = g_conf().get_val<int64_t>("exporter_prio_limit");
    // 这里是遍历所有的 clients ， 操作 clients 的另一个重要的关联函数为 DaemonMetricCollector::update_sockets()
    // 这里的 clients 本地符合要求的 socket 连接
    for (auto& [daemon_name, sock_client] : clients) {
        // 探测对应的 socket ，观察连接是否 ok
        bool ok;
        sock_client.ping(&ok);
        if (!ok) {
            failures++;
            continue;
        }

        // 向对应的 socket 发起 counter dump 请求，
        // 对应的请求会被 "{\"prefix\": \"" + command + "\"}" 进行包括封装。
        std::string counter_dump_response = asok_request(sock_client, "counter dump", daemon_name);
        if (counter_dump_response.size() == 0) {
            failures++;
            continue;
        }
        // 向对应的 socket 发起 counter schema 请求，
        // 对应的请求会被 "{\"prefix\": \"" + command + "\"}" 进行包括封装。
        std::string counter_schema_response = asok_request(sock_client, "counter schema", daemon_name);
        if (counter_schema_response.size() == 0) {
            failures++;
            continue;
        }

        // 处理对应的返回信息
        json_object counter_dump = boost::json::parse(counter_dump_response).as_object();
        json_object counter_schema = boost::json::parse(counter_schema_response).as_object();

        // 遍历 schema 信息
        for (auto& perf_group_item : counter_schema) {
            std::string perf_group = {perf_group_item.key().begin(), perf_group_item.key().end()};
            json_array perf_group_schema_array = perf_group_item.value().as_array();
            json_array perf_group_dump_array = counter_dump[perf_group].as_array();
            for (auto schema_itr = perf_group_schema_array.begin(), dump_itr = perf_group_dump_array.begin();
                 schema_itr != perf_group_schema_array.end() && dump_itr != perf_group_dump_array.end();
                 ++schema_itr, ++dump_itr) {
                auto counters = schema_itr->at("counters").as_object();
                auto counters_labels = schema_itr->at("labels").as_object();
                auto counters_values = dump_itr->at("counters").as_object();
                labels_t labels;

                for (auto& label : counters_labels) {
                    std::string label_key = {label.key().begin(), label.key().end()};
                    labels[label_key] = quote(label.value().as_string().c_str());
                }
                for (auto& counter : counters) {
                    // 筛选符合优先级配置的监控指标，
                    // 如果对应的监控指标低于限制值，则不会将该监控指标导出
                    json_object counter_group = counter.value().as_object();
                    if (counter_group["priority"].as_int64() < prio_limit) {
                        continue;
                    }
                    // 拼接导出的监控指标名称
                    std::string counter_name_init = {counter.key().begin(), counter.key().end()};
                    std::string counter_name = perf_group + "_" + counter_name_init;
                    promethize(counter_name);

                    auto extra_labels = get_extra_labels(daemon_name);
                    if (extra_labels.empty()) {
                        dout(1) << "Unable to parse instance_id from daemon_name: " << daemon_name << dendl;
                        continue;
                    }
                    labels.insert(extra_labels.begin(), extra_labels.end());

                    // For now this is only required for rgw multi-site metrics
                    // 目前这仅适用于 rgw 多站点指标
                    auto multisite_labels_and_name = add_fixed_name_metrics(counter_name);
                    if (!multisite_labels_and_name.first.empty()) {
                        labels.insert(multisite_labels_and_name.first.begin(), multisite_labels_and_name.first.end());
                        counter_name = multisite_labels_and_name.second;
                    }
                    auto perf_values = counters_values.at(counter_name_init);
                    dump_asok_metric(counter_group, perf_values, counter_name, labels);
                }
            }
        }

        // 从 socket 中获取对应的配置信息
        std::string config_show = asok_request(sock_client, "config show", daemon_name);
        if (config_show.size() == 0) {
            failures++;
            continue;
        }
        // 从配置中解析 pid_file 文件中的信息
        json_object pid_file_json = boost::json::parse(config_show).as_object();
        std::string pid_path = boost_string_to_std(pid_file_json["pid_file"].as_string());
        std::string pid_str = read_file_to_string(pid_path);
        if (!pid_path.size()) {
            dout(1) << "pid path is empty; process metrics won't be fetched for: " << daemon_name << dendl;
        }

        // 记录获取到的 pid 的信息
        if (!pid_str.empty()) {
            daemon_pids.push_back({daemon_name, std::stoi(pid_str)});
        }
    }
    dout(10) << "Perf counters retrieved for " << clients.size() - failures << "/" << clients.size() << " daemons."
             << dendl;
    // get time spent on this function
    timer.stop();
    std::string scrap_desc("Time spent scraping and transforming perf counters to metrics");
    labels_t scrap_labels;
    scrap_labels["host"] = quote(ceph_get_hostname());
    scrap_labels["function"] = quote(__FUNCTION__);

    // 添加执行时间等 metrics 监控数据信息
    add_metric(builder, timer.get_ms(), "ceph_exporter_scrape_time", scrap_desc, "gauge", scrap_labels);

    const std::lock_guard<std::mutex> lock(metrics_mutex);
    // only get metrics if there's pid path for some or all daemons isn't empty
    // 仅当某些或所有守护进程的 PID 路径不为空时获取指标
    // 获取 daemon 的进程信息
    if (daemon_pids.size() != 0) {
        get_process_metrics(daemon_pids);
    }

    // 将上面构建的 metrics 信息赋值给 metrics 变量
    metrics = builder->dump();
}

std::vector<std::string> read_proc_stat_file(std::string path)
{
    std::string stat = read_file_to_string(path);
    std::vector<std::string> strings;
    auto parts = ceph::split(stat);
    strings.assign(parts.begin(), parts.end());
    return strings;
}

struct pstat read_pid_stat(int pid)
{
    std::string stat_path("/proc/" + std::to_string(pid) + "/stat");
    std::vector<std::string> stats = read_proc_stat_file(stat_path);
    struct pstat stat;
    stat.minflt = std::stoul(stats[9]);
    stat.majflt = std::stoul(stats[11]);
    stat.utime = std::stoul(stats[13]);
    stat.stime = std::stoul(stats[14]);
    stat.num_threads = std::stoul(stats[19]);
    stat.start_time = std::stoul(stats[21]);
    stat.vm_size = std::stoul(stats[22]);
    stat.resident_size = std::stoi(stats[23]);
    return stat;
}

void DaemonMetricCollector::get_process_metrics(std::vector<std::pair<std::string, int>> daemon_pids)
{
    std::string path("/proc");
    std::stringstream ss;
    for (auto& [daemon_name, pid] : daemon_pids) {
        std::vector<std::string> uptimes = read_proc_stat_file("/proc/uptime");
        struct pstat stat = read_pid_stat(pid);
        int clk_tck = sysconf(_SC_CLK_TCK);
        double start_time_seconds = stat.start_time / (double)clk_tck;
        double user_time = stat.utime / (double)clk_tck;
        double kernel_time = stat.stime / (double)clk_tck;
        double total_time_seconds = user_time + kernel_time;
        double uptime = std::stod(uptimes[0]);
        double elapsed_time = uptime - start_time_seconds;
        double idle_time = elapsed_time - total_time_seconds;
        double usage = total_time_seconds * 100 / elapsed_time;

        labels_t labels;
        labels["ceph_daemon"] = quote(daemon_name);
        add_metric(builder,
                   stat.minflt,
                   "ceph_exporter_minflt_total",
                   "Number of minor page faults of daemon",
                   "counter",
                   labels);
        add_metric(builder,
                   stat.majflt,
                   "ceph_exporter_majflt_total",
                   "Number of major page faults of daemon",
                   "counter",
                   labels);
        add_metric(builder,
                   stat.num_threads,
                   "ceph_exporter_num_threads",
                   "Number of threads used by daemon",
                   "gauge",
                   labels);
        add_metric(builder, usage, "ceph_exporter_cpu_usage", "CPU usage of a daemon", "gauge", labels);

        std::string cpu_time_desc = "Process time in kernel/user/idle mode";
        labels_t cpu_total_labels;
        cpu_total_labels["ceph_daemon"] = quote(daemon_name);
        cpu_total_labels["mode"] = quote("kernel");
        add_metric(builder, kernel_time, "ceph_exporter_cpu_total", cpu_time_desc, "counter", cpu_total_labels);
        cpu_total_labels["mode"] = quote("user");
        add_metric(builder, user_time, "ceph_exporter_cpu_total", cpu_time_desc, "counter", cpu_total_labels);
        cpu_total_labels["mode"] = quote("idle");
        add_metric(builder, idle_time, "ceph_exporter_cpu_total", cpu_time_desc, "counter", cpu_total_labels);
        add_metric(builder, stat.vm_size, "ceph_exporter_vm_size", "Virtual memory used in a daemon", "gauge", labels);
        add_metric(
            builder, stat.resident_size, "ceph_exporter_resident_size", "Resident memory in a daemon", "gauge", labels);
    }
}

std::string DaemonMetricCollector::asok_request(AdminSocketClient& asok, std::string command, std::string daemon_name)
{
    std::string request("{\"prefix\": \"" + command + "\"}");
    std::string response;
    std::string err = asok.do_request(request, &response);
    if (err.length() > 0 || response.substr(0, 5) == "ERROR") {
        dout(1) << "command " << command << "failed for daemon " << daemon_name << "with error: " << err << dendl;
        return "";
    }
    return response;
}

labels_t DaemonMetricCollector::get_extra_labels(std::string daemon_name)
{
    labels_t labels;
    const std::string ceph_daemon_prefix = "ceph-";
    const std::string ceph_client_prefix = "client.";
    if (daemon_name.rfind(ceph_daemon_prefix, 0) == 0) {
        daemon_name = daemon_name.substr(ceph_daemon_prefix.size());
    }
    if (daemon_name.rfind(ceph_client_prefix, 0) == 0) {
        daemon_name = daemon_name.substr(ceph_client_prefix.size());
    }
    // In vstart cluster socket files for rgw are stored as radosgw.<instance_id>.asok
    if (daemon_name.find("radosgw") != std::string::npos) {
        std::size_t pos = daemon_name.find_last_of('.');
        std::string tmp = daemon_name.substr(pos + 1);
        labels["instance_id"] = quote(tmp);
    }
    else if (daemon_name.find("rgw") != std::string::npos) {
        // fetch intance_id for e.g. "hrgsea" from daemon_name=rgw.foo.ceph-node-00.hrgsea.2.94739968030880
        std::vector<std::string> elems;
        std::stringstream ss;
        ss.str(daemon_name);
        std::string item;
        while (std::getline(ss, item, '.')) {
            elems.push_back(item);
        }
        if (elems.size() >= 4) {
            labels["instance_id"] = quote(elems[3]);
        }
        else {
            return labels_t();
        }
    }
    else {
        labels.insert({"ceph_daemon", quote(daemon_name)});
    }
    return labels;
}

// Add fixed name metrics from existing ones that have details in their names
// that should be in labels (not in name). For backward compatibility,
// a new fixed name metric is created (instead of replacing)and details are put
// in new labels. Intended for RGW sync perf. counters but extendable as required.
// See: https://tracker.ceph.com/issues/45311
// 从现有的包含详细信息的指标名称中添加固定名称的指标
// 这些详细信息应该放在标签中（而不是名称中）。
// 为了向后兼容，创建了一个新的固定名称的指标（而不是替换现有的）
// 并将详细信息放入新的标签中。此功能主要面向 RGW 同步性能计数器，
// 但可以根据需要扩展。
// 参见：https://tracker.ceph.com/issues/45311
std::pair<labels_t, std::string> DaemonMetricCollector::add_fixed_name_metrics(std::string metric_name)
{
    std::string new_metric_name;
    labels_t labels;
    new_metric_name = metric_name;

    std::regex re("^data_sync_from_(.*)\\.");
    std::smatch match;
    if (std::regex_search(metric_name, match, re) == true) {
        new_metric_name = std::regex_replace(metric_name, re, "from_([^.]*)', 'from_zone");
        labels["source_zone"] = quote(match.str(1));
        return {labels, new_metric_name};
    }
    return {};
}

/*
perf_values can be either a int/double or a json_object. Since
   json_value is a wrapper of both we use that class.
 */
/*
perf_values 可以是 int/double 或 json_object 。 由于 json_value 是两者的包装器，我们使用这个类。
*/
void DaemonMetricCollector::dump_asok_metric(json_object perf_info, json_value perf_values, std::string name,
                                             labels_t labels)
{
    int64_t type = perf_info["type"].as_int64();
    std::string metric_type = boost_string_to_std(perf_info["metric_type"].as_string());
    std::string description = boost_string_to_std(perf_info["description"].as_string());

    if (type & PERFCOUNTER_LONGRUNAVG) {
        int64_t count = perf_values.as_object()["avgcount"].as_int64();
        add_metric(builder, count, name + "_count", description + " Count", "counter", labels);
        json_value sum_value = perf_values.as_object()["sum"];
        add_double_or_int_metric(builder, sum_value, name + "_sum", description + " Total", metric_type, labels);
    }
    else {
        add_double_or_int_metric(builder, perf_values, name, description, metric_type, labels);
    }
}

void DaemonMetricCollector::update_sockets()
{
    // 从 src/common/options 中的配置中可以看出 exporter_sock_dir 的默认值为 /var/run/ceph/
    std::string sock_dir = g_conf().get_val<std::string>("exporter_sock_dir");
    clients.clear();
    std::filesystem::path sock_path = sock_dir;
    if (!std::filesystem::is_directory(sock_path.parent_path())) {
        dout(1) << "ERROR: No such directory exist" << sock_dir << dendl;
        return;
    }

    // 遍历 /var/run/ceph/ 目录中的信息
    for (const auto& entry : std::filesystem::directory_iterator(sock_dir)) {
        // 如果对应文件的扩展名为 .asok ，则继续详细的处理
        if (entry.path().extension() == ".asok") {
            // 获取对应 socket 的末尾文件名
            std::string daemon_socket_name = entry.path().filename().string();
            std::string daemon_name = daemon_socket_name.substr(0, daemon_socket_name.size() - 5);
            // 如果获取的 daemon_name 在 clients 中不存在，
            // 并且， daemon_name 中没有 mgr 字符串，
            // 并且， daemon_name 中没有 ceph-exporter 字符串
            //
            // 则， 将对应的 daemon_name 信息添加到 clients 列表中。
            if (clients.find(daemon_name) == clients.end() && !(daemon_name.find("mgr") != std::string::npos) &&
                !(daemon_name.find("ceph-exporter") != std::string::npos)) {
                AdminSocketClient sock(entry.path().string());
                clients.insert({daemon_name, std::move(sock)});
            }
        }
    }
}

void OrderedMetricsBuilder::add(std::string value, std::string name, std::string description, std::string mtype,
                                labels_t labels)
{
    if (metrics.find(name) == metrics.end()) {
        Metric metric(name, mtype, description);
        metrics[name] = std::move(metric);
    }
    Metric& metric = metrics[name];
    metric.add(labels, value);
}

std::string OrderedMetricsBuilder::dump()
{
    for (auto& [name, metric] : metrics) {
        out += metric.dump() + "\n";
    }
    return out;
}

void UnorderedMetricsBuilder::add(std::string value, std::string name, std::string description, std::string mtype,
                                  labels_t labels)
{
    Metric metric(name, mtype, description);
    metric.add(labels, value);
    out += metric.dump() + "\n\n";
}

std::string UnorderedMetricsBuilder::dump()
{
    return out;
}

void Metric::add(labels_t labels, std::string value)
{
    metric_entry entry;
    entry.labels = labels;
    entry.value = value;
    entries.push_back(entry);
}

std::string Metric::dump()
{
    std::stringstream metric_ss;
    metric_ss << "# HELP " << name << " " << description << "\n";
    metric_ss << "# TYPE " << name << " " << mtype << "\n";
    for (auto& entry : entries) {
        std::stringstream labels_ss;
        size_t i = 0;
        for (auto& [label_name, label_value] : entry.labels) {
            labels_ss << label_name << "=" << label_value;
            if (i < entry.labels.size() - 1) {
                labels_ss << ",";
            }
            i++;
        }
        metric_ss << name << "{" << labels_ss.str() << "} " << entry.value;
        if (&entry != &entries.back()) {
            metric_ss << "\n";
        }
    }
    return metric_ss.str();
}

DaemonMetricCollector& collector_instance()
{
    static DaemonMetricCollector instance;
    return instance;
}
