// -*- mode:C++; tab-width:8; c-basic-offset:2; indent-tabs-mode:nil -*-
// vim: ts=8 sw=2 smarttab

#include "node_extent_mutable.h"

#include "node_extent_manager.h"

namespace crimson::os::seastore::onode {

NodeExtentMutable::NodeExtentMutable(NodeExtent& extent)
    : extent{extent}
{
    assert(extent.is_pending() ||   // during mutation
           extent.is_clean());      // during replay
}

const char* NodeExtentMutable::get_read() const
{
    assert(extent.is_pending() ||   // during mutation
           extent.is_clean());      // during replay
    return extent.get_bptr().c_str();
}

char* NodeExtentMutable::get_write()
{
    assert(extent.is_pending() ||   // during mutation
           extent.is_clean());      // during replay
    return extent.get_bptr().c_str();
}

extent_len_t NodeExtentMutable::get_length() const
{
    return extent.get_length();
}

laddr_t NodeExtentMutable::get_laddr() const
{
    return extent.get_laddr();
}

const char* NodeExtentMutable::buf_upper_bound() const
{
    return get_read() + get_length();
}

}   // namespace crimson::os::seastore::onode
