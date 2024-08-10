// -*- mode:C++; tab-width:8; c-basic-offset:2; indent-tabs-mode:t -*-
// vim: ts=8 sw=2 smarttab

#pragma once

#include "common/perf_counters.h"
#include "include/common_fwd.h"

enum
{
    l_osd_first = 10000,
    // ceph_osd_op_wip
    l_osd_op_wip,
    // ceph_osd_op
    l_osd_op,
    l_osd_op_inb,
    l_osd_op_outb,
    // ceph_osd_op_latency_sum
    // ceph_osd_op_latency_count
    l_osd_op_lat,
    // ceph_osd_op_process_latency_sum
    // ceph_osd_op_process_latency_count
    l_osd_op_process_lat,
    // ceph_osd_op_prepare_latency_sum
    // ceph_osd_op_prepare_latency_count
    l_osd_op_prepare_lat,
    // ceph_osd_op_r
    l_osd_op_r,
    // ceph_osd_op_r_out_bytes
    l_osd_op_r_outb,
    // ceph_osd_op_r_latency_sum
    // ceph_osd_op_r_latency_count
    l_osd_op_r_lat,
    l_osd_op_r_lat_outb_hist,
    // ceph_osd_op_r_process_latency_sum
    // ceph_osd_op_r_process_latency_count
    l_osd_op_r_process_lat,
    // ceph_osd_op_r_prepare_latency_sum
    // ceph_osd_op_r_prepare_latency_count
    l_osd_op_r_prepare_lat,
    // ceph_osd_op_w
    l_osd_op_w,
    l_osd_op_w_inb,
    // ceph_osd_op_w_latency_sum
    // ceph_osd_op_w_latency_count
    l_osd_op_w_lat,
    l_osd_op_w_lat_inb_hist,
    // ceph_osd_op_w_process_latency_sum
    // ceph_osd_op_w_process_latency_count
    l_osd_op_w_process_lat,
    // ceph_osd_op_w_prepare_latency_sum
    // ceph_osd_op_w_prepare_latency_count
    l_osd_op_w_prepare_lat,
    // ceph_osd_op_rw
    l_osd_op_rw,
    // ceph_osd_op_rw_in_bytes
    l_osd_op_rw_inb,
    // ceph_osd_op_rw_out_bytes
    l_osd_op_rw_outb,
    // ceph_osd_op_rw_latency_sum
    // ceph_osd_op_rw_latency_count
    l_osd_op_rw_lat,
    l_osd_op_rw_lat_inb_hist,
    l_osd_op_rw_lat_outb_hist,
    // ceph_osd_op_rw_process_latency_sum
    // ceph_osd_op_rw_process_latency_count
    l_osd_op_rw_process_lat,
    // ceph_osd_op_rw_prepare_latency_sum
    // ceph_osd_op_rw_prepare_latency_count
    l_osd_op_rw_prepare_lat,

    l_osd_op_delayed_unreadable,
    l_osd_op_delayed_degraded,

    // ceph_osd_op_before_queue_op_lat_sum
    // ceph_osd_op_before_queue_op_lat_count
    l_osd_op_before_queue_op_lat,
    // ceph_osd_op_before_dequeue_op_lat_sum
    // ceph_osd_op_before_dequeue_op_lat_count
    l_osd_op_before_dequeue_op_lat,

    // ceph_osd_subop
    l_osd_sop,
    // ceph_osd_subop_in_bytes
    l_osd_sop_inb,
    // ceph_osd_subop_latency_sum
    // ceph_osd_subop_latency_count
    l_osd_sop_lat,
    // ceph_osd_subop_w
    l_osd_sop_w,
    // ceph_osd_subop_w_in_bytes
    l_osd_sop_w_inb,
    // ceph_osd_subop_w_latency_sum
    // ceph_osd_subop_w_latency_count
    l_osd_sop_w_lat,
    // ceph_osd_subop_pull
    l_osd_sop_pull,
    // ceph_osd_subop_pull_latency_sum
    // ceph_osd_subop_pull_latency_count
    l_osd_sop_pull_lat,
    // ceph_osd_subop_push
    l_osd_sop_push,
    // ceph_osd_subop_push_in_bytes
    l_osd_sop_push_inb,
    // ceph_osd_subop_push_latency_sum
    // ceph_osd_subop_push_latency_count
    l_osd_sop_push_lat,

    // ceph_osd_pull
    l_osd_pull,
    // ceph_osd_push
    l_osd_push,
    // ceph_osd_push_out_bytes
    l_osd_push_outb,

    l_osd_rop,
    l_osd_rbytes,

    l_osd_recovery_push_queue_lat,
    l_osd_recovery_push_reply_queue_lat,
    l_osd_recovery_pull_queue_lat,
    l_osd_recovery_backfill_queue_lat,
    l_osd_recovery_backfill_remove_queue_lat,
    l_osd_recovery_scan_queue_lat,

