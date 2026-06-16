"""Editor helper — open files in $EDITOR and detect modifications."""
from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
from pathlib import Path


def _file_hash(path: Path) -> str:
    """Return a stable hash of the file contents."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def open_in_editor(path: Path) -> bool:
    """Open ``path`` in the user's ``$EDITOR``.

    Returns True if the file contents changed during the edit session,
    indicating the user likely saved changes.
    """
    editor = os.environ.get("EDITOR", "vi")
    try:
        cmd = shlex.split(editor)
    except ValueError:
        cmd = [editor]
    cmd.append(str(path))

    original_hash = _file_hash(path) if path.exists() else ""
    try:
        subprocess.run(cmd, check=False)
    except FileNotFoundError:
        print(f"Editor not found: {editor!r}. Set the EDITOR environment variable.")
        return False
    new_hash = _file_hash(path) if path.exists() else ""

    if not original_hash:
        return bool(new_hash)
    return new_hash != original_hash
