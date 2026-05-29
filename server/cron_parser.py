"""Cron parsing utilities."""

import os
import re
import subprocess
import time
from datetime import datetime
from server.config import HERMES_HOME
# =============================================================================
# Cron expression parser — human-readable descriptions
# =============================================================================

_CRON_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_CRON_DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def _pad_time(h, m):
    """Return 'HH:MM' zero-padded."""
    return f"{int(h):02d}:{int(m):02d}"


def _parse_cron_field(field, lo, hi, names=None):
    """
    Parse a single cron field. Returns ('all' | 'list' | 'range' | 'step', data).
    data: for 'all' → None; for 'list' → list of ints; for 'range' → (start, end);
          for 'step' → (start, end, step).
    """
    field = field.strip()
    if field == "*":
        return ("all", None)

    # Step: */N or S-E/N
    if "/" in field:
        base, _, step = field.partition("/")
        step = int(step)
        if base == "*":
            return ("step", (lo, hi, step))
        if "-" in base:
            s, e = base.split("-", 1)
            return ("step", (int(s), int(e), step))
        return ("step", (int(base), hi, step))

    # Range: S-E
    if "-" in field:
        s, e = field.split("-", 1)
        return ("range", (int(s), int(e)))

    # List: a,b,c
    if "," in field:
        return ("list", [int(x) for x in field.split(",")])

    # Single value
    return ("single", int(field))


def _cron_desc_minute(m):
    """Return a phrase describing the minutes field."""
    kind, data = _parse_cron_field(m, 0, 59)
    if kind == "all":
        return ""
    if kind == "single":
        return f"at minute {data}"
    if kind == "list":
        return f"at minutes {', '.join(map(str, data))}"
    if kind == "range":
        return f"every minute from {data[0]} to {data[1]}"
    if kind == "step":
        if data[0] == 0 and data[1] == 59:
            return f"every {data[2]} minutes"
        return f"every {data[2]} minutes from {data[0]} to {data[1]}"
    return ""


def _cron_desc_hour(h):
    """Return a phrase describing the hour field."""
    kind, data = _parse_cron_field(h, 0, 23)
    if kind == "all":
        return ""
    if kind == "single":
        return f"at {_pad_time(data, 0)}"
    if kind == "list":
        times = [_pad_time(x, 0) for x in data]
        return "at " + ", ".join(times)
    if kind == "range":
        return f"every hour from {_pad_time(data[0], 0)} to {_pad_time(data[1], 0)}"
    if kind == "step":
        if data[0] == 0 and data[1] == 23:
            return f"every {data[2]} hours"
        return f"every {data[2]} hours from {data[0]} to {data[1]}"
    return ""


def _cron_desc_dom(dom):
    """Return a phrase describing the day-of-month field."""
    kind, data = _parse_cron_field(dom, 1, 31)
    if kind == "all":
        return ""
    if kind == "single":
        return f"on day {data}"
    if kind == "list":
        return "on days " + ", ".join(map(str, data))
    if kind == "range":
        return f"on days {data[0]}–{data[1]}"
    if kind == "step":
        return f"every {data[2]} days starting day {data[0]}"
    return ""


def _cron_desc_month(mon):
    """Return a phrase describing the month field."""
    kind, data = _parse_cron_field(mon, 1, 12)
    if kind == "all":
        return ""
    if kind == "single":
        return f"in {_CRON_MONTHS[data]}"
    if kind == "list":
        names = [_CRON_MONTHS[x] for x in data]
        return "in " + ", ".join(names)
    if kind == "range":
        return f"from {_CRON_MONTHS[data[0]]} to {_CRON_MONTHS[data[1]]}"
    if kind == "step":
        return f"every {data[2]} months from {_CRON_MONTHS[data[0]]}"
    return ""


def _cron_desc_dow(dow):
    """Return a phrase describing the day-of-week field."""
    kind, data = _parse_cron_field(dow, 0, 7)
    if kind == "all":
        return ""
    if kind == "single":
        idx = data if data <= 6 else 0
        return f"on {_CRON_DAYS[idx]}"
    if kind == "list":
        names = [_CRON_DAYS[x if x <= 6 else 0] for x in data]
        return "on " + ", ".join(names)
    if kind == "range":
        s = data[0] if data[0] <= 6 else 0
        e = data[1] if data[1] <= 6 else 6
        return f"{_CRON_DAYS[s]} through {_CRON_DAYS[e]}"
    if kind == "step":
        return f"every {data[2]} days of week from {_CRON_DAYS[data[0]]}"
    return ""


