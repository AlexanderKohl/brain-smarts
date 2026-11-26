"""GitHub access to a team secrets repository, through gh: the administrator's invitation and the
new member's acceptance. A private repository on a person's account or an organisation's works the
same way: access is a collaborator invitation with write permission, which the enrolment needs to
commit its request. Nothing here reads or sends a secret; gh holds its own sign-in."""
from __future__ import annotations

import re
from typing import Any, Callable

import child_process

_URL = re.compile(r"^https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$")


class GitHubError(RuntimeError):
    """gh could not do what was asked; the message names the step, never a token."""


def _gh(*args: str) -> Any:
    return child_process.run(["gh", *args], capture_output=True)


def _out(result: Any) -> str:
    return result.stdout.decode("utf-8", "replace").strip() if isinstance(result.stdout, bytes) else str(result.stdout).strip()


def repository_of(url: str) -> str:
    """owner/name of an https://github.com/owner/name(.git) URL."""
    found = _URL.match(url.strip())
    if not found:
        raise GitHubError(f"{url} is not a GitHub repository address (https://github.com/owner/name)")
    return f"{found.group(1)}/{found.group(2)}"


def login(gh: Callable[..., Any] = _gh) -> str:
    result = gh("api", "user", "--jq", ".login")
    name = _out(result) if result.returncode == 0 else ""
    if not name:
        raise GitHubError("GitHub sign-in through gh is needed first: run gh auth login")
    return name


def invite(repository: str, member: str, gh: Callable[..., Any] = _gh) -> None:
    """Invite member with write permission; nothing changes when they are a collaborator already."""
    result = gh("api", "-X", "PUT", f"repos/{repository}/collaborators/{member}", "-f", "permission=push")
    if result.returncode != 0:
        raise GitHubError(f"gh could not invite {member} to {repository}: check the GitHub username, and that "
                          "this account administers the repository")


def can_write(repository: str, gh: Callable[..., Any] = _gh) -> bool:
    result = gh("api", f"repos/{repository}", "--jq", ".permissions.push")
    return result.returncode == 0 and _out(result) == "true"


def accept(repository: str, gh: Callable[..., Any] = _gh) -> bool:
    """Accept a pending invitation to repository; False when none is pending."""
    listed = gh("api", "user/repository_invitations", "--jq", ".[] | [.id, .repository.full_name] | @tsv")
    if listed.returncode != 0:
        raise GitHubError("gh could not list this account's repository invitations")
    for line in _out(listed).splitlines():
        number, _tab, name = line.partition("\t")
        if name.lower() == repository.lower() and number.isdigit():
            if gh("api", "-X", "PATCH", f"user/repository_invitations/{number}").returncode != 0:
                raise GitHubError(f"gh could not accept the invitation to {repository}")
            return True
    return False
