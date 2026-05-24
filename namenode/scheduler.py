import logging
import os
import threading
import time

import requests

import metadata as db

logger = logging.getLogger(__name__)

HEARTBEAT_TIMEOUT = float(os.getenv("HEARTBEAT_TIMEOUT", "15"))
CHECK_INTERVAL = 5.0

_rr_lock = threading.Lock()
_rr_index = 0


def next_two_nodes(active_nodes: list[dict]) -> tuple[dict, dict]:
    """Round-Robin: returns (primary, replica) advancing the cursor by 1 each call."""
    global _rr_index
    n = len(active_nodes)
    with _rr_lock:
        primary = active_nodes[_rr_index % n]
        replica = active_nodes[(_rr_index + 1) % n]
        _rr_index += 1
    return primary, replica


def _rereplicate_block(block_id: str, dead_node_id: str) -> None:
    survivor = db.get_surviving_replica(block_id, dead_node_id)
    if not survivor:
        logger.warning("block %s has no surviving replica — data loss", block_id)
        return

    active = db.get_active_datanodes(HEARTBEAT_TIMEOUT)
    candidates = [n for n in active if n["node_id"] not in (dead_node_id, survivor["node_id"])]
    if not candidates:
        logger.warning("no candidate DataNode available to re-replicate block %s", block_id)
        return

    target = candidates[0]
    try:
        url = f"http://{survivor['host']}:{survivor['port']}/blocks/{block_id}/replicate"
        resp = requests.post(
            url,
            json={"target_host": target["host"], "target_port": target["port"]},
            timeout=10,
        )
        resp.raise_for_status()
        db.replace_block_replica(block_id, dead_node_id, target["node_id"])
        logger.info(
            "re-replicated block %s: %s → %s",
            block_id, survivor["node_id"], target["node_id"],
        )
    except Exception as exc:
        logger.error("failed to re-replicate block %s: %s", block_id, exc)


def _check_nodes() -> None:
    dead_nodes = [n for n in db.get_all_datanodes(HEARTBEAT_TIMEOUT) if n["status"] == "down"]
    for node in dead_nodes:
        node_id = node["node_id"]
        blocks = db.get_blocks_on_node(node_id)
        if not blocks:
            continue
        logger.info("DataNode %s is down — re-replicating %d block(s)", node_id, len(blocks))
        for block_id in blocks:
            _rereplicate_block(block_id, node_id)


def _monitor_loop() -> None:
    while True:
        try:
            _check_nodes()
        except Exception as exc:
            logger.error("heartbeat monitor error: %s", exc)
        time.sleep(CHECK_INTERVAL)


def start_heartbeat_monitor() -> None:
    t = threading.Thread(target=_monitor_loop, daemon=True, name="heartbeat-monitor")
    t.start()
