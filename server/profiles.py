"""Profile builder."""

import os
from server.config import HERMES_HOME
from server.readers import read_profile_yaml, read_config_yaml, get_state_db_stats
# =============================================================================
# Profile builder
# =============================================================================

def build_profiles(errors_out):
    """Build profile list: default + named profiles under ~/.hermes/profiles/. Mutates errors_out."""
    profiles = []

    # --- Default profile (root ~/.hermes/) ---
    pdata = {
        "name": "default",
        "description": "Primary Hermes agent profile",
        "model": "",
        "provider": "",
        "skills": {},
        "state_db_stats": None,
        "has_state_db": False,
    }

    # Root skills
    root_skills = read_json(os.path.join(HERMES_HOME, "skills", ".usage.json"))
    if root_skills is not None:
        pdata["skills"] = root_skills

    # Root state.db
    root_state = os.path.join(HERMES_HOME, "state.db")
    if os.path.exists(root_state):
        pdata["has_state_db"] = True
        stats = get_state_db_stats(root_state)
        if stats is not None:
            pdata["state_db_stats"] = stats
        else:
            errors_out.append("default state.db: stats query failed")

    profiles.append(pdata)

    # --- Named profiles ---
    profiles_dir = os.path.join(HERMES_HOME, "profiles")
    try:
        names = sorted(os.listdir(profiles_dir))
    except Exception as e:
        errors_out.append(f"profiles directory not readable: {e}")
        names = []

    for name in names:
        prof_dir = os.path.join(profiles_dir, name)
        if not os.path.isdir(prof_dir):
            continue

        pdata = {
            "name": name,
            "description": "",
            "description_auto": "false",
            "model": "",
            "provider": "",
            "skills": {},
            "state_db_stats": None,
            "has_state_db": False,
        }

        # profile.yaml
        try:
            pyaml_path = os.path.join(prof_dir, "profile.yaml")
            if os.path.isfile(pyaml_path):
                pyaml = read_profile_yaml(pyaml_path)
                pdata["description"] = pyaml.get("description", "")
                pdata["description_auto"] = pyaml.get("description_auto", "false")
        except Exception:
            pass

        # config.yaml → model/provider
        try:
            cfg_path = os.path.join(prof_dir, "config.yaml")
            if os.path.isfile(cfg_path):
                cfg = read_config_yaml(cfg_path)
                pdata["model"] = cfg.get("model", "")
                pdata["provider"] = cfg.get("provider", "")
        except Exception:
            pass

        # skills/.usage.json
        try:
            skills_path = os.path.join(prof_dir, "skills", ".usage.json")
            if os.path.isfile(skills_path):
                skills = read_json(skills_path)
                if skills is not None:
                    pdata["skills"] = skills
        except Exception:
            pass

        # state.db
        try:
            state_path = os.path.join(prof_dir, "state.db")
            if os.path.isfile(state_path):
                pdata["has_state_db"] = True
                stats = get_state_db_stats(state_path)
                if stats is not None:
                    pdata["state_db_stats"] = stats
                else:
                    errors_out.append(f"{name} state.db: stats query failed")
        except Exception:
            pass

        profiles.append(pdata)

    return profiles

