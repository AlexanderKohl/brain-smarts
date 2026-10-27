"""Behaviour of release_notes.py on a throwaway brain and a throwaway git repository.

Every name here is invented (SMART-RULE-0008). The throwaway brain carries a copy of the
owner-board skill's `events.py` beside it so choice ids and the card-retiring release can run.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))
import release_choices as rc  # noqa: E402
import release_notes as rn  # noqa: E402

OWNER_BOARD = HERE.parents[5] / "shared" / "skills" / "owner-board" / "scripts"


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class Brain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / "brain"
        (self.root / "memory" / "skills" / "release-notes" / "config").mkdir(parents=True)
        (self.root / "CONTRACT.md").write_text("contract\n", encoding="utf-8")
        (self.root / "memory" / "OWNER.md").write_text("---\nowner_short_name: Ann\n---\n", encoding="utf-8")
        scripts = self.root / "shared" / "skills" / "owner-board" / "scripts"
        scripts.mkdir(parents=True)
        for name in ("events.py", "cards.py", "board_config.py"):
            shutil.copy(OWNER_BOARD / name, scripts / name)
        self.repo = base / "app"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "prod")
        git(self.repo, "config", "user.email", "tester@localhost")
        git(self.repo, "config", "user.name", "Example Tester")
        (self.repo / "package.json").write_text('{"version": "1.0.0"}\n', encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "start")
        git(self.repo, "checkout", "-q", "-b", "dev")
        config = {
            "project_repos_root": str(base),
            "pages": [{"id": "team", "title": "What's changed", "readers": "the team",
                       "projects": ["app", "crm"]}],
            "projects": [
                {"id": "app", "label": "App", "kind": "git", "repo": "app", "production": "prod",
                 "development": "dev", "local_refs": True},
                {"id": "crm", "label": "CRM", "kind": "folder", "folder": "app:release-notes/crm",
                 "released_on": "the snapshot"},
            ],
        }
        path = self.root / "memory" / "skills" / "release-notes" / "config" / "release-notes.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        self.cfg = rn.Config(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, name, message):
        (self.repo / name).write_text(name, encoding="utf-8")
        git(self.repo, "add", name)
        git(self.repo, "commit", "-q", "-m", message)
        return subprocess.run(["git", "-C", str(self.repo), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True).stdout.strip()

    def note(self, project, slug, v, commits=()):
        path = rn.new_note(self.cfg, self.cfg.projects[project], slug, slug.title(), commits=list(commits))
        front, body = rn.read_front(path)
        front["visibility"] = v
        rn.write_note(path, front, "Body of " + slug)
        return path


class Notes(Brain):
    def test_a_new_note_starts_undecided_and_a_repository_note_carries_no_brain_metadata(self):
        path = rn.new_note(self.cfg, self.cfg.projects["crm"], "portal-links", "Portal links")
        front, _ = rn.read_front(path)
        self.assertEqual(front["visibility"], "undecided")
        self.assertNotIn("contract", front)
        self.assertTrue(str(path).startswith(str(self.repo / "release-notes" / "crm")))

    def test_new_is_read_as_added(self):
        path = rn.new_note(self.cfg, self.cfg.projects["crm"], "x", "X", kind="added")
        path.write_text(path.read_text(encoding="utf-8").replace("kind: added", "kind: new"), encoding="utf-8")
        note = rn.load_notes(path.parent)[0]
        self.assertEqual(rn.problems(note), [])

    def test_unknown_visibility_is_a_problem(self):
        path = rn.new_note(self.cfg, self.cfg.projects["crm"], "x", "X")
        path.write_text(path.read_text(encoding="utf-8").replace("undecided", "maybe"), encoding="utf-8")
        self.assertTrue(rn.problems(rn.load_notes(path.parent)[0]))


class Choices(Brain):
    def test_a_choice_is_an_event_and_the_note_file_is_untouched(self):
        path = rn.new_note(self.cfg, self.cfg.projects["crm"], "x", "Old title")
        before = path.read_text(encoding="utf-8")
        report = rc.apply_choices(self.cfg, {"notes": [
            {"project": "crm", "slug": "x", "title": "New title", "visibility": "announce", "body": "What they see."}]},
            "Ann", "2026-10-01T09:00:00Z")
        self.assertEqual(path.read_text(encoding="utf-8"), before)
        events = sorted((self.cfg.folder(self.cfg.projects["crm"]) / "choices").glob("*.json"))
        self.assertEqual([e.stem for e in events], ["ann-20261001T090000Z"])
        self.assertIn("crm/x body, title, visibility", report[0])
        notes, broken, conflicts = rc.collect_unreleased(self.cfg, self.cfg.projects["crm"])
        self.assertEqual((notes[0]["front"]["title"], notes[0]["front"]["visibility"], notes[0]["body"]),
                         ("New title", "announce", "What they see."))
        self.assertEqual(conflicts, {})

    def test_the_fold_gives_one_answer_for_any_order_and_the_earliest_wins_across_authors(self):
        rn.new_note(self.cfg, self.cfg.projects["crm"], "x", "X")
        rc.apply_choices(self.cfg, {"notes": [{"project": "crm", "slug": "x", "visibility": "hold"}]}, "bob", "2026-10-01T09:00:05Z")
        rc.apply_choices(self.cfg, {"notes": [{"project": "crm", "slug": "x", "visibility": "announce"}]}, "ann", "2026-10-01T09:00:00Z")
        rc.apply_choices(self.cfg, {"notes": [{"project": "crm", "slug": "x", "visibility": "internal"}]}, "ann", "2026-10-01T09:00:09Z")
        choices = rc.read_choices(self.cfg, self.cfg.projects["crm"])
        for order in (choices, list(reversed(choices)), choices[1:] + choices[:1]):
            folded = rc.fold(sorted(order, key=lambda c: (c["saved_at"], c["by"], c["id"])))
            # Ann's own later choice replaces hers; Bob's different choice stays a conflict.
            self.assertEqual(folded["notes"]["x"]["visibility"]["value"], "internal")
            self.assertEqual([(c["first"]["by"], c["later"]["by"]) for c in folded["conflicts"]["x"]], [("ann", "bob")])
        notes, _, conflicts = rc.collect_unreleased(self.cfg, self.cfg.projects["crm"])
        self.assertEqual(notes[0]["conflicts"][0]["field"], "visibility")
        self.assertIn("x", conflicts)

    def test_a_commit_set_aside_by_a_choice_leaves_the_list(self):
        h = self.commit("a.txt", "tidy the tests")
        self.assertEqual([c["hash"] for c in rc.collect_loose(self.cfg, self.cfg.projects["app"], [])], [h])
        rc.apply_choices(self.cfg, {"commits": [{"project": "app", "hash": h, "action": "skip"}]}, "ann", "2026-10-01T09:00:00Z")
        self.assertEqual(rc.collect_loose(self.cfg, self.cfg.projects["app"], []), [])
        self.assertFalse((self.repo / "release-notes" / "not-user-visible.txt").exists())

    def test_a_new_note_choice_creates_the_note_by_its_author(self):
        h = self.commit("b.txt", "Site weather")
        report = rc.apply_choices(self.cfg, {"commits": [{"project": "app", "hash": h, "action": "new", "subject": "Site weather"}]},
                                  "ann", "2026-10-01T09:00:00Z")
        self.assertTrue((self.repo / "release-notes" / "unreleased" / "site-weather.md").exists())
        self.assertTrue(any("new note site-weather" in line for line in report))
        self.assertEqual(rc.collect_loose(self.cfg, self.cfg.projects["app"], []), [])

    def test_a_trailer_claims_a_commit(self):
        rn.new_note(self.cfg, self.cfg.projects["app"], "weather", "Weather")
        self.commit("b.txt", "site weather\n\nRelease-note: weather")
        notes = rn.load_notes(self.cfg.folder(self.cfg.projects["app"]) / "unreleased")
        self.assertEqual(rn.unnoted(self.cfg, self.cfg.projects["app"], notes), [])

    def test_a_legacy_not_user_visible_file_is_still_read(self):
        self.commit("c.txt", "tidy the tests again")
        folder = self.cfg.folder(self.cfg.projects["app"])
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "not-user-visible.txt").write_text("# set aside\n2026-10-01 tidy the tests again\n", encoding="utf-8")
        self.assertEqual(rn.unnoted(self.cfg, self.cfg.projects["app"], []), [])


class Releasing(Brain):
    def board(self):
        """A board that draws the app's notes, with two open cards and one above the version."""
        config = self.root / "memory" / "skills" / "owner-board" / "config"
        config.mkdir(parents=True)
        (config / "boards.json").write_text(json.dumps({"boards": [
            {"id": "app", "label": "App", "status": "projects/app/status", "release_notes": ["app"]}]}), encoding="utf-8")
        folder = self.root / "memory" / "projects" / "app" / "status"
        (folder / "cards").mkdir(parents=True)
        (folder / "board.json").write_text('{"id": "app", "label": "App", "tracks": {"t": {"label": "T", "task": "x"}}}', encoding="utf-8")
        for cid, version in (("ann-20260101T000000Z", "1.1.0"), ("ann-20260101T000001Z", "1.0.5"), ("ann-20260101T000002Z", "1.2.0")):
            (folder / "cards" / (cid + ".md")).write_text(
                "---\nid: %s\ntitle: t\ntype: board_card\nschema_version: 0.2\ncontract: /CONTRACT.md\nparent: /memory/projects/app\n"
                "created: 2026-01-01T10:00:00+10:00\nupdated: 2026-01-01T10:00:00+10:00\nowner: Ann\ntrack: t\nstate: needs_review\n"
                "version: %s\nbranch: null\nasked: 2026-01-01\narea:\n---\n\n# t\n\n## What landed\n\nx\n\n## To check\n\ny\n" % (cid, version),
                encoding="utf-8")
        return folder

    def test_only_announced_notes_reach_the_team_page_and_the_rest_carry_forward(self):
        for slug, v in [("a", "announce"), ("b", "internal"), ("c", "hold"), ("d", "undecided")]:
            self.note("crm", slug, v)
        rn.release(self.cfg, self.cfg.projects["crm"], "r1", "production", date="2026-10-01")
        folder = self.cfg.folder(self.cfg.projects["crm"])
        self.assertEqual(sorted(p.stem for p in (folder / "unreleased").glob("*.md")), ["c", "d"])
        rels = rc.collect_released(self.cfg, self.cfg.projects["crm"])
        self.assertEqual([r["version"] for r in rels["production"]], ["r1"])
        self.assertEqual(rels["testing"], [])
        team = rn.build(self.cfg)
        text = {p.name: p.read_text(encoding="utf-8") for p in team}
        self.assertIn("Body of a", text["team.production.html"])
        self.assertNotIn("Body of b", text["team.production.html"])
        self.assertIn("Nothing released to testing yet", text["team.testing.html"])
        self.assertEqual(text["team.html"], text["team.production.html"])

    def test_a_release_bakes_the_chosen_wording_in(self):
        self.note("crm", "a", "undecided")
        rc.apply_choices(self.cfg, {"notes": [{"project": "crm", "slug": "a", "visibility": "announce", "title": "Chosen title"}]},
                         "ann", "2026-10-01T09:00:00Z")
        rn.release(self.cfg, self.cfg.projects["crm"], "r1", "testing", date="2026-10-02")
        front, _ = rn.read_front(self.cfg.folder(self.cfg.projects["crm"]) / "released" / "r1" / "a.md")
        self.assertEqual((front["title"], front["visibility"]), ("Chosen title", "announce"))

    def test_testing_then_production_mark_one_release_and_never_twice(self):
        self.note("crm", "a", "announce")
        rn.release(self.cfg, self.cfg.projects["crm"], "r1", "testing", date="2026-10-01")
        self.note("crm", "b", "announce")
        rn.release(self.cfg, self.cfg.projects["crm"], "r1", "production", date="2026-10-03")
        rec = json.loads((self.cfg.folder(self.cfg.projects["crm"]) / "released" / "r1" / "release.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["environments"], {"testing": "2026-10-01", "production": "2026-10-03"})
        self.assertEqual(sorted(p.stem for p in (self.cfg.folder(self.cfg.projects["crm"]) / "unreleased").glob("*.md")), ["b"])
        with self.assertRaises(rn.Refused):
            rn.release(self.cfg, self.cfg.projects["crm"], "r1", "production")

    def test_a_code_release_waits_for_the_merge(self):
        h = self.commit("c.txt", "feature")
        self.note("app", "feature", "announce", [h])
        with self.assertRaises(rn.Refused):
            rn.release(self.cfg, self.cfg.projects["app"], "1.1.0", "production")
        rn.release(self.cfg, self.cfg.projects["app"], "1.1.0", "testing", date="2026-10-02")   # on dev already
        self.assertTrue((self.repo / "release-notes" / "released" / "1.1.0" / "feature.md").exists())

    def test_release_writes_one_released_event_per_open_card_at_or_below_the_version(self):
        folder = self.board()
        self.note("app", "a", "announce")
        lines = rn.release(self.cfg, self.cfg.projects["app"], "1.1.0", "testing", date="2026-10-02")
        written = sorted((folder / "events").glob("*.json"))
        self.assertEqual(len(written), 2)
        retired = {json.loads(p.read_text(encoding="utf-8"))["card"] for p in written}
        self.assertEqual(retired, {"ann-20260101T000000Z", "ann-20260101T000001Z"})   # not the 1.2.0 card
        self.assertTrue(all(json.loads(p.read_text(encoding="utf-8"))["env"] == "testing" for p in written))
        self.assertEqual(sum("retired app:" in line for line in lines), 2)
        # The same environment again writes none; production writes two more.
        self.assertEqual(rn.retire_cards(self.cfg, self.cfg.projects["app"], "1.1.0", "testing"), [])
        self.assertEqual(len(rn.retire_cards(self.cfg, self.cfg.projects["app"], "1.1.0", "production")), 2)

    def test_dry_run_writes_nothing(self):
        folder = self.board()
        self.note("app", "a", "announce")
        lines = rn.release(self.cfg, self.cfg.projects["app"], "1.1.0", "testing", date="2026-10-02", dry_run=True)
        self.assertTrue(any(line.startswith("would move a") for line in lines))
        self.assertFalse((folder / "events").exists())
        self.assertFalse((self.repo / "release-notes" / "released").exists())


class Linking(Brain):
    def release(self, version, message):
        (self.repo / "package.json").write_text('{"version": "%s"}\n' % version, encoding="utf-8")
        git(self.repo, "add", "package.json")
        return self.commit("f%s.txt" % version, message)

    def test_link_fills_a_notes_commits_and_versions_from_its_trailers(self):
        rn.new_note(self.cfg, self.cfg.projects["app"], "weather", "Weather")
        first = self.release("1.1.0", "site weather\n\nRelease-note: weather")
        self.release("1.1.1", "tidy")
        second = self.release("1.2.0", "weather on the page\n\nRelease-note: weather")
        self.assertEqual(rn.main(["--root", str(self.root), "link", "app"]), 0)
        note = rn.load_notes(self.cfg.folder(self.cfg.projects["app"]) / "unreleased")[0]
        self.assertEqual(note["front"]["commits"], [first, second])
        self.assertEqual(note["front"]["versions"], ["1.1.0", "1.2.0"])
        named = rn.release_link.named_by(self.repo, rn.git, "dev", rn.TRAILER)
        self.assertEqual(rn.release_link.link(rn.load_notes(self.cfg.folder(self.cfg.projects["app"]) / "unreleased"), named, rn.write_note), [])

    def test_versions_sort_as_versions(self):
        self.assertEqual(sorted(["1.10.0", "1.9.0", "1.9.10", "1.9.2"], key=rn.release_link.version_key),
                         ["1.9.0", "1.9.2", "1.9.10", "1.10.0"])


class BrokenNotes(Brain):
    """A note that does not parse is named, repaired or skipped; it never stops a command."""

    def folder(self):
        return self.cfg.folder(self.cfg.projects["app"]) / "unreleased"

    def broken(self, slug, front, newline="\n"):
        path = self.folder() / (slug + ".md")
        path.parent.mkdir(parents=True, exist_ok=True)
        text = "---\n" + front + "\n---\n\nWhat they see.\n"
        path.write_bytes(text.replace("\n", newline).encode("utf-8"))
        return path

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = rn.main(["--root", str(self.root), *argv])
        return code, out.getvalue()

    def test_check_names_every_failing_note_with_file_line_and_problem(self):
        self.broken("colon", "title: Colon\nkind: changed\nvisibility: undecided\nlook_out_for: Check: the total")
        self.broken("quote", 'title: "Your decision" is a page\nkind: changed\nvisibility: undecided')
        rn.new_note(self.cfg, self.cfg.projects["app"], "good", "Good")
        code, out = self.run_main("check")
        self.assertEqual(code, 1)
        self.assertIn("app/colon: does not parse", out)
        self.assertIn("colon.md: line 5: mapping values are not allowed here", out)
        self.assertIn("app/quote: does not parse", out)
        self.assertIn("2 problem(s)", out)

    def test_fix_turns_the_value_into_a_block_and_keeps_words_and_line_endings(self):
        path = self.broken("colon", "title: Colon\nkind: changed\nvisibility: undecided\n"
                           "look_out_for: Check: the total\nopened: 2026-10-01", newline="\r\n")
        code, out = self.run_main("fix")
        self.assertEqual(code, 0, out)
        self.assertIn("fixed app/colon", out)
        raw = path.read_bytes().decode("utf-8")
        self.assertIn("look_out_for: >-\r\n  Check: the total\r\n", raw)
        self.assertEqual(raw.count("\r\n"), raw.count("\n"))
        front, _ = rn.read_front(path)
        self.assertEqual(front["look_out_for"], "Check: the total")
        self.assertEqual(self.run_main("check")[0], 0)

    def test_fix_lists_what_it_could_not_repair(self):
        self.broken("odd", "title: [unclosed\nkind: changed")
        code, out = self.run_main("fix")
        self.assertEqual(code, 1)
        self.assertIn("could not repair app/odd", out)

    def test_link_and_build_skip_a_failing_note_and_say_so_at_the_top(self):
        self.broken("colon", "title: Colon\nkind: changed\nvisibility: undecided\nlook_out_for: Check: the total")
        rn.new_note(self.cfg, self.cfg.projects["app"], "weather", "Weather")
        self.commit("w.txt", "site weather\n\nRelease-note: weather")
        code, out = self.run_main("link", "app")
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("skipped app/colon: line 5"), out)
        code, out = self.run_main("build")
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("skipped app/colon"), out)
        self.assertTrue((self.cfg.pages_dir / "team.testing.html").is_file())
        self.assertTrue((self.cfg.pages_dir / "team.production.html").is_file())
        self.assertFalse((self.root / "memory" / "boards" / "release-notes.html").exists())   # no selection page


