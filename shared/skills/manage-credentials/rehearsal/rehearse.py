"""Rehearse the secrets store on this computer with throwaway secrets (follow-up plan, section R;
rehearsal plan RUN-20261121-131053).

  python shared/skills/manage-credentials/rehearsal/rehearse.py --check   the guard and every step that
                                                                           touches no keychain, process or cloud folder
  python shared/skills/manage-credentials/rehearsal/rehearse.py           the full rehearsal

Each step prints one line: the step, ok or FAILED, and what was checked; never a value. A guard
item that fails refuses the start and names the item. A failed step stops the run. The clean-up
always runs, says what it removed and names anything left. Exit codes: 0 all held, 1 a step
failed, 2 the guard refused, 3 something was left after the clean-up."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # --check leaves nothing beside the script

import argparse  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import secrets  # noqa: E402
import ssl  # noqa: E402
import subprocess  # noqa: E402
import tarfile  # noqa: E402
import time  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Callable, Iterable  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cleanup  # noqa: E402
import guard  # noqa: E402
import names  # noqa: E402
import tls  # noqa: E402
from wrapper import scrub  # noqa: E402

DASH = "–"  # en dash


class StepFailed(Exception):
    """A step's check did not hold; the message names what, never a value."""


class GuardRefused(Exception):
    def __init__(self, item: guard.Item) -> None:
        super().__init__(item.text)
        self.item = item


@dataclass
class Step:
    name: str
    action: Callable[[], str]


def _line(step: str, ok: bool, text: str, values: Iterable[str]) -> None:
    print(f"{step}: {'ok' if ok else 'FAILED'} {DASH} {scrub(text, values)}", flush=True)


def run(steps: list[Step], clean: Callable[[], cleanup.Report], secrets: Iterable[str] = ()) -> int:
    """Run steps in order until one fails; then the clean-up, always."""
    values, code = list(secrets), 0
    try:
        for step in steps:
            try:
                checked = step.action()
            except GuardRefused as refused:
                item = refused.item
                _line(step.name, False, f"refused to start: guard item {item.number} ({item.name}): {item.text}", values)
                code = 2
                break
            except Exception as error:  # noqa: BLE001 - reported by type and message, scrubbed
                text = str(error) if isinstance(error, StepFailed) else f"{type(error).__name__}: {error}"
                _line(step.name, False, text, values)
                code = 1
                break
            _line(step.name, True, checked, values)
    finally:
        report = clean()
        if report.left:
            _line("clean-up", False, "left: " + ", ".join(report.left), values)
            code = code or 3
        else:
            _line("clean-up", True, "; ".join(report.removed) or "nothing to remove", values)
    return code


def repository_root() -> Path:
    for candidate in [HERE, *HERE.parents]:
        if (candidate / "CONTRACT.md").is_file() and (candidate / ".git").exists():
            return candidate
    raise StepFailed("the mechanics repository holding this script was not found")


class SessionClient:
    """One wrapper.py session child: one JSON line per command each way."""

    def __init__(self, command: list[str], env: dict, seed: bytes, log: Path) -> None:
        log.parent.mkdir(parents=True, exist_ok=True)
        self._log = log.open("ab")
        self.proc = subprocess.Popen(command, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self._log, text=True, encoding="utf-8")
        self.proc.stdin.write(json.dumps({"seed": seed.hex()}) + "\n")
        self.proc.stdin.flush()

    def call(self, command: str, **payload: Any) -> dict:
        self.proc.stdin.write(json.dumps({"command": command, **payload}) + "\n")
        self.proc.stdin.flush()
        reply = self.proc.stdout.readline()
        if not reply:
            raise StepFailed(f"the session process ended during {command}")
        answer = json.loads(reply)
        if not answer.get("ok"):
            raise StepFailed(answer.get("checked") or command + " failed")
        return answer

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.stdin.close()
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self._log.close()


