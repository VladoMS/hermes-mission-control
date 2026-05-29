#!/usr/bin/env python3
"""Extract all modules from original server.py by function boundaries."""
import os, sys, re

os.chdir('/home/hermes/mission-control')

with open('/tmp/orig_server.py') as f:
    lines = f.readlines()
N = len(lines)

# Module definitions: (name, start_1idx, end_1idx, imports, docstring)
# end_1idx is INCLUSIVE (last line of the module)
modules = [
    # dashboard_db: from "Local retention database" section through end of _cleanup_old_snapshots
    ("dashboard_db", 92, 176,
     "import sqlite3\nimport time\nfrom server.config import DASHBOARD_DB, RETENTION_DAYS, _CHANNEL_REGISTRY",
     '"""Dashboard retention database."""'),
    
    # readers: from "Thread-safe caches" through end of get_state_db_stats
    # Note: _read_servers_config is at line 1708 (in servers section). We'll copy it here too.
    ("readers", 178, 382,
     "import os\nimport sqlite3\nimport json\nimport threading\nfrom server.config import HERMES_HOME",
     '"""Hermes data readers and shared caches."""'),
    
    # cron_parser: everything from "Cron expression parser" through build_crons
    ("cron_parser", 384, 997,
     "import os\nimport re\nimport subprocess\nimport time\nfrom datetime import datetime\nfrom server.config import HERMES_HOME",
     '"""Cron parsing utilities."""'),
    
    # health: VPS health collectors through get_prod_health
    ("health", 999, 1203,
     "import os\nimport subprocess\nimport threading\nimport time\nfrom server.config import PROD_CACHE_TTL\nfrom server.readers import _read_servers_config",
     '"""VPS health checks."""'),
    
    # profiles: build_profiles
    ("profiles", 1205, 1311,
     "import os\nfrom server.config import HERMES_HOME\nfrom server.readers import read_profile_yaml, read_config_yaml, get_state_db_stats",
     '"""Profile builder."""'),
    
    # content: content API helpers
    ("content", 1313, 1408,
     "import os\nfrom server.config import HERMES_HOME",
     '"""Content file management."""'),
    
    # kanban: kanban reader section
    ("kanban", 1410, 1529,
     "import os\nimport sqlite3\nfrom server.config import HERMES_HOME",
     '"""Kanban board reader."""'),
    
    # sessions: unified sessions + _tok_sum
    ("sessions", 1532, 1701,
     "import os\nfrom server.config import HERMES_HOME\nfrom server.readers import read_sqlite_ro",
     '"""Session ledger builder."""'),
    
    # servers: server discovery + per-server data. NOTE: _read_servers_config is used by health.py
    # We'll keep it in servers.py but read it from readers.py for the health import
    ("servers", 1704, 1919,
     "import json\nimport os\nimport subprocess\nimport time\nfrom server.config import SERVERS_CONFIG, HERMES_HOME\nfrom server.readers import read_json\nfrom server.cron_parser import cron_next_run\nfrom server.health import _get_health_for",
     '"""Server data collection."""'),
    
    # glance: weather + twitch
    ("glance", 1921, 2119,
     "import json\nimport os\nimport time\nimport urllib.request\nfrom server.config import HERMES_HOME",
     '"""Ambient data — weather, Twitch."""'),
    
    # sse: SSE multiplexer
    ("sse", 2121, 2229,
     "import hashlib\nimport json\nimport queue as queue_module\nimport threading\nimport time\nfrom server.config import _CHANNEL_FINGERPRINTS, _fp_lock, _CHANNEL_BURST, DASHBOARD_DB",
     '"""SSE multiplexer infrastructure."""'),
    
    # collectors: channel collectors through collect_server_crons
    ("collectors", 2232, 2320,
     "import os\nimport json\nfrom server.config import HERMES_HOME\nfrom server.readers import read_json\nfrom server.health import get_hermes_health, get_prod_health\nfrom server.profiles import build_profiles\nfrom server.sessions import build_unified_sessions, build_sessions_ledger\nfrom server.servers import build_servers\nfrom server.kanban import read_kanban_boards",
     '"""Per-channel data collectors."""'),
    
    # work_servers: from "Work Servers" through collect_work_postgres (not including _CHANNEL_COLLECTORS)
    ("work_servers", 2322, 2511,  # end before _CHANNEL_COLLECTORS at 2514
     "import json\nimport os\nimport subprocess\nimport time\nfrom server.config import HERMES_HOME\nfrom server.readers import _read_work_servers_config",
     '"""Work server (ansible) data collection."""'),
    
    # _CHANNEL_COLLECTORS dict + snapshot: includes the dict at 2514-2533 + build_snapshot
    ("snapshot", 2512, 2591,
     "import json\nimport os\nimport time\nfrom server.config import HERMES_HOME\nfrom server.dashboard_db import _save_snapshot_to_db\nfrom server.readers import read_json\nfrom server.health import get_hermes_health, get_prod_health\nfrom server.profiles import build_profiles\nfrom server.sessions import build_unified_sessions, build_sessions_ledger\nfrom server.servers import build_servers\nfrom server.kanban import read_kanban_boards\nfrom server.cron_parser import build_crons\nfrom server.collectors import collect_gateway, collect_processes, collect_hermes_health, collect_sessions_ledger, collect_profiles, collect_sessions, collect_kanban, collect_prod_health, collect_dokku, collect_server_crons, collect_servers\nfrom server.collectors import collect_work_system_health, collect_work_docker, collect_work_nexus, collect_work_jenkins, collect_work_postgres",
     '"""Snapshot assembly and channel collector registry."""'),
    
    # handler: HTTP Handlers section through end of MissionControlHandler class
    ("handler", 2593, 2977,
     "import http.server\nimport json\nimport os\nimport subprocess\nimport threading\nimport time\nimport urllib.parse\nfrom http import HTTPStatus\nfrom server.config import _CHANNEL_REGISTRY, _CHANNEL_FINGERPRINTS, _fp_lock, _CHANNEL_BURST, _SSE_QUEUE, CA_CERT_FILE, HERMES_HOME\nfrom server.sse import _sse_multiplex_drain\nfrom server.readers import _read_servers_config, read_json\nfrom server.content import list_content, read_content, save_content\nfrom server.glance import _get_glance_data\nfrom server.snapshot import _CHANNEL_COLLECTORS",
     '"""HTTP request handler."""'),
]