    l_osd_recovery_queue_lat,
    l_osd_recovery_context_queue_lat,

    // ceph_osd_loadavg
    l_osd_loadavg,
    // ceph_osd_cached_crc
    l_osd_cached_crc,
    // ceph_osd_cached_crc_adjusted
    l_osd_cached_crc_adjusted,
    l_osd_missed_crc,

    // ceph_osd_numpg
    l_osd_pg,
    // ceph_osd_numpg_primary
    l_osd_pg_primary,
    // ceph_osd_numpg_replica
    l_osd_pg_replica,
    // ceph_osd_numpg_stray
    l_osd_pg_stray,
    // ceph_osd_numpg_removing
    l_osd_pg_removing,
    l_osd_hb_to,
    // ceph_osd_map_messages
    l_osd_map,
    // ceph_osd_map_message_epochs
    l_osd_mape,
    // ceph_osd_map_message_epoch_dups
    l_osd_mape_dup,

    // ceph_osd_messages_delayed_for_map
    l_osd_waiting_for_map,

    // ceph_osd_osd_map_cache_hit
    l_osd_map_cache_hit,
    // ceph_osd_osd_map_cache_miss
    l_osd_map_cache_miss,
    // ceph_osd_osd_map_cache_miss_low
    l_osd_map_cache_miss_low,
    // ceph_osd_osd_map_cache_miss_low_avg_sum
    // ceph_osd_osd_map_cache_miss_low_avg_count
    l_osd_map_cache_miss_low_avg,
    // ceph_osd_osd_map_bl_cache_hit
    l_osd_map_bl_cache_hit,
    // ceph_osd_osd_map_bl_cache_miss
    l_osd_map_bl_cache_miss,

    // ceph_osd_stat_bytes
    l_osd_stat_bytes,
    // ceph_osd_stat_bytes_used
    l_osd_stat_bytes_used,
    // ceph_osd_stat_bytes_avail
    l_osd_stat_bytes_avail,

    // ceph_osd_copyfrom
    l_osd_copyfrom,

    // ceph_osd_tier_promote
    l_osd_tier_promote,
    // ceph_osd_tier_flush
    l_osd_tier_flush,
    // ceph_osd_tier_flush_fail
    l_osd_tier_flush_fail,
    // ceph_osd_tier_try_flush
    l_osd_tier_try_flush,
    // ceph_osd_tier_try_flush_fail
    l_osd_tier_try_flush_fail,
    // ceph_osd_tier_evict
    l_osd_tier_evict,
    // ceph_osd_tier_whiteout
    l_osd_tier_whiteout,
    // ceph_osd_tier_dirty
    l_osd_tier_dirty,
    // ceph_osd_tier_clean
    l_osd_tier_clean,
    // ceph_osd_tier_delay
    l_osd_tier_delay,
    // ceph_osd_tier_proxy_read
    l_osd_tier_proxy_read,
    // ceph_osd_tier_proxy_write
    l_osd_tier_proxy_write,

    // ceph_osd_agent_wake
    l_osd_agent_wake,
    // ceph_osd_agent_skip
    l_osd_agent_skip,
    // ceph_osd_agent_flush
    l_osd_agent_flush,
    // ceph_osd_agent_evict
    l_osd_agent_evict,

    // ceph_osd_object_ctx_cache_hit
    l_osd_object_ctx_cache_hit,
    // ceph_osd_object_ctx_cache_total
    l_osd_object_ctx_cache_total,

    // ceph_osd_op_cache_hit
    l_osd_op_cache_hit,
    // ceph_osd_osd_tier_flush_lat_sum
    // ceph_osd_osd_tier_flush_lat_count
    l_osd_tier_flush_lat,
    // ceph_osd_osd_tier_promote_lat_sum
    // ceph_osd_osd_tier_promote_lat_count
    l_osd_tier_promote_lat,
    // ceph_osd_osd_tier_r_lat_sum
    // ceph_osd_osd_tier_r_lat_count
    l_osd_tier_r_lat,

    // ceph_osd_osd_pg_info
    l_osd_pg_info,
    // ceph_osd_osd_pg_fastinfo
    l_osd_pg_fastinfo,
    // ceph_osd_osd_pg_biginfo
    l_osd_pg_biginfo,

    l_osd_last,
};

PerfCounters* build_osd_logger(CephContext* cct);

