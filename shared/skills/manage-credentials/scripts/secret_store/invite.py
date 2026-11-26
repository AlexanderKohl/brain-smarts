"""Both ends of a team enrolment, waited for, so that nobody copies a request id between computers.

invite_member (an administrator's computer) waits for a request from one login, answers it, shows
the six words for comparison with the words the new member sends by hand, enrols the computer and
admits the person to their first groups. join_team (the new member's computer) writes the request,
waits for the answer, shows the six words to send, and waits until the computer is enrolled and the
person admitted.

The two computers meet only through the team repository, by the store's own verified pull
(store.open). Every write is one the enrolment protocol (enrol.py) and the administrator
transactions (team.py) already make; this module adds the waiting and the choice of request, and no
write of its own. The fingerprint and the six words are not secrets: the fingerprint names the
team's trust root, and the words only show that nobody stood between the two computers. Neither is
printed here: the fingerprint is printed by the command, the words appear in a local window only."""

from __future__ import annotations

import time
from typing import Any, Callable

from . import canonical, enrol
from . import team as team_ops
from .errors import SecretStoreError
from .policy import object_hash

POLL = 5.0  # seconds between pulls while waiting for the other computer
WAIT = 2 * 60 * 60  # how long either end waits in all before it gives up

SEND_WORDS = ("Send these six words to the administrator who invited you (a message is fine: they are "
              "not a secret). Their computer shows the same six words and asks them to compare.")
CHECK_WORDS = ("Compare these six words with the six words of the new computer (sent to you, or on its own "
               "screen). Press \"They match\" only when all six are the same, in the same order.")
OWN_WORDS = ("Your other computer shows six words too, in its own window. They must be the same, in the same "
             "order; press \"They match\" there. Press Done here.")


def _show(intro: str, compare: bool) -> Callable[[str, list[str]], bool]:
    def show(title: str, words: list[str]) -> bool:
        from secret_window import show_words  # the scripts folder is on sys.path for the commands
        return show_words(title, words, intro, compare)
    return show


def _request_path(store, rid: str, part: str = "") -> Any:
    return store.clone / "requests" / f"{rid}{part}.json"


def _read(store, rid: str, part: str = "") -> Any:
    path = _request_path(store, rid, part)
    try:
        return canonical.loads(path.read_bytes()) if path.exists() else None
    except (OSError, ValueError):
        return None


def open_request(store, login: str, now: float) -> tuple[str, str] | None:
    """The newest request from login that is well formed, unexpired and not yet answered: its id and
    the hash of the request as checked here, which the answer and the approval are then bound to."""
    folder = store.clone / "requests"
    found = []
    for path in folder.glob("*.json") if folder.is_dir() else []:
        rid = path.name[:-len(".json")]
        if not enrol._ID.fullmatch(rid) or _request_path(store, rid, ".answer").exists():
            continue  # an answer or proof file, or a request already answered
        request = _read(store, rid)
        if not isinstance(request, dict) or request.get("login") != login:
            continue
        try:
            enrol.check_request(request, store.policy.repository, now)
        except SecretStoreError:
            continue
        found.append((request["expires"], rid, object_hash(request)))
    return max(found)[1:] if found else None


def groups_of(store, login: str) -> list[str]:
    return sorted(name for name, members in store.policy.doc["groups"].items() if login in members)


def check_can_invite(store, groups: list[str]) -> None:
    """Before anyone waits: this computer is an administrator's and every group exists."""
    team_ops._require_admin(store)
    team_ops._check_groups(store.policy.doc, groups)


