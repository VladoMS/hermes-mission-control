"""VPS health checks."""

import os
import subprocess
import threading
import time
from server.config import PROD_CACHE_TTL
from server.readers import _read_servers_config
# =============================================================================
# VPS Health Collectors
# =============================================================================

def _parse_proc_stat(line):
    """Parse a /proc/stat cpu line into a dict. First token is 'cpu' (label), rest are numbers."""
    parts = line.strip().split()
    # parts[0] = 'cpu', parts[1:] = user, nice, system, idle, iowait, irq, softirq, steal, guest, guest_nice
    fields = ["user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal", "guest", "guest_nice"]
    values = parts[1:]
    return {fields[i]: int(values[i]) for i in range(min(len(fields), len(values)))}


def _cpu_total_and_idle(sample):
    """Return (total, idle) jiffies from a /proc/stat cpu sample dict."""
    idle = sample.get("idle", 0) + sample.get("iowait", 0)
    total = sum(v for k, v in sample.items() if k != "cpu")
    return total, idle


def get_hermes_health(errors_out):
    """Collect hermes VPS health: CPU (two-sample diff), RAM, disk. Mutates errors_out."""
    result = {"cpu_pct": None, "mem": None, "disk": None}

    # --- CPU (two-sample diff, thread-safe) ---
    global _last_cpu_sample
    try:
        with open("/proc/stat", "r") as f:
            current = _parse_proc_stat(f.readline())
        with _cpu_lock:
            prev = _last_cpu_sample
            _last_cpu_sample = current
        if prev is not None:
            prev_total, prev_idle = _cpu_total_and_idle(prev)
            curr_total, curr_idle = _cpu_total_and_idle(current)
            tdiff = curr_total - prev_total
            if tdiff > 0:
                result["cpu_pct"] = round(100.0 * (1.0 - (curr_idle - prev_idle) / tdiff), 1)
            else:
                result["cpu_pct"] = 0.0
    except Exception as e:
        errors_out.append(f"hermes cpu: {e}")

    # --- RAM ---
    try:
        mem = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if ":" in line:
                    key, _, val = line.partition(":")
                    parts = val.strip().split()
                    if parts:
                        mem[key.strip()] = int(parts[0])
        total = mem.get("MemTotal", 0)
        available = mem.get("MemAvailable", mem.get("MemFree", 0))
        used = total - available
        pct = round(100.0 * used / total, 1) if total > 0 else 0.0
        result["mem"] = {
            "mem_total_mb": round(total / 1024, 1),
            "mem_used_mb": round(used / 1024, 1),
            "mem_available_mb": round(available / 1024, 1),
            "mem_pct": pct,
        }
    except Exception as e:
        errors_out.append(f"hermes mem: {e}")

    # --- Disk ---
    try:
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free
        pct = round(100.0 * used / total, 1) if total > 0 else 0.0
        result["disk"] = {
            "disk_total_gb": round(total / (1024 ** 3), 1),
            "disk_used_gb": round(used / (1024 ** 3), 1),
            "disk_free_gb": round(free / (1024 ** 3), 1),
            "disk_pct": pct,
        }
    except Exception as e:
        errors_out.append(f"hermes disk: {e}")

    # --- Uptime ---
    try:
        with open("/proc/uptime", "r") as f:
            result["uptime"] = float(f.readline().split()[0])
    except Exception as e:
        errors_out.append(f"hermes uptime: {e}")

    return result


