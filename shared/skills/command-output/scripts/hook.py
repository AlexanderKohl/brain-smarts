"""After-command hook: shortens a shell command's long output before the agent reads it.

  python shared/skills/command-output/scripts/hook.py <host>
  python shared/skills/command-output/scripts/hook.py settings <host>   the entry for the host's user settings

<host> is one of claude-code, codex, copilot-cli, gemini-cli. The host pipes its hook input (JSON)
on stdin after a shell command has run; this script answers in that host's own shape with the
shortened output, or prints nothing, which leaves the output exactly as it was. The command itself
is never changed, so its exit code, its permissions and the host's approval prompts are untouched.

It fails open: any error leaves the output unchanged and is appended to errors.log beside the saved
outputs. Each host's registration is in the skill's SKILL.md, section Hosts.

Standard library only.
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import filtering  # noqa: E402

RAN_NOTE = "[command-output: the command ran normally; its long output is shortened below]"


def _text(value) -> str:
    """A tool result as text: a string as it is, a list of parts by their text, anything else empty."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in value)
    return ""


def _exit_code(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def claude_code(payload: dict) -> dict | None:
    """PostToolUse for the Bash and PowerShell tools: updatedToolOutput replaces the result, in the
    tool's own response shape (stdout, stderr, interrupted, isImage, noOutputExpected).

    Observed with Claude Code 2.1.288 (7 October 2026): PostToolUse fires only for a command that
    succeeded, so a failure always reaches the model in full with its exit code; the response
    carries no exit code; and output too long for Claude Code is saved by Claude Code itself
    (persistedOutputPath) and shown as a short preview, which a replacement does not change, so
    such output is left to Claude Code."""
    if payload.get("tool_name") not in ("Bash", "PowerShell"):
        return None
    tool_input = payload.get("tool_input") or {}
    response = payload.get("tool_response")
    if tool_input.get("run_in_background"):
        return None
    command = str(tool_input.get("command") or "")
    cwd = payload.get("cwd")
    if isinstance(response, str):
        short = filtering.shrink(command, response, None, cwd=cwd, host="claude-code")
        updated = short
    elif isinstance(response, dict):
        if response.get("interrupted") or response.get("persistedOutputPath"):
            return None
        code = _exit_code(response.get("exit_code", response.get("exitCode")))
        updated = dict(response)
        changed = False
        for stream in ("stdout", "stderr"):
            text = response.get(stream)
            if isinstance(text, str):
                short = filtering.shrink(command, text, code, cwd=cwd, host="claude-code")
                if short is not None:
                    updated[stream] = short
                    changed = True
        if not changed:
            updated = None
    else:
        updated = None
    if updated is None:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": updated}}


def codex(payload: dict) -> dict | None:
    """PostToolUse for the shell tool: decision "block" with a reason replaces the result the model
    sees with the reason."""
    if payload.get("tool_name") not in ("Bash", "shell", "local_shell"):
        return None
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command")
    command = " ".join(command) if isinstance(command, list) else str(command or "")
    response = payload.get("tool_response")
    if isinstance(response, dict):
        text, code = _text(response.get("output")), _exit_code(response.get("exit_code"))
    else:
        text, code = _text(response), None
    short = filtering.shrink(command, text, code, cwd=payload.get("cwd"), host="codex")
    return None if short is None else {"decision": "block", "reason": f"{RAN_NOTE}\n{short}"}


def gemini_cli(payload: dict) -> dict | None:
    """AfterTool for run_shell_command: decision "deny" with a reason replaces the result sent back to
    the model with the reason."""
    if payload.get("tool_name") != "run_shell_command":
        return None
    command = str((payload.get("tool_input") or {}).get("command") or "")
    response = payload.get("tool_response") or {}
    text = _text(response.get("llmContent")) if isinstance(response, dict) else _text(response)
    short = filtering.shrink(command, text, None, cwd=payload.get("cwd"), host="gemini-cli")
    return None if short is None else {"decision": "deny", "reason": f"{RAN_NOTE}\n{short}"}


def copilot_cli(payload: dict) -> dict | None:
    """postToolUse for the bash and powershell tools: modifiedResult replaces the result."""
    if str(payload.get("toolName") or "").lower() not in ("bash", "powershell", "shell"):
        return None
    args = payload.get("toolArgs")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {"command": args}
    command = str((args or {}).get("command") or "") if isinstance(args, dict) else ""
    result = payload.get("toolResult") or {}
    if not isinstance(result, dict):
        return None
    short = filtering.shrink(command, _text(result.get("textResultForLlm")), None,
                             cwd=payload.get("cwd"), host="copilot-cli")
    if short is None:
        return None
    return {"modifiedResult": {"resultType": result.get("resultType", "success"), "textResultForLlm": short}}


HOSTS = {"claude-code": claude_code, "codex": codex, "copilot-cli": copilot_cli, "gemini-cli": gemini_cli}


def script_path() -> str:
    """This script in the owner's shared checkout (`brain_root` in /memory/OWNER.md), so a host setting
    survives the removal of the session copy it was printed from; this file's own path otherwise."""
    root = filtering.brain_root()
    try:
        lines = (root / "memory" / "OWNER.md").read_text(encoding="utf-8").splitlines() if root else []
    except OSError:
        lines = []
    for line in lines[1:] if lines and lines[0].strip() == "---" else []:
        if line.strip() == "---":
            break
        key, _sep, value = line.partition(":")
        if key.strip() == "brain_root" and value.strip():
            shared = Path(value.strip().strip("'\"")) / "shared" / "skills" / "command-output" / "scripts" / "hook.py"
            return shared.as_posix()
    return Path(__file__).resolve().as_posix()


def settings(host: str) -> str:
    """The entry that registers this hook in the host's user settings, for the owner to add."""
    command = f"python {script_path()} {host}"
    if host == "claude-code":
        entry = {"hooks": {"PostToolUse": [{"matcher": "Bash|PowerShell",
                                            "hooks": [{"type": "command", "command": command}]}]}}
        return "Merge into ~/.claude/settings.json:\n" + json.dumps(entry, indent=2)
    if host == "codex":
        return ("Add to ~/.codex/config.toml (and [features] hooks = true if the running version needs it):\n"
                f'[[hooks.PostToolUse]]\nmatcher = "^Bash$"\n[[hooks.PostToolUse.hooks]]\n'
                f'type = "command"\ncommand = "{command}"\ntimeout = 30')
    if host == "copilot-cli":
        entry = {"version": 1, "hooks": {"postToolUse": [{"type": "command", "bash": command, "powershell": command}]}}
        return "Write to ~/.copilot/hooks/command-output.json:\n" + json.dumps(entry, indent=2)
    entry = {"hooks": {"AfterTool": [{"matcher": "run_shell_command",
                                      "hooks": [{"type": "command", "command": command}]}]}}
    return "Merge into ~/.gemini/settings.json:\n" + json.dumps(entry, indent=2)


def log_error(host: str) -> None:
    try:
        folder = filtering.output_folder()
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        with (folder / "errors.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {host}\n{traceback.format_exc()}\n")
    except OSError:
        pass


def main(argv: list[str], stdin=None, stdout=None) -> int:
    stdin = sys.stdin.buffer if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    if argv[:1] == ["settings"] and len(argv) == 2 and argv[1] in HOSTS:
        stdout.write(settings(argv[1]) + "\n")
        return 0
    host = argv[0] if argv else ""
    if host not in HOSTS:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        raw = stdin.read()
        payload = json.loads(raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw)
        reply = HOSTS[host](payload) if isinstance(payload, dict) else None
    except Exception:  # fail open: the host keeps the original output
        log_error(host)
        return 0
    if reply is not None:
        stdout.write(json.dumps(reply, ensure_ascii=True))
        stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
