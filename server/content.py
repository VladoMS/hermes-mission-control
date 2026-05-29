"""Content file management — agent content + knowledge vault."""

import os
from server.config import HERMES_HOME
# =============================================================================
# Paths
# =============================================================================

CONTENT_DIR = os.path.join(HERMES_HOME, "content")

def _resolve_vault_dir():
    """Resolve vault path: env var → .env file → default."""
    path = os.getenv("OBSIDIAN_VAULT_PATH")
    if path and os.path.isdir(path):
        return path
    # Try reading from hermes .env
    env_file = os.path.join(HERMES_HOME, ".env")
    try:
        with open(env_file) as f:
            for line in f:
                if line.startswith("OBSIDIAN_VAULT_PATH="):
                    path = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                    if path and os.path.isdir(path):
                        return path
    except Exception:
        pass
    return "/home/hermes/vault"

VAULT_DIR = _resolve_vault_dir()
VAULT_SKIP_DIRS = {".git", ".obsidian", "scripts", "__pycache__"}

# =============================================================================
# Agent content helpers
# =============================================================================


def _validate_content_path(rel_path):
    """Resolve a relative path against CONTENT_DIR. Reject traversal attempts.
    Returns (absolute_path, error_string). One will be None."""
    if not rel_path or ".." in rel_path or rel_path.startswith("/"):
        return None, "invalid path"
    abs_path = os.path.normpath(os.path.join(CONTENT_DIR, rel_path))
    if not abs_path.startswith(os.path.normpath(CONTENT_DIR) + os.sep) and abs_path != os.path.normpath(CONTENT_DIR):
        return None, "path traversal rejected"
    if not abs_path.endswith(".md"):
        return None, "not a markdown file"
    if not os.path.isfile(abs_path):
        return None, "file not found"
    return abs_path, None


def list_content():
    """Walk ~/.hermes/content/ and return list of .md file metadata.
    Returns list of {agent, filename, rel_path, title, modified_at, size}."""
    docs = []
    if not os.path.isdir(CONTENT_DIR):
        return docs

    try:
        for profile in sorted(os.listdir(CONTENT_DIR)):
            prof_dir = os.path.join(CONTENT_DIR, profile)
            if not os.path.isdir(prof_dir):
                continue
            try:
                for fname in sorted(os.listdir(prof_dir)):
                    if not fname.endswith(".md"):
                        continue
                    fpath = os.path.join(prof_dir, fname)
                    rel = os.path.join(profile, fname)
                    try:
                        st = os.stat(fpath)
                        title = fname
                        # Extract first H1 as title
                        try:
                            with open(fpath, "r") as f:
                                for line in f:
                                    stripped = line.strip()
                                    if stripped.startswith("# ") and not stripped.startswith("## "):
                                        title = stripped[2:].strip()
                                        break
                        except Exception:
                            pass
                        docs.append({
                            "agent": profile,
                            "filename": fname,
                            "rel_path": rel,
                            "abs_path": fpath,
                            "title": title,
                            "modified_at": st.st_mtime,
                            "size": st.st_size,
                        })
                    except OSError:
                        pass
            except OSError:
                pass
    except OSError:
        pass

    return docs


def read_content(rel_path):
    """Read raw markdown content. Returns (content, abs_path, error)."""
    abs_path, err = _validate_content_path(rel_path)
    if err:
        return None, None, err
    try:
        with open(abs_path, "r") as f:
            return f.read(), abs_path, None
    except Exception as e:
        return None, None, f"read error: {e}"


def save_content(rel_path, content):
    """Write markdown content back. Returns (True, None) or (False, error)."""
    abs_path, err = _validate_content_path(rel_path)
    if err:
        return False, err
    try:
        with open(abs_path, "w") as f:
            f.write(content)
        return True, None
    except Exception as e:
        return False, f"write error: {e}"

# =============================================================================
# Knowledge vault helpers
# =============================================================================

def _extract_title_vault(fpath):
    """Extract first H1 from a vault markdown file as title. Falls back to filename."""
    try:
        with open(fpath, "r") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("# ") and not stripped.startswith("## "):
                    return stripped[2:].strip()
    except Exception:
        pass
    return None


def _is_vault_md(fname):
    """Check if a filename is a markdown file in the vault."""
    return fname.endswith(".md") and not fname.startswith(".")


def list_vault():
    """Walk the knowledge vault and return .md file metadata.
    Returns list of {source, section, filename, rel_path, abs_path, title, modified_at, size}.
    'section' is the top-level directory (1-projects, 2-areas, etc.).
    """
    docs = []
    if not os.path.isdir(VAULT_DIR):
        return docs

    try:
        for entry in sorted(os.listdir(VAULT_DIR)):
            entry_path = os.path.join(VAULT_DIR, entry)
            if not os.path.isdir(entry_path) or entry in VAULT_SKIP_DIRS or entry.startswith("."):
                continue
            section = entry
            try:
                for root, dirs, files in os.walk(entry_path):
                    # Skip hidden dirs and vault infra
                    dirs[:] = [d for d in dirs if not d.startswith(".") and d not in VAULT_SKIP_DIRS]
                    for fname in sorted(files):
                        if not _is_vault_md(fname):
                            continue
                        fpath = os.path.join(root, fname)
                        rel = os.path.relpath(fpath, VAULT_DIR)
                        try:
                            st = os.stat(fpath)
                            title = _extract_title_vault(fpath) or fname
                            docs.append({
                                "source": "vault",
                                "section": section,
                                "filename": fname,
                                "rel_path": rel,
                                "abs_path": fpath,
                                "title": title,
                                "modified_at": st.st_mtime,
                                "size": st.st_size,
                            })
                        except OSError:
                            pass
            except OSError:
                pass
    except OSError:
        pass

    return docs


def read_vault(rel_path):
    """Read raw markdown from vault. Returns (content, abs_path, error)."""
    if not rel_path or ".." in rel_path or rel_path.startswith("/"):
        return None, None, "invalid path"
    abs_path = os.path.normpath(os.path.join(VAULT_DIR, rel_path))
    if not abs_path.startswith(os.path.normpath(VAULT_DIR) + os.sep) and abs_path != os.path.normpath(VAULT_DIR):
        return None, None, "path traversal rejected"
    if not abs_path.endswith(".md"):
        return None, None, "not a markdown file"
    if not os.path.isfile(abs_path):
        return None, None, "file not found"
    try:
        with open(abs_path, "r") as f:
            return f.read(), abs_path, None
    except Exception as e:
        return None, None, f"read error: {e}"

