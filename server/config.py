"""
Mission Control — backend server for Hermes agent dashboard.
Constants, configuration, and shared globals.

Python stdlib only. No pip, no npm.
"""

import hashlib
import http.server
import json
import os
import queue as queue_module
import ssl
import sqlite3
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from http import HTTPStatus

# =============================================================================
# Constants
# =============================================================================

# Resolve the real Hermes data directory even when running under a profile
# (kanban workers have HOME set to the profile's nested home).
def _resolve_hermes_home():
    """Find the actual ~/.hermes data directory, not a profile subdirectory."""
    env_home = os.environ.get("HERMES_HOME", "")
    if env_home and "/profiles/" in env_home:
        # Running under a profile — walk up to the real .hermes
        return os.path.dirname(os.path.dirname(env_home))
    candidate = os.path.expanduser("~/.hermes")
    if os.path.isdir(candidate):
        return candidate
    # Fallback
    return "/home/hermes/.hermes"

HERMES_HOME = _resolve_hermes_home()
PORT = 51763
HOST = "0.0.0.0"
SSE_INTERVAL = 5       # seconds between SSE pushes
PROD_CACHE_TTL = 30    # seconds — cache prod SSH health to avoid hammering SSH

# Project root (config.py lives one level deep in server/)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVERS_CONFIG = os.path.join(_ROOT, "servers.json")
DASHBOARD_DB = os.path.join(_ROOT, "dashboard.db")
CERT_DIR = os.path.join(_ROOT, "certs")
CERT_FILE = os.path.join(CERT_DIR, "mc-cert.pem")
KEY_FILE = os.path.join(CERT_DIR, "mc-key.pem")
CA_CERT_FILE = os.path.join(CERT_DIR, "ca-cert.pem")
RETENTION_DAYS = 30

# ── SSE Multiplexer ──────────────────────────────────────────────────────
_SSE_QUEUE = queue_module.Queue(maxsize=64)
_CHANNEL_FINGERPRINTS = {}   # {event_type: md5_hex}, guarded by _fp_lock
_fp_lock = threading.Lock()

# Channel registry: (event_type, interval_seconds, tier)
# Tier 1 = burst on connect, Tier 2-3 = arrive on cadence
_CHANNEL_REGISTRY = [
    # Tier 1 — Fast, frequent
    ("gateway",          5,   1),
    ("processes",        5,   1),
    ("hermes-health",    5,   1),
    ("sessions-ledger", 15,   1),
    # Tier 2 — Medium, moderate
    ("profiles",        60,   2),
    ("sessions",        30,   2),
    ("kanban",          30,   2),
    ("daily-costs",    120,   2),
    # Tier 3 — Slow, cached
    ("prod-health",     30,   3),
    ("dokku",           60,   3),
    ("server-crons",   300,   3),
    # OpenRouter usage — live credit/cost data from OpenRouter API
    ("openrouter-usage", 60,   2),
    # OpenRouter activity — per-day per-model usage/token/cost data (cached locally)
    ("openrouter-activity", 300, 2),
    # OpenRouter keys — account-level key listing with usage totals
    ("openrouter-keys", 600, 3),
    ("servers",         60,   3),
    # Work servers — conservative intervals to avoid strain
    ("work-system",    900,   3),   # 15 min — CPU/MEM/DISK
    ("work-docker",   1800,   3),   # 30 min — container stats
    ("work-nexus",    1800,   3),   # 30 min — repo/blobs
    ("work-jenkins",  1800,   3),   # 30 min — job/queue status
    ("work-postgres", 1800,   3),   # 30 min — PG/Patroni/Etcd
]

# Burst signals — set on new SSE client connect, cleared after one push
_CHANNEL_BURST = {event_type: threading.Event() for event_type, _, _ in _CHANNEL_REGISTRY}
