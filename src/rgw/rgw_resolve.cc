// -*- mode:C++; tab-width:8; c-basic-offset:2; indent-tabs-mode:t -*-
// vim: ts=8 sw=2 smarttab ft=cpp

#include "acconfig.h"

#include <arpa/nameser.h>
#include <netinet/in.h>
#include <resolv.h>
#include <sys/types.h>

#ifdef HAVE_ARPA_NAMESER_COMPAT_H
#include <arpa/nameser_compat.h>
#endif

#include "common/dns_resolve.h"
#include "rgw_common.h"
#include "rgw_resolve.h"

#define dout_subsys ceph_subsys_rgw

using namespace std;

RGWResolver::~RGWResolver() {}

RGWResolver::RGWResolver()
{
    resolver = DNSResolver::get_instance();
}

int RGWResolver::resolve_cname(const string& hostname, string& cname, bool* found)
{
    return resolver->resolve_cname(g_ceph_context, hostname, &cname, found);
}

RGWResolver* rgw_resolver;


void rgw_init_resolver()
{
    rgw_resolver = new RGWResolver();
}

void rgw_shutdown_resolver()
{
    delete rgw_resolver;
}
