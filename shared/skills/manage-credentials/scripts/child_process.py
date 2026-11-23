"""Start the children the skill itself needs (git, gh) without a console window (plan R23, rule 1).

The tray runs under pythonw, which has no console; Windows gives every console program it starts a
new console window of its own unless the child is created with CREATE_NO_WINDOW. run and popen call
subprocess.run and subprocess.Popen with the caller's creationflags combined with NO_WINDOW and change
nothing else: a child started from a console behaves as before. Standard library only; no credential
passes through this module. A command the person named (vaultctl.py run, vault_credentials.py run and
session) is not started here: it keeps its console."""
from __future__ import annotations

import subprocess
import sys
from typing import Any

NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _flags(options: dict[str, Any]) -> dict[str, Any]:
    return {**options, "creationflags": options.get("creationflags", 0) | NO_WINDOW}


def run(command: Any, **options: Any) -> subprocess.CompletedProcess:
    """subprocess.run, with NO_WINDOW added to creationflags."""
    return subprocess.run(command, **_flags(options))


def popen(command: Any, **options: Any) -> subprocess.Popen:
    """subprocess.Popen, with NO_WINDOW added to creationflags."""
    return subprocess.Popen(command, **_flags(options))