class RepositoryDefinition(unittest.TestCase):
    """A second, fictional brain with no release-notes configuration of its own reads the projects
    a repository defines in `brain/status/release-notes.json`; the owner's memory entry wins."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / "brain-b"
        (self.root / "memory").mkdir(parents=True)
        (self.root / "CONTRACT.md").write_text("contract\n", encoding="utf-8")
        (self.root / "memory" / "OWNER.md").write_text("---\nowner_short_name: Bea\n---\n", encoding="utf-8")
        self.repo = base / "orchard-app"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "prod")
        git(self.repo, "config", "user.email", "tester@localhost")
        git(self.repo, "config", "user.name", "Example Tester")
        (self.repo / "a.txt").write_text("a", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "start")
        git(self.repo, "checkout", "-q", "-b", "dev")
        notes = self.repo / "release-notes" / "unreleased"
        notes.mkdir(parents=True)
        (notes / "pruning.md").write_text("---\ntitle: Pruning dates\nkind: added\nvisibility: undecided\n---\n\n"
                                          "Each tree shows when it was last pruned.\n", encoding="utf-8")
        (self.repo / "b.txt").write_text("b", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "show the pruning dates")
        self.write_definition([{"id": "orchard", "label": "Orchard app", "kind": "git", "development": "dev",
                                "production": "prod", "local_refs": True}])

    def tearDown(self):
        self.tmp.cleanup()

    def write_definition(self, projects):
        path = rc.repo_definition(self.repo)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"projects": projects}), encoding="utf-8")
        return path

    def test_a_brain_without_the_owner_configuration_reads_the_repository_projects(self):
        self.assertFalse((self.root / "memory" / "skills").exists())
        cfg = rc.load_config(self.root, repository=self.repo)
        self.assertEqual(cfg.problems, [])
        project = cfg.projects["orchard"]
        self.assertEqual(cfg.repo(project), self.repo.absolute())
        self.assertEqual(cfg.folder(project), self.repo.absolute() / "release-notes")
        notes, broken, _ = rc.collect_unreleased(cfg, project)
        self.assertEqual(([n["slug"] for n in notes], broken), (["pruning"], []))
        loose = rc.collect_loose(cfg, project, notes)
        self.assertIn("show the pruning dates", [c["subject"] for c in loose])
        self.assertEqual(rc.collect_released(cfg, project), {"testing": [], "production": []})

    def test_without_a_repository_file_the_memory_configuration_is_empty_not_an_error(self):
        cfg = rc.load_config(self.root)
        self.assertEqual((cfg.projects, cfg.pages, cfg.problems), ({}, [], []))
        with self.assertRaises(OSError):
            rc.load_config(self.root, self.root / "memory" / "missing.json")   # an explicit path must exist

    def test_the_owner_memory_entry_overrides_the_repository_entry_with_the_same_id(self):
        config = self.root / "memory" / "skills" / "release-notes" / "config"
        config.mkdir(parents=True)
        (config / "release-notes.json").write_text(json.dumps({"projects": [
            {"id": "orchard", "label": "Orchard (owner's own)", "kind": "folder",
             "folder": "/memory/projects/orchard/release-notes"}]}), encoding="utf-8")
        self.write_definition([{"id": "orchard", "label": "Orchard app", "kind": "git", "development": "dev",
                                "production": "prod"},
                               {"id": "orchard-crm", "label": "Orchard CRM", "kind": "folder",
                                "folder": "release-notes/crm"}])
        cfg = rc.load_config(self.root, repository=self.repo)
        self.assertEqual(cfg.projects["orchard"]["label"], "Orchard (owner's own)")
        self.assertEqual(cfg.folder(cfg.projects["orchard"]), self.root / "memory" / "projects" / "orchard" / "release-notes")
        self.assertEqual(cfg.folder(cfg.projects["orchard-crm"]), self.repo.absolute() / "release-notes" / "crm")

    def test_paths_outside_the_repository_and_a_broken_file_are_problems_not_errors(self):
        self.write_definition([
            {"id": "a", "label": "A", "kind": "folder", "folder": "C:/elsewhere"},
            {"id": "b", "label": "B", "kind": "folder", "folder": "/etc/notes"},
            {"id": "c", "label": "C", "kind": "folder", "folder": "release-notes/../../x"},
            {"id": "d", "label": "D", "kind": "git"},
            {"id": "e", "label": "E", "kind": "svn"},
            {"id": "f", "label": "F", "kind": "folder", "folder": "notes/f"}])
        cfg = rc.load_config(self.root, repository=self.repo)
        self.assertEqual(sorted(cfg.projects), ["f"])
        self.assertEqual(len(cfg.problems), 5, cfg.problems)
        self.assertTrue(all(p.startswith("orchard-app/brain/status/release-notes.json") for p in cfg.problems))
        rc.repo_definition(self.repo).write_text("{not json", encoding="utf-8")
        cfg = rc.load_config(self.root, repository=self.repo)
        self.assertEqual(cfg.projects, {})
        self.assertIn("cannot be read", cfg.problems[0])

    def link(self, link: Path, target: Path) -> None:
        """A directory link: a symlink, or a junction on Windows without the symlink privilege."""
        try:
            os.symlink(target, link, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                self.skipTest("this system cannot make a directory link")
            import _winapi
            _winapi.CreateJunction(str(target), str(link))

    def test_a_folder_that_leaves_the_repository_through_a_link_is_refused(self):
        outside = Path(self.tmp.name) / "elsewhere"
        (outside / "unreleased").mkdir(parents=True)
        shutil.rmtree(self.repo / "release-notes")
        self.link(self.repo / "release-notes", outside)
        (self.repo / "inner").mkdir()
        self.link(self.repo / "notes-alias", self.repo / "inner")   # a link that stays inside is fine
        self.assertIsNone(rn.confined(self.repo, "release-notes"))
        self.assertEqual(rn.confined(self.repo, "notes-alias"), self.repo / "notes-alias")
        self.write_definition([{"id": "orchard", "label": "Orchard app", "kind": "git", "development": "dev",
                                "production": "prod", "local_refs": True},
                               {"id": "alias", "label": "Alias", "kind": "folder", "folder": "notes-alias"}])
        cfg = rc.load_config(self.root, repository=self.repo)
        self.assertEqual(sorted(cfg.projects), ["alias"])
        self.assertTrue(any("orchard" in p and "link" in p for p in cfg.problems), cfg.problems)

    def test_a_link_made_after_loading_is_refused_before_anything_is_written(self):
        cfg = rc.load_config(self.root, repository=self.repo)
        project = cfg.projects["orchard"]
        outside = Path(self.tmp.name) / "elsewhere"
        outside.mkdir()
        shutil.rmtree(self.repo / "release-notes")
        self.link(self.repo / "release-notes", outside)
        scripts = self.root / "shared" / "skills" / "owner-board" / "scripts"
        scripts.mkdir(parents=True)
        for name in ("events.py", "cards.py", "board_config.py"):
            shutil.copy(OWNER_BOARD / name, scripts / name)
        with self.assertRaises(rn.Refused):
            rn.new_note(cfg, project, "frost", "Frost warnings")
        with self.assertRaises(rn.Refused):
            rc.apply_choices(cfg, {"notes": [{"project": "orchard", "slug": "pruning", "visibility": "announce"}],
                                   "commits": []}, "Bea", "", False)
        self.assertEqual(list(outside.iterdir()), [])

    def test_a_link_under_the_folder_is_refused_for_every_read_and_write(self):
        scripts = self.root / "shared" / "skills" / "owner-board" / "scripts"
        scripts.mkdir(parents=True)
        for name in ("events.py", "cards.py", "board_config.py"):
            shutil.copy(OWNER_BOARD / name, scripts / name)
        notes = self.repo / "release-notes"
        cfg = rc.load_config(self.root, repository=self.repo)
        project = cfg.projects["orchard"]
        choose = {"notes": [{"project": "orchard", "slug": "pruning", "visibility": "announce"}], "commits": []}
        new = {"notes": [], "commits": [{"project": "orchard", "hash": "abc1234", "action": "new", "subject": "Hail"}]}
        cases = {   # the link planted, and every call that reads or writes through it
            "unreleased": [lambda: rn.new_note(cfg, project, "frost", "Frost"),
                           lambda: rc.collect_unreleased(cfg, project),
                           lambda: rc.apply_choices(cfg, new, "Bea", "", False),
                           lambda: rn.fix_notes(cfg)],
            "choices": [lambda: rc.apply_choices(cfg, choose, "Bea", "", False),
                        lambda: rc.collect_unreleased(cfg, project)],
            "released": [lambda: rn.release(cfg, project, "1.0.0", "testing"),
                         lambda: rc.collect_released(cfg, project)],
            "released/1.0.0": [lambda: rn.release(cfg, project, "1.0.0", "testing")],
        }
        for child, calls in cases.items():
            with self.subTest(link=child):
                outside = Path(tempfile.mkdtemp(dir=self.tmp.name, prefix="outside-"))
                link = notes / child
                keep = None
                if link.exists():
                    keep = Path(self.tmp.name) / ("kept-" + child.replace("/", "-"))
                    shutil.move(str(link), str(keep))
                link.parent.mkdir(parents=True, exist_ok=True)
                self.link(link, outside)
                try:
                    for call in calls:
                        with self.assertRaises(rn.Refused):
                            call()
                    self.assertEqual(list(outside.iterdir()), [])
                finally:
                    os.unlink(link) if link.is_symlink() else os.rmdir(link)
                    if keep is not None:
                        shutil.move(str(keep), str(link))
        with self.assertRaises(rn.Refused):   # a version that climbs out is refused the same way
            rn.release(cfg, project, "../../../escaped", "testing")
        self.assertFalse((Path(self.tmp.name) / "escaped").exists())

    def run_cli(self, *args) -> tuple:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = rn.main(["--root", str(self.root), *args])
        return code, out.getvalue(), err.getvalue()

    def test_the_command_line_loads_the_repository_definition(self):
        code, out, err = self.run_cli("--repo", str(self.repo), "new", "orchard", "frost", "--title", "Frost warnings")
        self.assertEqual(code, 0, err)
        self.assertTrue((self.repo / "release-notes" / "unreleased" / "frost.md").is_file())
        here = os.getcwd()
        try:   # without --repo: the repository holding the current folder
            os.chdir(self.repo / "release-notes")
            code, out, err = self.run_cli("new", "orchard", "hail", "--title", "Hail warnings")
        finally:
            os.chdir(here)
        self.assertEqual(code, 0, err)
        self.assertTrue((self.repo / "release-notes" / "unreleased" / "hail.md").is_file())
        code, out, err = self.run_cli("--repo", str(self.root), "check")
        self.assertEqual(code, 2)
        self.assertIn("no brain/status/release-notes.json", err)

    def test_the_command_line_still_lets_the_owner_entry_win(self):
        config = self.root / "memory" / "skills" / "release-notes" / "config"
        config.mkdir(parents=True)
        (config / "release-notes.json").write_text(json.dumps({"projects": [
            {"id": "orchard", "label": "Orchard (owner's own)", "kind": "folder",
             "folder": "/memory/projects/orchard/release-notes"}]}), encoding="utf-8")
        code, out, err = self.run_cli("--repo", str(self.repo), "new", "orchard", "frost", "--title", "Frost warnings")
        self.assertEqual(code, 0, err)
        self.assertTrue((self.root / "memory" / "projects" / "orchard" / "release-notes" / "unreleased" / "frost.md").is_file())
        self.assertFalse((self.repo / "release-notes" / "unreleased" / "frost.md").exists())


if __name__ == "__main__":
    unittest.main()