def cron_to_human(expr):
    """
    Convert a 5-field cron expression to a human-readable English description.

    Returns a short string like 'Every day at 03:00', 'Every 30 minutes', etc.
    """
    try:
        parts = expr.strip().split()
        if len(parts) != 5:
            return expr
        minute, hour, dom, month, dow = parts
    except Exception:
        return expr

    # Detect "every N minutes" (step on minutes, * everything else)
    mkind, mdata = _parse_cron_field(minute, 0, 59)
    if mkind == "step" and hour == "*" and dom == "*" and month == "*" and dow == "*":
        return f"Every {mdata[2]} minutes"

    # Detect "every minute" (* * * * *)
    if minute == "*" and hour == "*" and dom == "*" and month == "*" and dow == "*":
        return "Every minute"

    # Hour-level patterns
    hkind, hdata = _parse_cron_field(hour, 0, 23)

    # Every hour at minute N
    if mkind == "single" and hour == "*" and dom == "*" and month == "*" and dow == "*":
        return f"Every hour at minute {mdata}"

    # Every N hours
    if mkind == "single" and hkind == "step" and dom == "*" and month == "*" and dow == "*":
        if hdata[0] == 0 and hdata[1] == 23:
            if mdata != 0:
                return f"Every {hdata[2]} hours at minute {mdata}"
            return f"Every {hdata[2]} hours"
        return f"Every {hdata[2]} hours from {hdata[0]}:00 to {hdata[1]}:00 at minute {mdata}"

    # Every day at HH:MM
    if hour != "*" and dom == "*" and month == "*" and dow == "*":
        hkind2, hdata2 = _parse_cron_field(hour, 0, 23)
        if hkind2 == "single" and (mkind == "single" or mkind == "all"):
            m_val = mdata if mkind == "single" else 0
            return f"Every day at {_pad_time(hdata2, m_val)}"
        if hkind2 == "list" and mkind == "single":
            times = [f"{_pad_time(x, mdata)}" for x in hdata2]
            return "Every day at " + ", ".join(times)
        if hkind2 == "step" and hdata2[0] == 0 and hdata2[1] == 23:
            if mkind == "single" and mdata != 0:
                return f"Every {hdata2[2]} hours at minute {mdata}"
            return f"Every {hdata2[2]} hours"

    # Day-of-week patterns — "Every Monday at HH:MM"
    if dow != "*" and dom == "*":
        hkind3, hdata3 = _parse_cron_field(hour, 0, 23)
        if hkind3 == "single" and (mkind == "single" or mkind == "all"):
            m_val = mdata if mkind == "single" else 0
            time_str = f" at {_pad_time(hdata3, m_val)}"
            dkind, ddata = _parse_cron_field(dow, 0, 7)
            if dkind == "single":
                idx = ddata if ddata <= 6 else 0
                return f"Every {_CRON_DAYS[idx]}{time_str}"
            if dkind == "list":
                names = [_CRON_DAYS[x if x <= 6 else 0] for x in ddata]
                return f"Every {', '.join(names)}{time_str}"
        return _cron_desc_dow(dow) + " " + _cron_desc_hour(hour) + " " + _cron_desc_minute(minute)

    # Day-of-month patterns — "1st of every month at HH:MM"
    if dom != "*":
        hkind4, hdata4 = _parse_cron_field(hour, 0, 23)
        if hkind4 == "single" and (mkind == "single" or mkind == "all"):
            m_val = mdata if mkind == "single" else 0
            time_str = f" at {_pad_time(hdata4, m_val)}"
            if dom.isdigit():
                d = int(dom)
                suffix = "th" if 11 <= d <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th")
                return f"{d}{suffix} of every month{time_str}"
            return f"On day {dom} of every month{time_str}"

    # Fallback: stitch field descriptions
    pieces = []
    for fn in [_cron_desc_minute, _cron_desc_hour, _cron_desc_dom, _cron_desc_month, _cron_desc_dow]:
        p = fn
        if p == _cron_desc_minute:
            desc = _cron_desc_minute(minute)
        elif p == _cron_desc_hour:
            desc = _cron_desc_hour(hour)
        elif p == _cron_desc_dom:
            desc = _cron_desc_dom(dom)
        elif p == _cron_desc_month:
            desc = _cron_desc_month(month)
        else:
            desc = _cron_desc_dow(dow)
        if desc:
            pieces.append(desc)

    if pieces:
        return " ".join(pieces).capitalize()
    return expr