# Verify boundaries
print("Verifying boundaries:")
for name, start, end, imports, docstring in modules:
    first_line = lines[start-1].strip()
    last_line = lines[end-1].strip()
    print(f"  {name:20s} [{start:4d}-{end:4d}] start: {first_line[:60]}")
    print(f"  {'':20s} {'':10s} end:   {last_line[:60]}")

# Extract
for name, start, end, imports, docstring in modules:
    body_lines = lines[start-1:end]
    content = f"{docstring}\n\n{imports}\n{''.join(body_lines)}"
    
    path = f'server/{name}.py'
    with open(path, 'w') as f:
        f.write(content)
    print(f"  Wrote {name}.py ({len(body_lines)} lines)")

# Now handle the special case: _read_servers_config is used by health.py
# but it's in servers.py. We need to copy it to readers.py.
# The function is at line 1708. Let's extract it.
servers_config_func_lines = lines[1707:1715]  # 0-indexed
servers_config_code = ''.join(servers_config_func_lines)

# Also _read_work_servers_config at line 2333
work_servers_config_func_lines = lines[2332:2345]  # 0-indexed
work_servers_config_code = ''.join(work_servers_config_func_lines)

# Append both to readers.py
with open('server/readers.py', 'a') as f:
    f.write('\n\n# ── Server config readers (shared between health and servers modules) ──\n\n')
    f.write(servers_config_code)
    f.write('\n')
    f.write(work_servers_config_code)

print("\nAdded _read_servers_config and _read_work_servers_config to readers.py")
print("\nDone! Running syntax checks...")
