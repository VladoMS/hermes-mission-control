"""Work server (ansible) data collection."""

import json
import os
import subprocess
import time
import threading
from server.config import HERMES_HOME
from server.readers import read_json
# =============================================================================
# Work Servers — data collection from work-laptop over Tailscale
# =============================================================================

_WORK_LAPTOP = "work-laptop"
_WORK_SCRIPTS = "/workspace/hermes/scripts/work-servers"
_WORK_ANSIBLE_DIR = "/workspace/Git/DevOps-Main"
_work_servers_config = None
_work_servers_lock = threading.Lock()


def _read_work_servers_config():
    """Read work-servers.json, cached in memory."""
    global _work_servers_config
    if _work_servers_config is not None:
        return _work_servers_config
    with _work_servers_lock:
        if _work_servers_config is not None:
            return _work_servers_config
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "work-servers.json")
        cfg = read_json(path)
        _work_servers_config = cfg if cfg else {"servers": []}
        return _work_servers_config


def _run_ansible_script(ansible_group, script_name, timeout=45):
    """Run an ansible script module against a group. Returns parsed JSON per host.
    Returns dict: {hostname: parsed_json_data} or {} on failure."""
    cmd = (
        f"ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes "
        f"{_WORK_LAPTOP} "
        f"'cd {_WORK_ANSIBLE_DIR} && "
        f"ansible {ansible_group} -m script -a {_WORK_SCRIPTS}/{script_name} 2>/dev/null'"
    )
    results = {}
    try:
        import subprocess as _sp
        proc = _sp.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        output = proc.stdout
        # Parse ansible YAML-style output
        current_host = None
        in_stdout = False
        stdout_lines = []
        for line in output.split("\n"):
            # Detect host name line: "hostname | CHANGED =>" or "hostname | SUCCESS =>"
            if " | CHANGED =>" in line or " | SUCCESS =>" in line or " | FAILED =>" in line:
                if current_host and stdout_lines:
                    try:
                        results[current_host] = json.loads("".join(stdout_lines))
                    except json.JSONDecodeError:
                        pass
                current_host = line.split(" |")[0].strip()
                in_stdout = False
                stdout_lines = []
            elif current_host and line.strip().startswith("stdout:"):
                in_stdout = True
                continue
            elif current_host and in_stdout and line.startswith("        "):
                stdout_lines.append(line[8:])
            elif current_host and in_stdout and not line.startswith("        "):
                in_stdout = False
                if stdout_lines:
                    try:
                        results[current_host] = json.loads("".join(stdout_lines))
                    except json.JSONDecodeError:
                        pass
                stdout_lines = []
        # Don't forget the last host
        if current_host and stdout_lines:
            try:
                results[current_host] = json.loads("".join(stdout_lines))
            except json.JSONDecodeError:
                pass
    except Exception:
        pass
    return results


def collect_work_system_health():
    """Collect CPU/MEM/DISK health from all work servers. Returns dict."""
    cfg = _read_work_servers_config()
    servers = []
    seen_groups = set()

    for srv in cfg.get("servers", []):
        group = srv.get("ansible_group")
        if not group or group in seen_groups:
            continue
        seen_groups.add(group)

        # Collect from ALL hosts in the ansible group
        data = _run_ansible_script(group, "system_health.py")
        for hostname, health in data.items():
            servers.append({
                "server_name": srv["name"],
                "ansible_group": group,
                "hostname": hostname,
                "health": health,
            })

    return {"servers": servers, "collected_at": time.time()}


def collect_work_docker():
    """Collect Docker stats from servers with the 'docker' or 'docker_swarm' role."""
    cfg = _read_work_servers_config()
    results = []
    for srv in cfg.get("servers", []):
        roles = srv.get("roles", [])
        if "docker" not in roles and "docker_swarm" not in roles:
            continue
        group = srv.get("ansible_group")
        if not group:
            continue
        data = _run_ansible_script(group, "docker_stats.py")
        for hostname, stats in data.items():
            results.append({
                "server_name": srv["name"],
                "hostname": hostname,
                "docker": stats.get("docker", {}),
            })
    return {"servers": results, "collected_at": time.time()}


def collect_work_nexus():
    """Collect Nexus repository stats."""
    cfg = _read_work_servers_config()
    results = []
    for srv in cfg.get("servers", []):
        if "nexus" not in srv.get("roles", []):
            continue
        group = srv.get("ansible_group")
        if not group:
            continue
        data = _run_ansible_script(group, "nexus_stats.py")
        for hostname, stats in data.items():
            results.append({
                "server_name": srv["name"],
                "hostname": hostname,
                "nexus": stats.get("nexus", {}),
            })
    return {"servers": results, "collected_at": time.time()}


def collect_work_jenkins():
    """Collect Jenkins stats from old and new instances."""
    cfg = _read_work_servers_config()
    results = []
    for srv in cfg.get("servers", []):
        roles = srv.get("roles", [])
        if "jenkins_old" not in roles and "jenkins_new" not in roles:
            continue
        group = srv.get("ansible_group")
        if not group:
            continue
        data = _run_ansible_script(group, "jenkins_stats.py")
        for hostname, stats in data.items():
            # Determine which jenkins instance this is
            jtype = "old" if "jenkins_old" in roles else "new"
            if "jenkins_new" in roles:
                jtype = "new"
            results.append({
                "server_name": srv["name"],
                "hostname": hostname,
                "jenkins_type": jtype,
                "jenkins": stats.get("jenkins", {}),
            })
    return {"servers": results, "collected_at": time.time()}


def collect_work_postgres():
    """Collect Postgres, Patroni, and Etcd stats from all PG servers."""
    cfg = _read_work_servers_config()
    results = []
    for srv in cfg.get("servers", []):
        if "postgres" not in srv.get("roles", []):
            continue
        group = srv.get("ansible_group")
        if not group:
            continue
        data = _run_ansible_script(group, "postgres_stats.py")
        for hostname, stats in data.items():
            results.append({
                "server_name": srv["name"],
                "hostname": hostname,
                "postgres": stats.get("postgres", {}),
                "patroni": stats.get("patroni", {}),
                "etcd": stats.get("etcd", {}),
            })
    return {"servers": results, "collected_at": time.time()}
