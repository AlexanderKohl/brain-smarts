"""The board server saves into the inbox folder (design 04, increment 2): each kind of saved
decisions round-trips, byte for byte, to a file the existing apply script's dry run accepts
unchanged; the server names the file, never the page; it never overwrites; `/_saved.json` lists
what waits; `apply_events.py` reads the inbox folder by default and moves a file out once applied.
The mail and social kinds are tested in their own library skills. Every name is invented
(SMART-RULE-0008): the owner is Sam (author `sam`). Run from the brain root:
    python -m unittest discover -s shared/skills/owner-board/scripts/tests -p "test_serve_boards_saves.py" -v
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from board_fixtures import HAS_GIT, SOIL, git, quiet  # noqa: E402
from test_serve_boards_post import TASKS_BODY, PlumbingBase  # noqa: E402

import apply_events  # noqa: E402
import board_inbox  # noqa: E402
import events  # noqa: E402
import task_actions  # noqa: E402

STAMP = "2026-01-10-10-00-00"


class SaveBase(PlumbingBase):
    def setUp(self):
        super().setUp()
        self.config = self.brain.config()
        self.garden = self.config.board("garden")
        self.nowhere = mock.patch.object(apply_events, "downloads", return_value=str(self.brain.root / "no-downloads"))
        self.nowhere.start()
        self.addCleanup(self.nowhere.stop)

    def verdicts(self, **extra) -> dict:
        state = events.state(self.garden)
        soil = next(c for c in state["items"] if c["id"] == SOIL)
        body = {"schema": self.garden["verdict_schema"], "board": "garden", "by": "sam",
                "savedAt": "2026-01-10T10:00:00.000Z",
                "verdicts": [{"id": SOIL, "verdict": "accepted", "why": "", "sig": soil["sig"],
                              "seen_through": soil.get("last_event", ""), "version": "1.1.0", "shots": []}],
                "tasks": [], "releaseNotes": {}}
        body.update(extra)
        return body

    def save(self, kind: str, body: dict | bytes, path: str | None = None):
        status, _, text = self.run_.post(path or "/_save/" + kind, body)
        return status, json.loads(text)

    def saved(self) -> dict:
        status, _, text = self.run_.request("GET", "/_saved.json")
        self.assertEqual(status, 200)
        return json.loads(text)


class RoundTripTests(SaveBase):
    def test_verdicts_are_filed_byte_for_byte_and_the_apply_dry_run_takes_them(self):
        raw = json.dumps(self.verdicts(), indent=2).encode("utf-8")
        status, answer = self.save("verdicts", raw)
        name = "garden-verdicts-garden-" + STAMP + ".json"
        self.assertEqual(status, 200, answer)
        self.assertEqual(answer["saved"], name)
        self.assertEqual(answer["folder"], "/memory/inbox/")
        self.assertIn(name, answer["say"])
        self.assertEqual((self.inbox / name).read_bytes(), raw)
        applied, skipped, _ = apply_events.apply_file(self.config, self.garden, str(self.inbox / name), dry_run=True)
        self.assertEqual((len(applied), skipped), (1, []))
        self.assertTrue(applied[0].startswith("accept"))

    def test_task_actions_are_filed_and_the_tasks_dry_run_takes_them(self):
        raw = json.dumps(TASKS_BODY).encode("utf-8")
        status, answer = self.save("task-actions", raw)
        name = "task-actions-" + STAMP + ".json"
        self.assertEqual((status, answer["saved"]), (200, name))
        self.assertEqual((self.inbox / name).read_bytes(), raw)
        applied, skipped, _ = task_actions.apply_file(self.config.task_store, str(self.inbox / name), dry_run=True)
        self.assertEqual((len(applied), skipped), (1, []))

    def test_the_mail_and_social_kinds_are_not_offered_without_their_library_skills(self):
        offered = json.loads(self.run_.request("GET", "/_board-server.json")[2])["saves"]
        self.assertEqual(offered, ["verdicts", "task-actions"])
        for kind in ("inbox-decisions", "social-decisions"):
            with self.subTest(kind=kind):
                self.assertEqual(self.save(kind, {"schema": "x", "savedAt": "2026-01-10T10:00:00Z"})[0], 404)
        self.assertEqual(self.written(), [])


class RefusalTests(SaveBase):
    def refused(self, kind: str, body: dict) -> str:
        status, answer = self.save(kind, body)
        self.assertEqual(status, 400, answer)
        self.assertEqual(sorted(answer), ["refused"])
        self.assertEqual(self.written(), [])
        return answer["refused"]

    def test_a_wrong_schema_is_refused(self):
        self.refused("verdicts", self.verdicts(schema="owner-board/verdicts/v0"))
        self.refused("task-actions", dict(TASKS_BODY, schema=self.garden["verdict_schema"]))
        self.refused("verdicts", dict(TASKS_BODY, board="garden"))
        no_schema = dict(TASKS_BODY)
        del no_schema["schema"]
        self.refused("task-actions", no_schema)

    def test_an_unregistered_board_or_none_is_refused(self):
        self.assertIn("pond", self.refused("verdicts", self.verdicts(board="pond")))
        self.refused("verdicts", self.verdicts(board=""))
        self.refused("verdicts", self.verdicts(board="../garden"))
        missing = self.verdicts()
        del missing["board"]
        self.refused("verdicts", missing)

    def test_a_body_without_a_save_time_is_refused(self):
        for saved_at in (None, "", "yesterday", "2026-01-10", "2026-01-10T10:00", "../../x", 20260110):
            with self.subTest(saved_at=saved_at):
                body = dict(TASKS_BODY)
                if saved_at is None:
                    del body["savedAt"]
                else:
                    body["savedAt"] = saved_at
                self.refused("task-actions", body)

    def test_an_inbox_folder_that_cannot_be_written_gives_a_reason_without_its_path(self):
        self.inbox.write_text("a file where the folder should be", encoding="utf-8")
        status, answer = self.save("task-actions", TASKS_BODY)
        self.assertEqual(status, 500)
        self.assertEqual(answer, {"refused": "the inbox folder could not be written"})

    def test_the_refusal_names_no_path_on_this_machine(self):
        reason = self.refused("verdicts", self.verdicts(board="pond"))
        self.assertNotIn(str(self.brain.root), reason)


class NamingTests(SaveBase):
    def test_two_saves_in_one_second_get_a_number_and_nothing_is_overwritten(self):
        bodies = [dict(TASKS_BODY, tasks=[dict(TASKS_BODY["tasks"][0], note="note %d" % n)]) for n in (1, 2, 3)]
        names = [self.save("task-actions", body)[1]["saved"] for body in bodies]
        base = "task-actions-" + STAMP
        self.assertEqual(names, [base + ".json", base + "-2.json", base + "-3.json"])
        for name, body in zip(names, bodies):
            self.assertEqual(json.loads((self.inbox / name).read_text(encoding="utf-8")), body)

    def test_a_name_sent_by_the_page_is_ignored(self):
        body = dict(TASKS_BODY, name="../../evil.json", fileName="..\\evil.json", filename="evil.json")
        status, answer = self.save("task-actions", body, "/_save/task-actions?name=evil.json&file=../x.json")
        self.assertEqual((status, answer["saved"]), (200, "task-actions-" + STAMP + ".json"))
        self.assertEqual(self.written(), ["task-actions-" + STAMP + ".json"])
        self.assertEqual(sorted(p.name for p in self.brain.root.rglob("*evil*")), [])

    def test_the_save_time_names_the_file_and_nothing_else_from_the_body_does(self):
        body = dict(TASKS_BODY, savedAt="2026-02-03T04:05:06.789+10:00", board="../../etc")
        self.assertEqual(self.save("task-actions", body)[1]["saved"], "task-actions-2026-02-03-04-05-06.json")


class WaitingTests(SaveBase):
    def test_saved_lists_what_waits_without_its_content(self):
        self.assertEqual(self.saved(), {"folder": "/memory/inbox/", "saved": []})
        self.save("task-actions", TASKS_BODY)
        self.save("verdicts", self.verdicts())
        for stray in ("notes.txt", "other.json", ".saving-abc.tmp", "inbox-decisions-2026-01-10-10-00-00.json"):
            (self.inbox / stray).write_text("{}", encoding="utf-8")
        listed = self.saved()["saved"]
        self.assertEqual(sorted(e["name"] for e in listed),
                         ["garden-verdicts-garden-" + STAMP + ".json", "task-actions-" + STAMP + ".json"])
        for entry in listed:
            self.assertEqual(sorted(entry), ["kind", "name", "saved", "size"])
            self.assertEqual(entry["size"], (self.inbox / entry["name"]).stat().st_size)
        self.assertEqual({e["kind"] for e in listed}, {"verdicts", "task-actions"})

    def test_saved_is_refused_to_another_host(self):
        self.assertEqual(self.run_.request("GET", "/_saved.json", host="attacker.example")[0], 403)


class ApplyFromTheInboxTests(SaveBase):
    def test_the_apply_dry_run_finds_a_file_in_the_inbox_folder(self):
        name = self.save("verdicts", self.verdicts())[1]["saved"]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = apply_events.main(["--root", str(self.brain.root), "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn(name + " -> Garden Planner", out.getvalue())
        self.assertIn("1 applied", out.getvalue())
        self.assertTrue((self.inbox / name).is_file())    # a dry run moves nothing

    def test_an_applied_file_leaves_the_inbox_and_the_list(self):
        self.save("verdicts", self.verdicts())
        self.save("task-actions", TASKS_BODY)
        self.assertEqual(len(self.saved()["saved"]), 2)
        quiet(apply_events.route, self.config, False)
        self.assertEqual(self.written(), [])
        self.assertEqual(self.saved()["saved"], [])


@unittest.skipUnless(HAS_GIT, "git is not installed")
class SessionCopyTests(unittest.TestCase):
    """A session copy's memory is a linked worktree; the server runs from the shared checkout, so
    the apply in the copy also reads the shared checkout's inbox folder."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="board-inbox-"))
        self.addCleanup(shutil.rmtree, self.base, True)

    def test_a_linked_worktree_also_reads_the_shared_checkouts_inbox(self):
        shared = self.base / "brain" / "memory"
        shared.mkdir(parents=True)
        git(shared, "init", "-q", "-b", "main")
        (shared / "README.md").write_text("memory\n", encoding="utf-8")
        git(shared, "add", "README.md")
        git(shared, "-c", "user.name=sam", "-c", "user.email=sam@example.com", "commit", "-q", "-m", "first")
        copy = self.base / "sessions" / "one" / "memory"
        git(shared, "worktree", "add", "-q", "-b", "session/one", str(copy))
        self.assertEqual(board_inbox.inbox_folders(copy), [])          # neither folder exists yet
        (shared / "inbox").mkdir()
        self.assertEqual([Path(p).resolve() for p in board_inbox.inbox_folders(copy)], [(shared / "inbox").resolve()])
        (copy / "inbox").mkdir()
        self.assertEqual([Path(p).resolve() for p in board_inbox.inbox_folders(copy)],
                         [(copy / "inbox").resolve(), (shared / "inbox").resolve()])
        self.assertEqual([Path(p).resolve() for p in board_inbox.inbox_folders(shared)], [(shared / "inbox").resolve()])

    def test_a_memory_that_is_no_repository_reads_its_own_inbox_only(self):
        plain = self.base / "memory"
        (plain / "inbox").mkdir(parents=True)
        self.assertEqual([Path(p).resolve() for p in board_inbox.inbox_folders(plain)], [(plain / "inbox").resolve()])


if __name__ == "__main__":
    unittest.main()
