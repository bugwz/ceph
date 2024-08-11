#include "http_server.h"

#include "common/debug.h"
#include "common/hostname.h"
#include "exporter/DaemonMetricCollector.h"
#include "global/global_context.h"
#include "global/global_init.h"

#include <boost/asio.hpp>
#include <boost/beast/core.hpp>
#include <boost/beast/http.hpp>
#include <boost/beast/version.hpp>
#include <boost/thread/thread.hpp>
#include <chrono>
#include <cstdlib>
#include <ctime>
#include <iostream>
#include <map>
#include <memory>
#include <string>

#define dout_context g_ceph_context
#define dout_subsys  ceph_subsys_ceph_exporter

namespace beast = boost::beast;     // from <boost/beast.hpp>
namespace http = beast::http;       // from <boost/beast/http.hpp>
namespace net = boost::asio;        // from <boost/asio.hpp>
using tcp = boost::asio::ip::tcp;   // from <boost/asio/ip/tcp.hpp>

class http_connection : public std::enable_shared_from_this<http_connection>
{
public:
    http_connection(tcp::socket socket)
        : socket_(std::move(socket))
    {}

    // Initiate the asynchronous operations associated with the connection.
    // 启动与连接相关的异步操作
    void start()
    {
        // 读取对应的 http 请求
        read_request();
        check_deadline();
    }

private:
    tcp::socket socket_;
    // 每次的 buffer 大小为 8192
    beast::flat_buffer buffer_{8192};
    http::request<http::dynamic_body> request_;
    http::response<http::string_body> response_;

    net::steady_timer deadline_{socket_.get_executor(), std::chrono::seconds(60)};

    // Asynchronously receive a complete request message.
    void read_request()
    {
        auto self = shared_from_this();

        http::async_read(socket_, buffer_, request_, [self](beast::error_code ec, std::size_t bytes_transferred) {
            boost::ignore_unused(bytes_transferred);
            if (ec) {
                dout(1) << "ERROR: " << ec.message() << dendl;
                return;
            }
            else {
                // 处理 http 请求
                self->process_request();
            }
        });
    }

    // Determine what needs to be done with the request message.
    // 确定需要对请求消息进行什么操作
    void process_request()
    {
        response_.version(request_.version());
        response_.keep_alive(request_.keep_alive());

        // 只支持 get 操作
        switch (request_.method()) {
        case http::verb::get:
            // 设置响应码
            response_.result(http::status::ok);
            // 创建返回的数据
            create_response();
            break;

        default:
            // We return responses indicating an error if
            // we do not recognize the request method.
            // 如果我们无法识别请求方法，我们将返回指示错误的响应。
            response_.result(http::status::method_not_allowed);
            response_.set(http::field::content_type, "text/plain");
            std::string body("Invalid request-method '" + std::string(request_.method_string()) + "'");
            response_.body() = body;
            break;
        }

        // 异步写回相应数据
        write_response();
    }

    // Construct a response message based on the program state.
    // 根据程序状态构建响应消息。
    void create_response()
    {
        // 如果请求的地址为 / ，则返回一个 html 格式的内容数据
        if (request_.target() == "/") {
            response_.set(http::field::content_type, "text/html; charset=utf-8");
            std::string body("<html>\n"
                             "<head><title>Ceph Exporter</title></head>\n"
                             "<body>\n"
                             "<h1>Ceph Exporter</h1>\n"
                             "<p><a href='/metrics'>Metrics</a></p>"
                             "</body>\n"
                             "</html>\n");
            response_.body() = body;
        }
        // 如果请求的地址为 /metrics ， 即直接请求的监控数据
        // 这个服务的默认 http 端口为 9926
        else if (request_.target() == "/metrics") {
            response_.set(http::field::content_type, "text/plain; charset=utf-8");
            // 获取对应的 metrics 实例， 然后采集数据，返回采集后的监控数据
            DaemonMetricCollector& collector = collector_instance();
            // 这里的 metrics 数据是之前已经设置好的，应该是会定期更新，所以这个读取操作由于是读取的历史数据，
            // 所以这里的操作十分迅速。
            std::string metrics = collector.get_metrics();
            response_.body() = metrics;
        }
        else {
            // 不支持其它的请求地址
            response_.result(http::status::method_not_allowed);
            response_.set(http::field::content_type, "text/plain");
            response_.body() = "File not found \n";
        }
    }

    // Asynchronously transmit the response message.
    void write_response()
    {
        auto self = shared_from_this();

        response_.prepare_payload();

        http::async_write(socket_, response_, [self](beast::error_code ec, std::size_t) {
            self->socket_.shutdown(tcp::socket::shutdown_send, ec);
            self->deadline_.cancel();
            if (ec) {
                dout(1) << "ERROR: " << ec.message() << dendl;
                return;
            }
        });
    }

    // Check whether we have spent enough time on this connection.
    void check_deadline()
    {
        auto self = shared_from_this();

        deadline_.async_wait([self](beast::error_code ec) {
            if (!ec) {
                // Close socket to cancel any outstanding operation.
                self->socket_.close(ec);
            }
        });
    }
};

// "Loop" forever accepting new connections.
void http_server(tcp::acceptor& acceptor, tcp::socket& socket)
{
    acceptor.async_accept(socket, [&](beast::error_code ec) {
        // 处理 socket 请求
        if (!ec) std::make_shared<http_connection>(std::move(socket))->start();
        http_server(acceptor, socket);
    });
}

// http server 入口
void http_server_thread_entrypoint()
{
    try {
        // 获取 exporter 地址和端口信息
        // 依据 src/common/options 的默认配置信息， exporter_addr 的默认值为 0.0.0.0
        std::string exporter_addr = g_conf().get_val<std::string>("exporter_addr");
        auto const address = net::ip::make_address(exporter_addr);
        // 依据 src/common/options 的默认配置信息， exporter_http_port 默认值为 9926
        unsigned short port = g_conf().get_val<int64_t>("exporter_http_port");

        net::io_context ioc{1};

        tcp::acceptor acceptor{ioc, {address, port}};
        tcp::socket socket{ioc};
        // 启动 http 服务
        http_server(acceptor, socket);
        dout(1) << "Http server running on " << exporter_addr << ":" << port << dendl;
        ioc.run();
    }
    catch (std::exception const& e) {
        dout(1) << "Error: " << e.what() << dendl;
        exit(EXIT_FAILURE);
    }
}
