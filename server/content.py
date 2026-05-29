"""Content file management."""

import os
from server.config import HERMES_HOME
# =============================================================================
# Content API helpers
# =============================================================================

CONTENT_DIR = os.path.join(HERMES_HOME, "content")


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

