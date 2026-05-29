"""Server data collection."""

import json
import os
import subprocess
import time
from server.config import SERVERS_CONFIG, HERMES_HOME
from server.readers import read_json
from server.cron_parser import cron_next_run
from server.health import _get_health_for, get_prod_health
# =============================================================================
# Servers — dynamic server discovery + per-server data
# =============================================================================

def _read_servers_config():
    """Load servers.json. Returns list of server dicts or empty list on failure."""
    try:
        with open(SERVERS_CONFIG) as f:
            cfg = json.load(f)
        return sorted(cfg.get("servers", []), key=lambda s: s.get("sort_order", 99))
    except Exception:
        return []

def _ssh(host, cmd, timeout=10):
    """Run a command over SSH. Returns (stdout, exit_code) or (None, -1) on failure."""
    try:
        p = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", host, cmd],
            capture_output=True, text=True, timeout=timeout
        )
        return p.stdout.strip(), p.returncode
    except Exception:
        return None, -1

def _get_dokku_data(host):
    """Collect Dokku app list and container status from a remote host.
    Returns dict with apps, containers, and per-app stats, or None if not a Dokku host."""
    if host == "localhost":
        return None
    result = {"apps": [], "containers": [], "container_stats": {}, "errors": []}

    # Dokku apps — try command, fall back gracefully
    out, rc = _ssh(host, "dokku apps:list 2>/dev/null || dokku ls 2>/dev/null")
    if rc == 0 and out:
        for line in out.split("\n"):
            line = line.strip()
            if line and line != "=====> My Apps" and not line.startswith("---"):
                result["apps"].append(line)
    elif out:
        for line in out.split("\n"):
            line = line.strip()
            if line and line != "=====> My Apps" and not line.startswith("---"):
                result["apps"].append(line)

    # Docker containers (PS format: short ID, image, status, names)
    out, rc = _ssh(host, "docker ps --format '{{.ID}}\\t{{.Image}}\\t{{.Status}}\\t{{.Names}}' 2>/dev/null")
    if rc == 0 and out:
        for line in out.split("\n"):
            parts = line.split("\t")
            if len(parts) >= 4:
                result["containers"].append({
                    "id": parts[0],
                    "image": parts[1],
                    "status": parts[2],
                    "name": parts[3],
                })

    # Docker stats — per-container CPU/MEM (one-shot, no stream)
    out, rc = _ssh(host, "docker stats --no-stream --format '{{.Name}}\\t{{.CPUPerc}}\\t{{.MemPerc}}\\t{{.MemUsage}}' 2>/dev/null", timeout=8)
    if rc == 0 and out:
        for line in out.split("\n"):
            parts = line.split("\t")
            if len(parts) >= 4:
                name = parts[0]
                cpu = parts[1].rstrip('%')
                mem = parts[2].rstrip('%')
                mem_usage = parts[3]
                try:
                    result["container_stats"][name] = {
                        "cpu_pct": float(cpu),
                        "mem_pct": float(mem),
                        "mem_usage": mem_usage,
                    }
                except ValueError:
                    result["container_stats"][name] = {
                        "cpu_pct": 0,
                        "mem_pct": 0,
                        "mem_usage": mem_usage,
                    }

    return result

def _get_server_crons(host, errors_out):
    """Get cron jobs for a specific server. Returns list of cron entries."""
    if host == "localhost":
        # Reuse the existing build_crons which reads Hermes + system locally
        return build_crons(errors_out)
    
    # Remote: read via SSH (simplified — just raw crontab lines)
    crons = []
    out, rc = _ssh(host, "cat /var/spool/cron/crontabs/root /etc/crontab /etc/cron.d/* 2>/dev/null")
    if rc == 0 and out:
        for line in out.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("PATH=") and not line.startswith("SHELL="):
                parts = line.split()
                if len(parts) >= 6 and _looks_like_cron(" ".join(parts[:5])):
                    expr = " ".join(parts[:5])
                    cmd = " ".join(parts[5:])
                    crons.append({
                        "schedule_display": expr,
                        "schedule_desc": cron_to_human(expr) if cron_to_human(expr) else expr,
                        "command": cmd[:120],
                        "source": "system",
                        "host": host,
                    })
    return crons

def _looks_like_cron(field):
    """Quick check if a string looks like a valid cron expression."""
    import re
    return bool(re.match(r'^[\d*/,\-]+\s+[\d*/,\-]+\s+[\d*/,\-]+\s+[\d*/,\-]+\s+[\d*/,\-]+$', field))


def build_servers(errors_out):
    """Build servers array for the snapshot. One entry per server in servers.json."""
    servers_cfg = _read_servers_config()
    servers = []

    for srv in servers_cfg:
        name = srv["name"]
        host = srv["host"]
        entry = {
            "name": name,
            "display": srv.get("display", name),
            "host": host,
            "type": srv.get("type", "vps"),
            "notes": srv.get("notes", ""),
            "has_dokku": srv.get("has_dokku", False),
            "cron_label": srv.get("cron_label", "JOBS"),
            "health": {},
            "crons": [],
            "dokku": None,
        }

        # Health — use proper collector per host
        if host == "localhost":
            entry["health"] = get_hermes_health(errors_out)
        elif host == "prod":
            entry["health"] = get_prod_health(errors_out)
        else:
            entry["health"] = _get_health_for(host, errors_out)

        # Cron jobs
        entry["crons"] = _get_server_crons(host, errors_out)

        # Dokku (only if applicable)
        if srv.get("has_dokku"):
            dokku = _get_dokku_data(host)
            if dokku:
                entry["dokku"] = dokku

        servers.append(entry)

    return servers
