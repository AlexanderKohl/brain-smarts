"""Loaded by Python itself at the start of every process of a credential test run: run_all.py and
tests/hermetic.py put this folder, alone, on PYTHONPATH, so each test process and every Python child
it starts loads it (plan R24). It gives the Vault Agent the run's test-only pipe name the way the
rehearsal's wrapper does (rehearsal/wrapper.py, install): vault_agent_runtime.AGENT_NAME, which
ipc_address reads at call time, is set as the module is executed. Nothing in scripts/ changes and
no process of the run can address the pipe of an agent that runs outside it.

Standard library only; it reads one environment variable and never a credential. A child started
with python -I or -E does not load it: tests/test_hermetic.py shows the children the tests start."""

from __future__ import annotations

import os
import sys

PIPE_VARIABLE = "BRAIN_TEST_PIPE_NAME"
PIPE_PREFIX = "PortableAIBrainVaultAgent-test-"
MODULE = "vault_agent_runtime"


class PipeNameFinder:
    """A meta-path finder that wraps the loader of vault_agent_runtime: the module runs as written,
    then its AGENT_NAME becomes the test pipe name."""

    brain_test_pipe = True  # how install() finds a finder put in by an earlier copy of this module

    def __init__(self, pipe: str) -> None:
        self.pipe = pipe

    def find_spec(self, name, path=None, target=None):
        if name != MODULE:
            return None
        spec = None
        for finder in sys.meta_path:
            if getattr(finder, "brain_test_pipe", False):
                continue
            find = getattr(finder, "find_spec", None)
            spec = find(name, path, target) if find is not None else None
            if spec is not None:
                break
        if spec is None or spec.loader is None or not hasattr(spec.loader, "exec_module"):
            return spec
        run, pipe = spec.loader.exec_module, self.pipe

        def exec_module(module):
            run(module)
            module.AGENT_NAME = pipe

        spec.loader.exec_module = exec_module
        return spec

    def invalidate_caches(self) -> None:
        pass


def install(pipe: str) -> None:
    """Put the finder first (once) and name the pipe of a vault_agent_runtime already imported."""
    if not pipe.startswith(PIPE_PREFIX):
        raise SystemExit(f"hermetic: {PIPE_VARIABLE} is not a test pipe name; refusing to run")
    for finder in sys.meta_path:
        if getattr(finder, "brain_test_pipe", False):
            finder.pipe = pipe
            break
    else:
        sys.meta_path.insert(0, PipeNameFinder(pipe))
    module = sys.modules.get(MODULE)
    if module is not None:
        module.AGENT_NAME = pipe


if os.environ.get(PIPE_VARIABLE):
    install(os.environ[PIPE_VARIABLE])