// PeeringState perf counters
enum
{
    rs_first = 20000,
    // ceph_recoverystate_perf_initial_latency_sum
    // ceph_recoverystate_perf_initial_latency_count
    rs_initial_latency,
    // ceph_recoverystate_perf_started_latency_sum
    // ceph_recoverystate_perf_started_latency_count
    rs_started_latency,
    // ceph_recoverystate_perf_reset_latency_sum
    // ceph_recoverystate_perf_reset_latency_count
    rs_reset_latency,
    // ceph_recoverystate_perf_start_latency_sum
    // ceph_recoverystate_perf_start_latency_count
    rs_start_latency,
    // ceph_recoverystate_perf_primary_latency_sum
    // ceph_recoverystate_perf_primary_latency_count
    rs_primary_latency,
    // ceph_recoverystate_perf_peering_latency_sum
    // ceph_recoverystate_perf_peering_latency_count
    rs_peering_latency,
    // ceph_recoverystate_perf_backfilling_latency_sum
    // ceph_recoverystate_perf_backfilling_latency_count
    rs_backfilling_latency,
    // ceph_recoverystate_perf_waitremotebackfillreserved_latency_sum
    // ceph_recoverystate_perf_waitremotebackfillreserved_latency_count
    rs_waitremotebackfillreserved_latency,
    // ceph_recoverystate_perf_waitlocalbackfillreserved_latency_sum
    // ceph_recoverystate_perf_waitlocalbackfillreserved_latency_count
    rs_waitlocalbackfillreserved_latency,
    // ceph_recoverystate_perf_notbackfilling_latency_sum
    // ceph_recoverystate_perf_notbackfilling_latency_count
    rs_notbackfilling_latency,
    // ceph_recoverystate_perf_repnotrecovering_latency_sum
    // ceph_recoverystate_perf_repnotrecovering_latency_count
    rs_repnotrecovering_latency,
    // ceph_recoverystate_perf_repwaitrecoveryreserved_latency_sum
    // ceph_recoverystate_perf_repwaitrecoveryreserved_latency_count
    rs_repwaitrecoveryreserved_latency,
    // ceph_recoverystate_perf_repwaitbackfillreserved_latency_sum
    // ceph_recoverystate_perf_repwaitbackfillreserved_latency_count
    rs_repwaitbackfillreserved_latency,
    // ceph_recoverystate_perf_reprecovering_latency_sum
    // ceph_recoverystate_perf_reprecovering_latency_count
    rs_reprecovering_latency,
    // ceph_recoverystate_perf_activating_latency_sum
    // ceph_recoverystate_perf_activating_latency_count
    rs_activating_latency,
    // ceph_recoverystate_perf_waitlocalrecoveryreserved_latency_sum
    // ceph_recoverystate_perf_waitlocalrecoveryreserved_latency_count
    rs_waitlocalrecoveryreserved_latency,
    // ceph_recoverystate_perf_waitremoterecoveryreserved_latency_sum
    // ceph_recoverystate_perf_waitremoterecoveryreserved_latency_count
    rs_waitremoterecoveryreserved_latency,
    // ceph_recoverystate_perf_recovering_latency_sum
    // ceph_recoverystate_perf_recovering_latency_count
    rs_recovering_latency,
    // ceph_recoverystate_perf_recovered_latency_sum
    // ceph_recoverystate_perf_recovered_latency_count
    rs_recovered_latency,
    // ceph_recoverystate_perf_clean_latency_sum
    // ceph_recoverystate_perf_clean_latency_count
    rs_clean_latency,
    // ceph_recoverystate_perf_active_latency_sum
    // ceph_recoverystate_perf_active_latency_count
    rs_active_latency,
    // ceph_recoverystate_perf_replicaactive_latency_sum
    // ceph_recoverystate_perf_replicaactive_latency_count
    rs_replicaactive_latency,
    // ceph_recoverystate_perf_stray_latency_sum
    // ceph_recoverystate_perf_stray_latency_count
    rs_stray_latency,
    // ceph_recoverystate_perf_getinfo_latency_sum
    // ceph_recoverystate_perf_getinfo_latency_count
    rs_getinfo_latency,
    // ceph_recoverystate_perf_getlog_latency_sum
    // ceph_recoverystate_perf_getlog_latency_count
    rs_getlog_latency,
    // ceph_recoverystate_perf_waitactingchange_latency_sum
    // ceph_recoverystate_perf_waitactingchange_latency_count
    rs_waitactingchange_latency,
    // ceph_recoverystate_perf_incomplete_latency_sum
    // ceph_recoverystate_perf_incomplete_latency_count
    rs_incomplete_latency,
    // ceph_recoverystate_perf_down_latency_sum
    // ceph_recoverystate_perf_down_latency_count
    rs_down_latency,
    // ceph_recoverystate_perf_getmissing_latency_sum
    // ceph_recoverystate_perf_getmissing_latency_count
    rs_getmissing_latency,
    // ceph_recoverystate_perf_waitupthru_latency_sum
    // ceph_recoverystate_perf_waitupthru_latency_count
    rs_waitupthru_latency,
    // ceph_recoverystate_perf_notrecovering_latency_sum
    // ceph_recoverystate_perf_notrecovering_latency_count
    rs_notrecovering_latency,
    rs_last,
};

PerfCounters* build_recoverystate_perf(CephContext* cct);