# =============================================================================
# Cron next-run calculator
# =============================================================================

import calendar as _calendar

def _next_cron_field(value, kind, data, lo, hi):
    """Find the next valid value >= `value` for a single cron field. Returns (next_val, wrapped)."""
    if kind == "all":
        return value, False
    if kind == "single":
        if value <= data:
            return data, False
        else:
            return lo, True   # wrap: no valid value remaining in this range
    if kind == "list":
        for v in data:
            if v >= value:
                return v, False
        return data[0], True  # wrap to first in list
    if kind == "range":
        if value < data[0]:
            return data[0], False
        if value <= data[1]:
            return value, False
        return data[0], True  # wrap
    if kind == "step":
        start, end, step = data
        if value < start:
            return start, False
        if value <= end:
            # Find first multiple of step >= value, starting from start
            dist = value - start
            next_val = start + ((dist + step - 1) // step) * step
            if next_val <= end:
                return next_val, False
        return start, True  # wrap
    return value, False


def cron_next_run(expr, from_ts=None):
    """
    Calculate the next time a 5-field cron expression will fire, as a Unix timestamp.
    Uses a simple minute-by-minute search (max 2 years forward, ~1M iterations).
    Returns the next timestamp or None if no match within 2 years.
    """
    import datetime as _dt

    try:
        parts = expr.strip().split()
        if len(parts) != 5:
            return None
        m_expr, h_expr, dom_expr, mon_expr, dow_expr = parts
    except Exception:
        return None

    # Pre-parse all fields
    m_info = (m_expr, _parse_cron_field(m_expr, 0, 59))
    h_info = (h_expr, _parse_cron_field(h_expr, 0, 23))
    dom_info = (dom_expr, _parse_cron_field(dom_expr, 1, 31))
    mon_info = (mon_expr, _parse_cron_field(mon_expr, 1, 12))
    dow_info = (dow_expr, _parse_cron_field(dow_expr, 0, 7))

    if from_ts is None:
        now = _dt.datetime.utcnow()
    else:
        now = _dt.datetime.utcfromtimestamp(from_ts)

    # Start from current minute
    year, month, day, hour, minute = now.year, now.month, now.day, now.hour, now.minute
    # Increment by 1 minute so "now" doesn't match if it just fired
    minute += 1

    max_iter = 2 * 366 * 24 * 60  # ~2 years in minutes
    for _ in range(max_iter):
        if minute >= 60:
            minute = 0
            hour += 1
        if hour >= 24:
            hour = 0
            day += 1
        days_in_month = _calendar.monthrange(year, month)[1]
        if day > days_in_month:
            day = 1
            month += 1
        if month > 12:
            month = 1
            year += 1

        # Check each field
        dow = _calendar.weekday(year, month, day)  # 0=Mon, need 0=Sun for cron
        cron_dow = (dow + 1) % 7

        # Minute match
        m_kind, m_data = m_info[1]
        if m_kind == "single" and minute != m_data:
            minute += 1; continue
        elif m_kind == "list" and minute not in m_data:
            minute += 1; continue
        elif m_kind == "range" and not (m_data[0] <= minute <= m_data[1]):
            minute += 1; continue
        elif m_kind == "step":
            start, end, step = m_data
            if start <= minute <= end and (minute - start) % step == 0:
                pass
            else:
                minute += 1; continue

        # Hour match
        h_kind, h_data = h_info[1]
        if h_kind == "single" and hour != h_data:
            minute = 0; hour += 1; continue
        elif h_kind == "list" and hour not in h_data:
            minute = 0; hour += 1; continue
        elif h_kind == "range" and not (h_data[0] <= hour <= h_data[1]):
            minute = 0; hour += 1; continue
        elif h_kind == "step":
            start, end, step = h_data
            if not (start <= hour <= end and (hour - start) % step == 0):
                minute = 0; hour += 1; continue

        # Day-of-month and day-of-week: OR relationship in cron
        dom_kind, dom_data = dom_info[1]
        dow_kind, dow_data = dow_info[1]

        dom_ok = True
        dow_ok = True

        # If either field is non-*, both must match (OR).
        # If both are non-*, either match is sufficient.
        # If both are *, both are ok.

        if dom_expr != "*":
            dom_ok = False
            if dom_kind == "single" and day == dom_data:
                dom_ok = True
            elif dom_kind == "list" and day in dom_data:
                dom_ok = True
            elif dom_kind == "range" and dom_data[0] <= day <= dom_data[1]:
                dom_ok = True
            elif dom_kind == "step":
                start, end, step = dom_data
                if start <= day <= end and (day - start) % step == 0:
                    dom_ok = True

        if dow_expr != "*":
            dow_ok = False
            if dow_kind == "single":
                target = dow_data if dow_data <= 6 else 0
                if cron_dow == target:
                    dow_ok = True
            elif dow_kind == "list":
                targets = [x if x <= 6 else 0 for x in dow_data]
                if cron_dow in targets:
                    dow_ok = True
            elif dow_kind == "range":
                s = dow_data[0] if dow_data[0] <= 6 else 0
                e = dow_data[1] if dow_data[1] <= 6 else 6
                if s <= cron_dow <= e:
                    dow_ok = True
            elif dow_kind == "step":
                start = dow_data[0] if dow_data[0] <= 6 else 0
                if (cron_dow - start) % dow_data[2] == 0:
                    dow_ok = True

        # Cron OR semantics: if both fields are specified (non-*), either matching is enough.
        # If only one is specified, that one must match.
        if dom_expr != "*" and dow_expr != "*":
            if not (dom_ok or dow_ok):
                minute = 0; hour = 0; day += 1; continue
        elif dom_expr != "*" and not dom_ok:
            minute = 0; hour = 0; day += 1; continue
        elif dow_expr != "*" and not dow_ok:
            minute = 0; hour = 0; day += 1; continue

        # Month match
        mon_kind, mon_data = mon_info[1]
        if mon_kind == "single" and month != mon_data:
            minute = 0; hour = 0; day = 1; month += 1; continue
        elif mon_kind == "list" and month not in mon_data:
            minute = 0; hour = 0; day = 1; month += 1; continue
        elif mon_kind == "range" and not (mon_data[0] <= month <= mon_data[1]):
            minute = 0; hour = 0; day = 1; month += 1; continue
        elif mon_kind == "step":
            start, end, step = mon_data
            if not (start <= month <= end and (month - start) % step == 0):
                minute = 0; hour = 0; day = 1; month += 1; continue

        # All checks passed — found next run
        ts = _dt.datetime(year, month, day, hour, minute, 0).timestamp()
        return ts

    return None


def _relative_time(ts):
    """Convert a future Unix timestamp to a relative string like 'in 3h 12m'."""
    now = time.time()
    diff = int(ts - now)
    if diff < 0:
        return "now"
    if diff < 60:
        return "in <1m"
    if diff < 3600:
        return f"in {diff // 60}m"
    hours = diff // 3600
    minutes = (diff % 3600) // 60
    if hours < 48:
        if minutes == 0:
            return f"in {hours}h"
        return f"in {hours}h {minutes}m"
    days = hours // 24
    hours = hours % 24
    if hours == 0:
        return f"in {days}d"
    return f"in {days}d {hours}h"


# =============================================================================
# Cron Data Source — unified Hermes + system crontabs
# =============================================================================

def _parse_system_cron_line(line, source_label, source_path):
    """
    Parse one line from a system crontab file.
    Lines starting with # or blank or variable assignments are skipped.
    Returns a job dict or None.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    # Variable assignments
    if "=" in line and not any(line.startswith(c) for c in "0123456789*@"):
        return None

    parts = line.split()
    if len(parts) < 6:
        return None

    # Try to parse: minute hour dom month dow user command
    # But some crontabs (root's) may not have a user field.
    # /etc/crontab and /etc/cron.d have the user field.
    # /var/spool/cron/crontabs/root does NOT have a user field.

    # Detect: if parts[5] looks like a cron field (digit/*), this is a no-user crontab
    p5 = parts[5]
    user = None
    cmd_start = 5

    if not (p5.isdigit() or p5 == "*" or "/" in p5 or "-" in p5 or "," in p5):
        # Has user field
        user = parts[5]
        cmd_start = 6

    expr = " ".join(parts[0:5])
    command = " ".join(parts[cmd_start:])

    valid_cron = True
    for f in parts[0:5]:
        if not any(c in "0123456789*-,/" for c in f):
            valid_cron = False
            break

    if not valid_cron:
        return None

    return {
        "id": None,
        "name": command[:80] + ("..." if len(command) > 80 else ""),
        "command": command,
        "schedule_display": expr,
        "schedule_desc": cron_to_human(expr),
        "next_run_at": None,
        "next_run_relative": None,
        "enabled": True,
        "source": "system",
        "source_path": source_path,
        "user": user,
    }


def _read_system_crontab(path, source_label, crons_out):
    """Read a single crontab file and append parsed entries to crons_out."""
    try:
        with open(path, "r") as f:
            for line in f:
                entry = _parse_system_cron_line(line, source_label, path)
                if entry:
                    # Compute next run
                    ts = cron_next_run(entry["schedule_display"])
                    if ts is not None:
                        entry["next_run_at"] = time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)
                        )
                        entry["next_run_relative"] = _relative_time(ts)
                    crons_out.append(entry)
    except Exception:
        pass  # File may not exist or be unreadable


def build_crons(errors_out):
    """
    Build the unified cron job list: Hermes jobs + system crontab jobs.
    Each entry has: id, name, command, schedule_display, schedule_desc,
    next_run_at, next_run_relative, enabled, source ('hermes'|'system'), source_path.
    Mutates errors_out.
    """
    crons = []

    # --- Hermes cron jobs ---
    cron_json = read_json(os.path.join(HERMES_HOME, "cron", "jobs.json"))
    hermes_jobs = []
    if cron_json is not None and "jobs" in cron_json:
        hermes_jobs = cron_json["jobs"]

    for job in hermes_jobs:
        expr = job.get("schedule_display", "")
        if not expr and "schedule" in job:
            expr = job["schedule"].get("expr", "")
        name = job.get("name", "unnamed")
        command = name
        if job.get("script"):
            command = job["script"]
        elif job.get("prompt"):
            command = job["prompt"][:80]

        entry = {
            "id": job.get("id"),
            "name": name,
            "command": command,
            "schedule_display": expr,
            "schedule_desc": cron_to_human(expr) if expr else "",
            "next_run_at": job.get("next_run_at"),
            "next_run_relative": None,
            "enabled": job.get("enabled", True),
            "source": "hermes",
            "source_path": os.path.join(HERMES_HOME, "cron", "jobs.json"),
            "user": None,
        }

        # Compute relative next run from the stored timestamp
        if entry["next_run_at"]:
            try:
                # Parse ISO timestamp
                import datetime as _dt
                ts_str = entry["next_run_at"]
                if ts_str.endswith("Z"):
                    ts_str = ts_str[:-1] + "+00:00"
                dt = _dt.datetime.fromisoformat(ts_str)
                ts = dt.timestamp()
                entry["next_run_relative"] = _relative_time(ts)
            except Exception:
                pass

        crons.append(entry)

    # --- System crontabs ---
    # /var/spool/cron/crontabs/root
    _read_system_crontab("/var/spool/cron/crontabs/root", "root crontab", crons)

    # /etc/crontab
    _read_system_crontab("/etc/crontab", "system crontab", crons)

    # /etc/cron.d/*
    try:
        cron_d_dir = "/etc/cron.d"
        for fname in sorted(os.listdir(cron_d_dir)):
            fpath = os.path.join(cron_d_dir, fname)
            if os.path.isfile(fpath) and not fname.startswith("."):
                _read_system_crontab(fpath, f"cron.d/{fname}", crons)
    except Exception as e:
        errors_out.append(f"reading /etc/cron.d: {e}")

    return crons

