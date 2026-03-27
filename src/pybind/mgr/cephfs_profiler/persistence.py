"""
PersistenceManager: handles daily portrait summaries in MGR KV store.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .types import ClientPortrait

logger = logging.getLogger(__name__)

PREFIX = "cephfs_profiler/daily"
META_LAST_PERSIST = "cephfs_profiler/meta/last_persist_time"


class PersistenceManager:
    """Manages daily portrait persistence in MGR KV store."""

    @staticmethod
    def save_daily_portrait(module, portrait: ClientPortrait, date_str: str) -> None:
        """Save a daily portrait summary to KV store."""
        key = f"{PREFIX}/{portrait.fs_name}/{portrait.client_id}/{date_str}"
        try:
            module.set_store(key, json.dumps(portrait.to_dict()))
            logger.debug("Saved daily portrait: %s", key)
        except Exception as e:
            logger.error("Failed to save portrait %s: %s", key, e)

    @staticmethod
    def save_persist_time(module, timestamp: str) -> None:
        """Record the last persistence time."""
        module.set_store(META_LAST_PERSIST, timestamp)

    @staticmethod
    def get_last_persist_time(module) -> Optional[str]:
        """Get the last persistence timestamp."""
        return module.get_store(META_LAST_PERSIST)

    @staticmethod
    def load_history(module, fs_name: str, client_id: str,
                     days: int = 30) -> List[Dict]:
        """Load stored daily portraits for a client."""
        prefix = f"{PREFIX}/{fs_name}/{client_id}/"
        stored = module.get_store_prefix(prefix)
        if not stored:
            return []

        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        results = []
        for key, val in stored.items():
            date_part = key.rsplit("/", 1)[-1]
            if date_part >= cutoff:
                try:
                    results.append(json.loads(val))
                except json.JSONDecodeError:
                    logger.warning("Corrupted stored portrait: %s", key)

        results.sort(key=lambda x: x.get("last_seen", ""))
        return results

    @staticmethod
    def prune_old(module, retention_days: int) -> int:
        """Delete stored portraits older than retention_days. Returns count deleted."""
        all_stored = module.get_store_prefix(f"{PREFIX}/")
        if not all_stored:
            return 0

        cutoff = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d")
        deleted = 0
        for key in list(all_stored.keys()):
            date_part = key.rsplit("/", 1)[-1]
            if date_part < cutoff:
                module.set_store(key, None)  # delete
                deleted += 1

        if deleted:
            logger.info("Pruned %d expired portrait records", deleted)
        return deleted

    @staticmethod
    def reset_history(module, fs_name: Optional[str] = None,
                      client_id: Optional[str] = None) -> int:
        """Clear stored portrait history. Returns count deleted."""
        if fs_name and client_id:
            prefix = f"{PREFIX}/{fs_name}/{client_id}/"
        elif fs_name:
            prefix = f"{PREFIX}/{fs_name}/"
        else:
            prefix = f"{PREFIX}/"

        stored = module.get_store_prefix(prefix)
        if not stored:
            return 0

        for key in stored:
            module.set_store(key, None)
        return len(stored)
