"""The rehearsal-only wrapper (conductor's decision, plan section 1, option 2): every child process
of the rehearsal runs through it. It sets the Vault Agent's pipe name to the run's own and makes
the token endpoint trust only the run's certificate, then runs one command:

  python -I wrapper.py probe [--full]      the guard's view from inside the environment (JSON, no value)
  python -I wrapper.py serve [--vault P]   the Vault Agent, as vault_agent.py serve
  python -I wrapper.py session             step commands read as JSON lines on stdin (steps.py)

It refuses to run without a rehearsal pipe name. No product setting changes: the product code is
the copy in the throwaway brain named by REHEARSAL_SCRIPTS."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import types
from pathlib import Path
from typing import Any, Callable, Iterable

HERE = Path(__file__).resolve().parent
PREFIX = "PortableAIBrainVaultAgent-rehearsal-"


def install(runtime: Any, endpoint: Any, pipe: str | None, cafile: str | None,
            context_factory: Callable[[str], Any] | None = None) -> None:
    """Point the agent at the run's pipe and the token endpoint at the run's certificate only."""
    if not pipe or not str(pipe).startswith(PREFIX):
        raise SystemExit("rehearsal wrapper: no rehearsal pipe name; refusing to run")
    runtime.AGENT_NAME = pipe  # vault_agent_runtime.ipc_address reads it at call time
    if cafile:
        if context_factory is None:
            from tls import trusted_context as context_factory
        real = endpoint.ssl
        shim = types.ModuleType("ssl_rehearsal")
        shim.__dict__.update({k: getattr(real, k) for k in dir(real) if not k.startswith("__")})
        shim.create_default_context = lambda *a, **k: context_factory(cafile)
        endpoint.ssl = shim


def scrub(text: str, values: Iterable[str]) -> str:
    """text with every known invented value replaced; used on every line a child writes."""
    for value in values:
        if value:
            text = text.replace(value, "[hidden]")
    return text


def _prepare() -> None:
    scripts = os.environ.get("REHEARSAL_SCRIPTS")
    if not scripts or not Path(scripts, "vault_agent_runtime.py").is_file():
        raise SystemExit("rehearsal wrapper: REHEARSAL_SCRIPTS does not name the copied scripts")
    sys.path.insert(0, scripts)
    sys.path.insert(1, str(HERE))
    import token_endpoint
    import vault_agent_runtime
    install(vault_agent_runtime, token_endpoint, os.environ.get("REHEARSAL_PIPE_NAME"),
            os.environ.get("REHEARSAL_CA_FILE") if Path(os.environ.get("REHEARSAL_CA_FILE", "-")).is_file() else None)


def probe(full: bool) -> dict:
    """What guard items 1 to 6 judge. --check (full false) never reads a keychain entry."""
    import portable_vault
    import vault_agent_runtime
    from secret_store import keys, store_ops
    result: dict[str, Any] = {"root_vault": str(portable_vault.find_brain_root()),
                              "root_store": str(store_ops.find_brain_root())}
    try:
        config = store_ops.load_config()
        result["config"] = {k: (str(v) if isinstance(v, Path) else v) for k, v in config.items()
                            if k not in ("enabled", "recovery_package_cloud")}
    except Exception as error:  # noqa: BLE001 - reported by name, never a value
        result["config"] = {"error": type(error).__name__}
    result["vault_path"] = str(portable_vault.default_vault_path())
    result["env_vault"] = os.environ.get("PORTABLE_VAULT_PATH")
    result["runtime_base"] = str(vault_agent_runtime.runtime_base())
    result["ipc_address"] = str(vault_agent_runtime.ipc_address())
    import token_endpoint
    result["token_trust"] = len(token_endpoint.ssl.create_default_context().get_ca_certs())
    try:
        backend = keys._backend()
        result["backend"] = f"{type(backend).__module__}.{type(backend).__qualname__}"
    except Exception as error:  # noqa: BLE001
        backend, result["backend"] = None, f"unavailable ({type(error).__name__})"
    result["keychain"] = None
    users = json.loads(os.environ.get("REHEARSAL_USERS", "[]"))
    if full and backend is not None:
        result["keychain"] = {u: backend.get_password(keys.SERVICE, u) is not None for u in users}
    result["env_secret_names"] = sorted(k for k in ("PORTABLE_VAULT_PASSPHRASE", "GH_TOKEN", "GITHUB_TOKEN")
                                        if os.environ.get(k))
    try:
        result["gh_status"] = subprocess.run(["gh", "auth", "status"], capture_output=True, timeout=30).returncode
    except FileNotFoundError:
        result["gh_status"] = None
    except subprocess.TimeoutExpired:
        result["gh_status"] = 0  # unknown counts as signed in: refuse
    return result


def main(argv: list[str]) -> int:
    _prepare()
    command = argv[0] if argv else ""
    if command == "probe":
        print(json.dumps(probe("--full" in argv)))
        return 0
    if command == "serve":
        import vault_agent
        sys.argv = ["vault_agent.py", *argv[1:], "serve"]
        return vault_agent.main()
    if command == "session":
        import steps
        return steps.session(sys.stdin, sys.stdout)
    raise SystemExit("rehearsal wrapper: unknown command")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