def _collect_prod_health_raw():
    """Execute one SSH call to prod gathering cpu×2, meminfo, and df. Returns (data, errors)."""
    result = {"cpu_pct": None, "mem": None, "disk": None, "ssh_ok": False}
    errors = []

    # Single SSH call: read /proc/stat twice (with remote sleep) + meminfo + df
    cmd = (
        "head -1 /proc/stat; sleep 0.5; head -1 /proc/stat; "
        "cat /proc/meminfo; df -B1 / | tail -1"
    )
    try:
        proc = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no", "prod", cmd],
            capture_output=True, text=True, timeout=12,
        )
        if proc.returncode != 0:
            errors.append(f"prod ssh: exit code {proc.returncode}")
            return result, errors

        result["ssh_ok"] = True
        lines = proc.stdout.strip().split("\n")

        # First two lines are /proc/stat samples
        if len(lines) >= 2:
            try:
                s1 = _parse_proc_stat(lines[0])
                s2 = _parse_proc_stat(lines[1])
                t1, i1 = _cpu_total_and_idle(s1)
                t2, i2 = _cpu_total_and_idle(s2)
                if t2 > t1:
                    result["cpu_pct"] = round(100.0 * (1.0 - (i2 - i1) / (t2 - t1)), 1)
            except Exception as e:
                errors.append(f"prod cpu parse: {e}")

        # Parse /proc/meminfo lines between cpu samples and df
        mem = {}
        in_mem = False
        for line in lines[2:]:
            if line.startswith("MemTotal:"):
                in_mem = True
            if in_mem and ":" in line:
                key, _, val = line.partition(":")
                parts = val.strip().split()
                if parts and parts[0].isdigit():
                    mem[key.strip()] = int(parts[0])
            if line.startswith("Filesystem") or (in_mem and line.startswith("/")):
                in_mem = False

        if mem:
            total = mem.get("MemTotal", 0)
            available = mem.get("MemAvailable", mem.get("MemFree", 0))
            used = total - available
            pct = round(100.0 * used / total, 1) if total > 0 else 0.0
            result["mem"] = {
                "mem_total_mb": round(total / 1024, 1),
                "mem_used_mb": round(used / 1024, 1),
                "mem_available_mb": round(available / 1024, 1),
                "mem_pct": pct,
            }
        else:
            errors.append("prod mem: parse failure")

        # Last line is df output
        df_line = lines[-1].strip()
        if df_line:
            parts = df_line.split()
            if len(parts) >= 5:
                try:
                    total_b = int(parts[1])
                    used_b = int(parts[2])
                    avail_b = int(parts[3])
                    pct_str = parts[4].rstrip("%")
                    result["disk"] = {
                        "disk_total_gb": round(total_b / (1024 ** 3), 1),
                        "disk_used_gb": round(used_b / (1024 ** 3), 1),
                        "disk_free_gb": round(avail_b / (1024 ** 3), 1),
                        "disk_pct": float(pct_str) if pct_str.replace(".", "").replace("-", "").isdigit() else 0.0,
                    }
                except (ValueError, IndexError):
                    errors.append("prod disk: df parse failure")
        else:
            errors.append("prod disk: no df output")

    except subprocess.TimeoutExpired:
        errors.append("prod ssh: timeout (>12s)")
    except Exception as e:
        errors.append(f"prod ssh: {e}")

    return result, errors


def get_prod_health(errors_out):
    """
    Collect prod VPS health. Cached for PROD_CACHE_TTL seconds.
    Mutates errors_out with any cache-fresh errors.
    """
    global _prod_cache, _prod_errors_cache
    now = time.time()

    with _prod_lock:
        if _prod_cache and (now - _prod_cache["ts"]) < PROD_CACHE_TTL:
            errors_out.extend(_prod_errors_cache)
            return dict(_prod_cache["data"])  # shallow copy

    # Cache miss — do the SSH call
    data, errs = _collect_prod_health_raw()
    with _prod_lock:
        _prod_cache = {"data": data, "ts": now}
        _prod_errors_cache = list(errs)

    errors_out.extend(errs)
    return dict(data)



def _get_health_for(host, errors_out):
    """Get VPS health for any host. Local = direct /proc, remote = SSH /proc."""
    if host == "localhost":
        return get_hermes_health(errors_out)
    
    # SSH-based health collection (reuse prod pattern but for any host)
    data = {"cpu_pct": None, "mem": None, "disk": None, "ssh_ok": False}
    try:
        out, rc = _ssh(host, "cat /proc/stat /proc/meminfo && df -BG / | tail -1", timeout=8)
        if rc != 0:
            errors_out.append(f"{host} health: SSH failed (code {rc})")
            return data
        data["ssh_ok"] = True
        
        lines = out.split("\n")
        # Parse /proc/stat (first line = cpu total)
        if lines:
            parts = lines[0].split()
            if len(parts) >= 5:
                # Simple single-sample CPU: just report what we can
                total = sum(int(p) for p in parts[1:5]) if len(parts) >= 5 else 1
                idle = int(parts[4]) if len(parts) >= 5 else 0
                data["cpu_pct"] = 0.0  # Need two samples; first call seeds the baseline
        
        # Parse /proc/meminfo
        mem_total = mem_avail = 0
        for line in lines:
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1]) // 1024
            if line.startswith("MemAvailable:"):
                mem_avail = int(line.split()[1]) // 1024
        if mem_total > 0:
            mem_used = mem_total - mem_avail
            data["mem"] = {
                "mem_total_mb": mem_total,
                "mem_used_mb": mem_used,
                "mem_available_mb": mem_avail,
                "mem_pct": round(mem_used / mem_total * 100, 1),
            }
        
        # Parse df output
        for line in lines:
            if line.endswith("G") and "/" in line:
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        total_gb = float(parts[1].rstrip("G"))
                        used_gb = float(parts[2].rstrip("G"))
                        data["disk"] = {
                            "disk_total_gb": total_gb,
                            "disk_used_gb": used_gb,
                            "disk_free_gb": round(total_gb - used_gb, 1),
                            "disk_pct": round(used_gb / total_gb * 100, 1) if total_gb > 0 else 0,
                        }
                    except ValueError:
                        pass
        
    except Exception as e:
        errors_out.append(f"{host} health: {e}")
    
    return data

