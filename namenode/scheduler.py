import threading

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
