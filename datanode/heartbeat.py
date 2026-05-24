import logging
import os
import shutil
import threading
import time

import requests

logger = logging.getLogger(__name__)

NODE_ID           = os.getenv("NODE_ID", "dn0")
HOST              = os.getenv("HOST", "localhost")
PORT              = int(os.getenv("PORT", "8001"))
NAMENODE_URL      = os.getenv("NAMENODE_URL", "http://namenode:8000")
HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL", "5"))
BLOCKS_DIR        = os.getenv("BLOCKS_DIR", "/app/blocks")


def _free_bytes() -> int:
    try:
        return shutil.disk_usage(BLOCKS_DIR).free
    except Exception:
        return 0


def _register() -> None:
    url = f"{NAMENODE_URL}/datanodes/register"
    payload = {"node_id": NODE_ID, "host": HOST, "port": PORT, "free_bytes": _free_bytes()}
    while True:
        try:
            resp = requests.post(url, json=payload, timeout=5)
            resp.raise_for_status()
            logger.info("registered with NameNode as %s", NODE_ID)
            return
        except Exception as exc:
            logger.warning("registration failed, retrying in 2s: %s", exc)
            time.sleep(2)


def _heartbeat_loop() -> None:
    _register()
    url = f"{NAMENODE_URL}/datanodes/heartbeat"
    while True:
        time.sleep(HEARTBEAT_INTERVAL)
        try:
            resp = requests.post(url, json={"node_id": NODE_ID, "free_bytes": _free_bytes()}, timeout=5)
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("heartbeat failed: %s", exc)


def start() -> None:
    t = threading.Thread(target=_heartbeat_loop, daemon=True, name="heartbeat")
    t.start()