def invite_member(store, login: str, groups: list[str], display: Callable | None = None, *,
                  say: Callable[[str], None] = print, poll: float = POLL, wait: float = WAIT,
                  clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep) -> str:
    """Administrator: wait for login's request, answer it, compare words, enrol, admit. Returns the
    computer that was enrolled. A request that expires or ends on mismatches is let go, and the next
    request from the same login is taken up."""
    display = display or _show(CHECK_WORDS, True)
    store.open()
    check_can_invite(store, groups)
    unadmitted = sorted(store.policy.doc["people"].get(login, {}).get("computers", {}))
    if unadmitted and not groups_of(store, login):  # an earlier run stopped between enrolment and admission
        say(f"{login} has an enrolled computer but no group yet; admitting them now.")
        _admit(store, login, groups, say)
        return unadmitted[0]
    deadline, rid = clock() + wait, None
    while True:
        now = clock()
        if rid is None:
            chosen = open_request(store, login, now)
            if chosen is not None:
                rid, chosen = chosen
                enrol.answer(store, rid, now)
                if (enrol._load_pending(store, rid) or {}).get("request") != chosen:
                    # The request changed between choosing it and answering it (answer pulls again):
                    # the answer may belong to someone else's request, so this attempt is let go.
                    enrol._end(store, rid)
                    say("The request changed while it was being answered; waiting for a new one.")
                    rid = None
                else:
                    say(f"Enrolment request from {login} answered; waiting for their computer to answer back.")
        else:
            request = _read(store, rid)
            if request is None or now > request["expires"]:
                enrol._end(store, rid)
                say("That enrolment request expired before it finished; waiting for a new one (it will show new words).")
                rid = None
            elif _request_path(store, rid, ".proof").exists():
                say(f"The words window is open: compare it with the six words {login} sends you.")
                try:
                    enrol.approve(store, rid, display, clock=clock)
                except SecretStoreError as error:
                    say(f"Not enrolled: {error}.")
                    if enrol._load_pending(store, rid) is None:  # the attempt has ended
                        say(f"Waiting for a new request from {login}.")
                        rid = None
                else:
                    computer = request["computer"]
                    say(f"{login}/{computer} is enrolled.")
                    _admit(store, login, groups, say)
                    return computer
        if now > deadline:
            raise SecretStoreError(f"no enrolment from {login} finished within {int(wait // 60)} minutes; "
                                   "run the invitation again")
        sleep(poll)
        store.open()


def _admit(store, login: str, groups: list[str], say: Callable[[str], None]) -> None:
    held = groups_of(store, login)
    if held:  # a second computer of a member: their groups stay as they are
        say(f"{login} is already in {', '.join(held)}; their groups are unchanged.")
        return
    team_ops.admit(store, login, groups)
    say(f"Admitted {login} to {', '.join(groups)}.")


def join_team(store, fingerprint: str | None, display: Callable | None = None, *,
              say: Callable[[str], None] = print, poll: float = POLL, wait: float = WAIT,
              clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep) -> list[str]:
    """New member: request enrolment (pinning the trust root by fingerprint at the first open), show
    the six words once the administrator has answered, and wait until this computer is enrolled and
    its person admitted. A request that expires or ends is replaced by a new one. Returns the groups."""
    display = display or _show(SEND_WORDS, False)
    me = (store.config["person"], store.config["computer"])
    deadline = clock() + wait
    while not _enrolled(store, me):
        try:
            rid = enrol.request(store, fingerprint, clock())
        except SecretStoreError:
            if _enrolled(store, me):  # enrolled earlier: request refuses, and the open was made
                break
            raise
        say("Enrolment requested; waiting for the administrator's computer to answer.")
        _follow(store, rid, me, display, say, (poll, deadline, wait), clock, sleep)
    say("This computer is enrolled in the team store; waiting to be admitted to a group.")
    while True:
        groups = groups_of(store, me[0])
        if groups:
            return groups
        _tick(deadline, wait, clock, sleep, poll)
        store.open()


def _enrolled(store, me: tuple[str, str]) -> bool:
    return store.policy is not None and me in store.policy.computers


def _tick(deadline: float, wait: float, clock: Callable, sleep: Callable, poll: float) -> None:
    if clock() > deadline:
        raise SecretStoreError(f"the team enrolment did not finish within {int(wait // 60)} minutes; "
                               "run the setup again")
    sleep(poll)


def _follow(store, rid: str, me: tuple[str, str], display: Callable, say: Callable[[str], None],
            timing: tuple[float, float, float], clock: Callable, sleep: Callable) -> None:
    """Wait on one request until this computer is enrolled, or the request ends or expires."""
    poll, deadline, wait = timing
    request, shown = _read(store, rid), False
    while True:
        _tick(deadline, wait, clock, sleep, poll)
        store.open()
        if _enrolled(store, me):
            return
        now = clock()
        if not _request_path(store, rid).exists() or request is None or now > request["expires"]:
            say("The enrolment request ended without enrolling this computer; making a new one (new words).")
            return
        if not shown and _request_path(store, rid, ".answer").exists():
            enrol.prove(store, rid, display, now)
            shown = True
            say("Send the six words from the window to the administrator; waiting for their approval.")