class Rehearsal:
    def __init__(self, check: bool, commit: str, environ: dict | None = None, logs: str | None = None) -> None:
        self.check, self.commit, self.logs = check, commit, logs
        self.base = dict(environ if environ is not None else os.environ)
        self.n = names.new_names(cloud_root=names.cloud_root_from(self.base))
        self.seed = secrets.token_bytes(32)
        self.processes: list[Any] = []
        self.sessions: dict[str, SessionClient] = {}
        self.agents: dict[str, Any] = {}
        self.server: tls.FakeTokenServer | None = None
        self.baseline: dict | None = None
        self.state: dict[str, Any] = {}

    # -- plumbing ---------------------------------------------------------------------------------
    def env(self, pc: str) -> dict:
        env = names.child_env(self.base, self.n, pc)
        env["REHEARSAL_USERS"] = json.dumps([self.n.keychain_user(p) for p in names.PCS])
        return env

    def wrapper(self, *args: str) -> list[str]:
        return [sys.executable, "-I", "-B", str(HERE / "wrapper.py"), *args]

    def probe(self, pc: str, full: bool) -> dict:
        done = subprocess.run(self.wrapper("probe", *(["--full"] if full else [])), env=self.env(pc),
                              capture_output=True, text=True, timeout=120)
        if done.returncode != 0:
            raise GuardRefused(guard.Item(0, "probe", False, "the guard's probe did not run in the rehearsal "
                                          f"environment (exit {done.returncode})"))
        return json.loads(done.stdout.strip().splitlines()[-1])

    def write_config(self, pc: str, enabled: bool = True) -> None:
        path = self.n.config_path(pc)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(names.config_for(self.n, pc, enabled), indent=2) + "\n", "utf-8")

    def session(self, pc: str, fresh: bool = False) -> SessionClient:
        if fresh:  # a second process, used once
            client = SessionClient(self.wrapper("session"), self.env(pc), self.seed,
                                   self.n.temp / pc / "logs" / "session.log")
            self.processes.append(client.proc)
            return client
        if pc not in self.sessions:
            self.sessions[pc] = self.session(pc, fresh=True)
        return self.sessions[pc]

    def once(self, pc: str, command: str, **payload: Any) -> dict:
        client = self.session(pc, fresh=True)
        try:
            return client.call(command, **payload)
        finally:
            client.close()

    def start_agent(self, pc: str, vault: Path | None = None) -> str:
        self.stop_agent(pc)
        log = (self.n.temp / pc / "logs" / "agent.log").open("ab")
        args = self.wrapper("serve", *(["--vault", str(vault)] if vault else []))
        proc = subprocess.Popen(args, env=self.env(pc), stdout=log, stderr=log, stdin=subprocess.DEVNULL)
        log.close()
        self.processes.append(proc)
        self.agents[pc] = proc
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise StepFailed(f"the {pc} agent ended at start (exit {proc.returncode}); see its log in the run folder")
            state = self.n.state_file(pc)
            if state.is_file() and json.loads(state.read_text("utf-8") or "{}").get("pid") == proc.pid:
                return f"{pc} agent started on pipe {self.n.pipe(pc)}; state file under the run's home"
            time.sleep(0.5)
        raise StepFailed(f"the {pc} agent wrote no state file within 30 seconds")

    def stop_agent(self, pc: str) -> None:
        proc = self.agents.pop(pc, None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=15)

    def recheck(self, pc: str) -> None:
        """Guard items 1 to 6 again before a step (keychain entries the run made are expected now)."""
        bad = guard.first_failure(guard.evaluate(self.probe(pc, False), self.n, pc, check_mode=True))
        if bad:
            raise GuardRefused(bad)

    # -- steps both modes run ---------------------------------------------------------------------
    def baseline_step(self) -> str:
        if self.n.temp.exists():
            raise GuardRefused(guard.Item(7, "owner baseline", False, "the run folder already exists"))
        try:
            self.baseline = guard.record_baseline(self.base)
        except OSError as error:
            raise GuardRefused(guard.baseline_item(None, type(error).__name__)) from None
        return guard.baseline_item(self.baseline).text

    def prepare_step(self) -> str:
        root = repository_root()
        archive = subprocess.run(["git", "-C", str(root), "archive", "--format=tar", self.commit, "CONTRACT.md", "shared"],
                                 capture_output=True, timeout=300)
        if archive.returncode != 0:
            raise StepFailed(f"git archive of {self.commit} failed")
        for pc in names.PCS:
            with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
                tar.extractall(self.n.brain(pc), filter="data")
            for folder in (self.n.local_app_data(pc), self.n.temp / pc / "logs"):
                folder.mkdir(parents=True, exist_ok=True)
            # The store asks git for a global user name; the run's home is its own, so it gets its own.
            (self.n.home(pc) / ".gitconfig").write_text(
                "[user]\n\tname = rehearsal\n\temail = rehearsal@example.com\n", "utf-8")
            self.write_config(pc)
        self.n.gh_empty.mkdir(parents=True, exist_ok=True)
        for kind in ("personal", "team"):
            done = subprocess.run(["git", "init", "--quiet", "--bare", "--initial-branch=main", str(self.n.remote(kind))],
                                  capture_output=True, timeout=60)
            if done.returncode != 0:
                raise StepFailed(f"git init --bare for the {kind} remote failed")
        if (self.n.brain("pc1") / "memory" / "OWNER.md").exists():
            raise StepFailed("a throwaway brain holds an owner profile")
        return (f"two throwaway brains exported from {self.commit} (CONTRACT.md and shared/ only), "
                "configs written, two local bare remotes")

    def certificate_step(self) -> str:
        cert, key = tls.make_certificate(self.n.tls_dir)
        if tls.certificate_hosts(cert) != [tls.LOOPBACK]:
            raise StepFailed("the run certificate is not for 127.0.0.1 alone")
        if not tls.memory_handshake(tls.trusted_context(cert), tls.server_context(cert, key)):
            raise StepFailed("the wrapper's context does not trust the run certificate")
        if tls.memory_handshake(ssl.create_default_context(), tls.server_context(cert, key)):
            raise StepFailed("the system trust store accepts the run certificate")
        return "certificate for 127.0.0.1 made in the run folder; trusted by the wrapper's context only"

    def guard_step(self, pc: str) -> str:
        probe = self.probe(pc, full=not self.check)
        items = guard.evaluate(probe, self.n, pc, check_mode=self.check)
        bad = guard.first_failure(items)
        if bad:
            raise GuardRefused(bad)
        if probe.get("token_trust") != 1:
            raise StepFailed("inside the wrapper the token endpoint does not trust the run certificate alone")
        return "wrapper trusts the run certificate alone; items 1-6 hold: " + "; ".join(f"{i.number} {i.text}" for i in items)

    # -- the full run -----------------------------------------------------------------------------
    def full_steps(self) -> list[Step]:
        s = self.state
        pc1 = lambda command, **kw: self.session("pc1").call(command, **kw)  # noqa: E731

        def guarded(name: str, pc: str, action: Callable[[], str]) -> Step:
            return Step(name, lambda: (self.recheck(pc), action())[1])

        def server() -> str:
            cert, key = self.n.ca_file, self.n.tls_dir / "key.pem"
            self.server = tls.FakeTokenServer(cert, key, self.seed).start()
            return "fake token endpoint on " + self.server.url

        def expect_token(reply: dict, label: str) -> str:
            if reply["data"].get("access_hash") != tls.token_hash(self.server.issued, self.seed):
                raise StepFailed(f"{label}: the stored access token is not the endpoint's latest")
            return label + "; the stored token's hash matches the endpoint's latest"

        def refresh(mode: str, expect: str, url: str | None = None) -> str:
            self.server.mode = mode
            calls = self.server.calls
            reply = pc1("refresh", url=url or self.server.url)
            outcome = reply["data"]["outcome"]
            if outcome != expect:
                raise StepFailed(f"the refresh ended {outcome}, expected {expect}")
            if expect == "answered":
                return expect_token(reply, "refresh answered and published")
            if expect == "needs_replace" and (self.server.calls != calls or not reply["data"]["names_replace"]):
                raise StepFailed("an uncertain sign-in called the endpoint again or did not name replace-signin")
            return f"refresh ended {outcome} as expected"

        def init() -> str:
            reply = pc1("init")
            s["fingerprint"] = reply["data"]["fingerprint"]
            return reply["checked"]

        def package(team: bool) -> str:
            reply = pc1("recovery_package", team=team)
            s["team_package" if team else "package"] = reply["data"]["package"]
            return reply["checked"]

        def enrol() -> str:
            rid = self.session("pc2").call("enrol_request", fingerprint=s["team_fingerprint"])["data"]["request"]
            if pc1("enrol_approve", request=rid)["data"]["state"] != "answered":
                raise StepFailed("the first enrol-approve did not answer the request")
            words = self.session("pc2").call("enrol_prove", request=rid)["data"]["words_hash"]
            if pc1("enrol_approve", request=rid, words_hash=words)["data"]["state"] != "enrolled":
                raise StepFailed("the second computer was not enrolled")
            return "pc2 enrolled in the team store; the words matched on both sides"

        def team_init() -> str:
            reply = pc1("team_init")
            s["team_fingerprint"] = reply["data"]["fingerprint"]
            return reply["checked"]

        def agent_on_old_vault() -> str:
            self.stop_agent("pc1")
            self.write_config("pc1", enabled=False)
            return self.start_agent("pc1", self.n.vault("pc1"))

        def store_switched_on() -> str:  # the vault agent keeps running: it was started with the store off
            self.write_config("pc1", enabled=True)
            return "store switched on with the vault-backed agent still running"

        def store_switched_off() -> str:
            self.write_config("pc1", enabled=False)
            return "store switched off for the vault-backed agent"

        def agent_on_store() -> str:
            self.stop_agent("pc1")
            self.write_config("pc1", enabled=True)
            return self.start_agent("pc1")

        vault = str(self.n.vault("pc1"))
        closed = f"https://{tls.LOOPBACK}:{tls.free_closed_port()}/token"
        return [
            Step("fake token endpoint", server),
            guarded("step 1 set-up", "pc1", init),
            guarded("step 2 put", "pc1", lambda: pc1("put_static")["checked"]),
            guarded("step 2 agent pc1", "pc1", lambda: self.start_agent("pc1")),
            guarded("step 2 read from a second process", "pc1",
                    lambda: self.once("pc1", "agent_read", entry="rehearsal-static", label="static")["checked"]),
            guarded("step 3 first sign-in", "pc1", lambda: expect_token(pc1("signin", url=self.server.url), "first grant")),
            guarded("step 3a answered", "pc1", lambda: refresh("token", "answered")),
            guarded("step 3b nothing sent", "pc1", lambda: refresh("token", "not_called", closed)),
            guarded("step 3b next refresh calls", "pc1", lambda: refresh("token", "answered")),
            guarded("step 3c refused", "pc1", lambda: refresh("refuse", "refused")),
            guarded("step 3c next refresh calls", "pc1", lambda: refresh("token", "answered")),
            guarded("step 3d time-out", "pc1", lambda: refresh("hang", "uncertain")),
            guarded("step 3d uncertain stays", "pc1", lambda: refresh("token", "needs_replace")),
            guarded("step 3e replace-signin", "pc1", lambda: pc1("replace_signin")["checked"]),
            guarded("step 3e new authorisation", "pc1",
                    lambda: expect_token(pc1("signin", url=self.server.url, create=False), "new authorisation")),
            guarded("step 3e refresh after", "pc1", lambda: refresh("token", "answered")),
            guarded("step 4 recovery package", "pc1", lambda: package(False)),
            guarded("step 5 restore", "pc1",
                    lambda: pc1("restore", package=s["package"], target_root=str(self.n.restore_dir))["checked"]),
            guarded("step 6 team store", "pc1", team_init),
            guarded("step 6 enrol pc2", "pc2", enrol),
            guarded("step 6 team put", "pc1", lambda: pc1("put_static", group="rehearsal")["checked"]),
            guarded("step 4 team recovery package", "pc1", lambda: package(True)),
            guarded("step 6 agent pc2", "pc2", lambda: self.start_agent("pc2")),
            guarded("step 6 pc2 reads the team secret", "pc2",
                    lambda: self.once("pc2", "agent_read", entry="rehearsal-team", label="team")["checked"]),
            guarded("step 6 pc2 get-check", "pc2", lambda: self.once("pc2", "get_check", group="rehearsal")["checked"]),
            guarded("step 7 store off for the old vault", "pc1", lambda: (self.stop_agent("pc1"), store_switched_off())[1]),
            guarded("step 7 old vault", "pc1", lambda: pc1("old_vault", path=vault)["checked"]),
            guarded("step 7 agent on the old vault", "pc1", agent_on_old_vault),
            guarded("step 7 unlock", "pc1", lambda: self.once("pc1", "unlock")["checked"]),
            guarded("step 7 store on", "pc1", store_switched_on),
            guarded("step 7 stale-agent refusals", "pc1", lambda: self.once("pc1", "stale_refusal")["checked"]),
            guarded("step 7 dry run", "pc1", lambda: self.once("pc1", "migrate", argv=["--dry-run"])["checked"]),
            guarded("step 7 migrate", "pc1", lambda: self.once(
                "pc1", "migrate", argv=["--backup-dir", str(self.n.temp / "pc1" / "backups")])["checked"]),
            guarded("step 7 marker written", "pc1", lambda: self.once("pc1", "marker", path=vault, present=True)["checked"]),
            guarded("step 7 agent on the store", "pc1", agent_on_store),
            guarded("step 7 store-on refusal", "pc1", lambda: self.once("pc1", "store_on_refusal")["checked"]),
            guarded("step 7 agent on the old vault again", "pc1", agent_on_old_vault),
            guarded("step 7 unlock again", "pc1", lambda: self.once("pc1", "unlock")["checked"]),
            guarded("step 7 store on again", "pc1", store_switched_on),
            guarded("step 7 rollback dry run", "pc1",
                    lambda: self.once("pc1", "migrate", argv=["rollback", "--dry-run"])["checked"]),
            guarded("step 7 rollback", "pc1", lambda: self.once("pc1", "migrate", argv=["rollback"])["checked"]),
            guarded("step 7 marker cleared", "pc1", lambda: self.once("pc1", "marker", path=vault, present=False)["checked"]),
            guarded("step 7 store off", "pc1", store_switched_off),
            guarded("step 7 static back", "pc1", lambda: self.once("pc1", "old_static_back", path=vault)["checked"]),
        ]

    def steps(self) -> list[Step]:
        first = [Step("guard item 7: owner baseline", self.baseline_step), Step("prepare", self.prepare_step),
                 Step("certificate", self.certificate_step),
                 Step("guard pc1", lambda: self.guard_step("pc1")), Step("guard pc2", lambda: self.guard_step("pc2"))]
        return first if self.check else first + self.full_steps()

    def clean(self) -> cleanup.Report:
        for client in self.sessions.values():
            client.close()
        if self.server is not None:
            self.server.stop()
        if self.logs:  # the children's logs, kept for reading after the run folder is gone
            for log in sorted(self.n.temp.glob("*/logs/*.log")):
                target = Path(self.logs) / f"{self.n.run_id}-{log.parent.parent.name}-{log.name}"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(log.read_bytes())
        report = cleanup.clean_up(self.n, check_mode=self.check, processes=self.processes)
        if self.baseline is not None:
            report.left += guard.compare_baseline(self.baseline, guard.record_baseline(self.base))
            report.removed.append("the owner's agent state, package folder and checkpoint folder unchanged"
                                  if not report.left else "")
        report.removed = [line for line in report.removed if line]
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="the guard and the steps that touch no keychain, "
                                                             "process or cloud folder")
    parser.add_argument("--commit", default="HEAD", help="the commit under test (default HEAD)")
    parser.add_argument("--logs", help="a folder that receives a copy of the child processes' logs before the "
                                       "clean-up (they may hold the run's invented values)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # the en dash in every line
    rehearsal = Rehearsal(args.check, args.commit, logs=args.logs)
    print(f"rehearsal {rehearsal.n.run_id}: {'check' if args.check else 'full run'} in {rehearsal.n.temp}", flush=True)
    return run(rehearsal.steps(), rehearsal.clean)


if __name__ == "__main__":
    raise SystemExit(main())
