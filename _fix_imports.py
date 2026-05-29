#!/usr/bin/env python3
"""Fix import issues across extracted modules."""
import os

os.chdir('/home/hermes/mission-control')

# 1. Move _get_health_for from servers.py to health.py
# _get_health_for is at original line 1817, currently in servers.py
# It's a pure SSH helper that belongs in health.py

# Read servers.py to find _get_health_for
with open('server/servers.py') as f:
    servers_content = f.read()

# Find _get_health_for function
import re
# Find from "def _get_health_for" through the next def/class at same indent level
match = re.search(r'(def _get_health_for\(.*?)(?=\n(?:def |class |# ====))', servers_content, re.DOTALL)
if not match:
    # Try to find it by searching for the function name
    idx = servers_content.find('def _get_health_for')
    if idx == -1:
        print("ERROR: _get_health_for not found in servers.py")
        exit(1)
    # Find the next def at the same indentation level
    rest = servers_content[idx:]
    next_def = re.search(r'\n(?:def |class )', rest[30:])  # skip past the def line
    if next_def:
        end_idx = idx + 30 + next_def.start()
        func_text = servers_content[idx:end_idx]
    else:
        func_text = servers_content[idx:]
else:
    func_text = match.group(1)

# Remove from servers.py
servers_new = servers_content.replace(func_text, '')
with open('server/servers.py', 'w') as f:
    f.write(servers_new)

# Append to health.py
with open('server/health.py', 'a') as f:
    f.write('\n\n')
    f.write(func_text)
    f.write('\n')

print("Moved _get_health_for from servers.py to health.py")

# 2. Fix work_servers.py — add threading import
with open('server/work_servers.py') as f:
    ws = f.read()

ws = ws.replace(
    'from server.config import HERMES_HOME',
    'import threading\nfrom server.config import HERMES_HOME'
)
with open('server/work_servers.py', 'w') as f:
    f.write(ws)
print("Added threading import to work_servers.py")

# 3. Fix servers.py — remove _get_health_for import from health
servers_new = servers_new.replace(
    'from server.health import _get_health_for\n',
    'from server.health import _get_health_for, get_prod_health\n'
)
# But wait, servers.py now doesn't have _get_health_for — it imports it
# The import line is already there. Just verify.
with open('server/servers.py', 'w') as f:
    f.write(servers_new)
print("Updated servers.py imports")

# 4. Fix handler.py — it imports from server.snapshot which imports from collectors
# handler imports _CHANNEL_COLLECTORS from snapshot. That's already set up.
# But handler also uses collectors directly. Let me check.

# 5. Verify we can import health, servers, collectors, snapshot, handler
import sys
import importlib

critical = ['server.health', 'server.servers', 'server.collectors', 'server.snapshot', 'server.handler', 'server.work_servers']
for mod in critical:
    try:
        # Clear cache
        if mod in sys.modules:
            del sys.modules[mod]
        importlib.import_module(mod)
        print(f"  {mod}: OK")
    except Exception as e:
        print(f"  {mod}: FAIL — {e}")

print("\nDone fixing imports")
