"""Plan R24: the guard every test file of this folder imports first, before anything else:

    import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)

On import, two things, in this order:

1. The guard. When the brain the code under test would use (found as portable_vault.find_brain_root
   finds it from scripts/) holds a secrets-store configuration, the whole test process stops before
   any test runs, with one message. Only the file's existence counts: it is never opened or parsed,
   so "enabled": false and an unreadable file refuse as well, and a path that cannot be checked
   refuses too. No keychain, clone, agent or code under test is touched: this module imports only
   the standard library and the two harness files beside it.
2. The barriers. In a process run_all.py started they are already in the environment, and only the
   pipe name is installed in this process (hermetic_site/sitecustomize.py, which Python loaded at
   start-up). In a process started some other way (python -m unittest in a checkout without the
   file) this module makes a container of its own, puts the same barriers into os.environ, so every
   child inherits them, and removes the container when the process ends.

tests/test_hermetic.py fails when a test file does not import this module first.
"""

from __future__ import annotations

import atexit
import importlib.util
import os
import secrets
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
CONFIG_RELATIVE = Path("memory") / "skills" / "manage-credentials" / "config" / "secret-store.json"
REFUSED_EXIT = 3
REFUSAL = ("hermetic: this checkout holds a live secrets-store configuration ({path}); run the folder with "
           "tests/run_all.py, which runs it from a throwaway copy")


def brain_root() -> Path:
    """The brain portable_vault.find_brain_root finds from scripts/portable_vault.py (store_ops walks
    the same folders), including its fallback for a copy outside any brain."""
    here = (SCRIPTS / "portable_vault.py").resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "CONTRACT.md").is_file():
            return candidate
    return here.parents[4]


def live_configuration(root: Path | None = None) -> Path | None:
    """The configuration path when something is there, or when that cannot be told; None only when
    it is certainly absent. The file is never opened."""
    path = Path(root or brain_root()) / CONFIG_RELATIVE
    try:
        os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError:
        return path  # cannot tell: refuse
    return path


def refuse_if_live() -> None:
    path = live_configuration()
    if path is None:
        return
    sys.stdout.flush()
    sys.stderr.write(REFUSAL.format(path=path) + "\n")
    sys.stderr.flush()
    os._exit(REFUSED_EXIT)  # no test of this process runs, whichever loader imported the file


def _load(name: str, path: Path):
    """A harness file beside this one, by its path (the test folder need not be on sys.path)."""
    if name in sys.modules and Path(getattr(sys.modules[name], "__file__", "") or "").resolve() == path:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(f"hermetic_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up while the file runs
    spec.loader.exec_module(module)
    return module


def _own_container() -> None:
    """The barriers of run_all.py for a process it did not start, in a container of this process."""
    run_all = _load("run_all", HERE / "run_all.py")
    container = Path(tempfile.mkdtemp(prefix="brain-test-"))
    atexit.register(run_all.remove_container, container)
    run_all.prepare_container(container)
    environment = run_all.barrier_environment(container, run_all.new_pipe_name(secrets.token_hex(4), os.getpid()),
                                              os.environ)
    for key in [k for k in os.environ if k not in environment]:
        del os.environ[key]
    os.environ.update(environment)
    tempfile.tempdir = None  # the next temporary folder is made in the container


def enter() -> None:
    refuse_if_live()
    if not os.environ.get("BRAIN_TEST_CONTAINER"):
        _own_container()
    _load("sitecustomize", HERE / "hermetic_site" / "sitecustomize.py").install(os.environ["BRAIN_TEST_PIPE_NAME"])


enter()
