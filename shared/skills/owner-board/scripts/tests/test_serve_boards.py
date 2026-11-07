"""The board server: the directory page's links to status pages outside its folder are served,
and nothing else is. Every folder and name is invented (SMART-RULE-0008). Run from the brain root:
    python -m unittest discover -s shared/skills/owner-board/scripts/tests -p "test_serve_boards.py" -v
"""
from __future__ import annotations

import datetime
import http.client
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import serve_boards  # noqa: E402


class ArrivalTests(unittest.TestCase):
    def test_a_link_that_climbs_above_the_root_arrives_without_the_climb(self):
        self.assertEqual(serve_boards.arrival("../../../example-repo/brain/status/status.html"), "/example-repo/brain/status/status.html")
        self.assertEqual(serve_boards.arrival("../projects/example-node/status/status.html"), "/projects/example-node/status/status.html")
        self.assertEqual(serve_boards.arrival("projects/example.html"), "/projects/example.html")
        self.assertEqual(serve_boards.arrival("a/../b/./c"), "/b/c")


class Site:
    """A boards folder, a memory node with a status page and tasks, a repository with a brain
    node and code beside it, and a secret file next to everything."""

    def __init__(self, base: Path):
        self.boards = base / "memory" / "boards"
        self.node = base / "memory" / "projects" / "example-node"
        self.repo = base / "example-repo"
        for folder, files in {
            self.boards: {"index.html": "directory", "projects/example.html": "own page"},
            self.node: {"status/status.html": "node board", "tasks/open/TASK-1.md": "a task", ".hidden/x.txt": "hidden"},
            self.repo / "brain": {"status/status.html": "repo board", "tasks/TASK-2.md": "repo task"},
            self.repo: {".env": "SECRET=1", "src/app.py": "code"},
            base / "memory": {"OWNER.md": "owner"},
        }.items():
            for name, text in files.items():
                path = folder / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
        self.table = [("/example-repo/brain", self.repo / "brain"), ("/projects/example-node", self.node), ("/", self.boards)]


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="serve-boards-"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.site = Site(self.base)

    def got(self, path: str):
        return serve_boards.resolve(path, self.site.table)

    def test_the_board_pages_and_their_task_links_are_served(self):
        self.assertEqual(self.got("/"), (self.site.boards / "index.html").resolve())
        self.assertEqual(self.got("/projects/example.html"), (self.site.boards / "projects/example.html").resolve())
        self.assertEqual(self.got("/projects/example-node/status/status.html"), (self.site.node / "status/status.html").resolve())
        self.assertEqual(self.got("/projects/example-node/tasks/open/TASK-1.md"), (self.site.node / "tasks/open/TASK-1.md").resolve())
        self.assertEqual(self.got("/example-repo/brain/status/status.html"), (self.site.repo / "brain/status/status.html").resolve())
        self.assertEqual(self.got("/example-repo/brain/status/status.html?x=1#y"), (self.site.repo / "brain/status/status.html").resolve())

    def test_nothing_outside_the_mounted_folders_is_served(self):
        for path in ("/example-repo/.env", "/example-repo/src/app.py", "/example-repo/brain/../.env", "/%2e%2e/OWNER.md",
                     "/../OWNER.md", "/projects/example-node/.hidden/x.txt", "/projects/example-node/status/", "/missing.html",
                     "/projects/example-node/..%2f..%2fOWNER.md", "/C:/Windows/win.ini", "/projects/example-node%5c..%5c..%5cOWNER.md"):
            with self.subTest(path=path):
                self.assertIsNone(self.got(path))

    def test_a_prefix_matches_whole_segments_only(self):
        (self.site.boards / "projects" / "example-node-other.html").write_text("other", encoding="utf-8")
        self.assertEqual(self.got("/projects/example-node-other.html"), (self.site.boards / "projects/example-node-other.html").resolve())


class ServerTests(unittest.TestCase):
    """The handler on a real socket: the Host check and the 404 for what is not mounted."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="serve-boards-http-"))
        self.addCleanup(shutil.rmtree, self.base, True)
        site = Site(self.base)
        handler = type("H", (serve_boards.Handler,), {"table": site.table, "log_message": lambda *a: None})
        self.server = serve_boards.http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def get(self, path: str, host: str | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=10)
        conn.putrequest("GET", path, skip_host=True)
        conn.putheader("Host", host or f"localhost:{self.server.server_address[1]}")
        conn.endheaders()
        res = conn.getresponse()
        body = res.read().decode("utf-8", errors="replace")
        conn.close()
        return res.status, res.getheader("Content-Type"), body

    def test_a_repository_status_page_is_served_with_its_type(self):
        status, ctype, body = self.get("/example-repo/brain/status/status.html")
        self.assertEqual((status, body), (200, "repo board"))
        self.assertIn("text/html", ctype)

    def test_the_repository_beside_its_brain_is_not_served(self):
        self.assertEqual(self.get("/example-repo/.env")[0], 404)
        self.assertEqual(self.get("/example-repo/src/app.py")[0], 404)

    def test_a_request_for_another_host_is_refused(self):
        self.assertEqual(self.get("/", host="attacker.example")[0], 403)
        self.assertEqual(self.get("/", host="127.0.0.1")[0], 200)


def git(cwd: Path, *args: str) -> str:
    out = subprocess.run(["git", "-c", "user.name=sam", "-c", "user.email=sam@example.com", "-c", "commit.gpgsign=false",
                          "-c", "core.autocrlf=false", *args], cwd=str(cwd), capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(" ".join(args) + ": " + out.stderr)
    return out.stdout


class MemoryCheckout:
    """A memory checkout with a local origin, and a second clone that pushes two commits to it.
    The fetch in the checkout stands in for a push from a session copy, which updates origin/main
    in the shared .git without touching the checkout's own files."""

    def __init__(self, base: Path, files: int = 2):
        self.origin = base / "origin.git"
        git(base, "init", "--bare", "-b", "main", str(self.origin))
        self.memory = base / "memory"
        git(base, "clone", "-q", str(self.origin), str(self.memory))
        git(self.memory, "checkout", "-q", "-B", "main")
        for n in range(files):
            (self.memory / ("note-%02d.md" % n)).write_text("note %d\n" % n, encoding="utf-8")
        git(self.memory, "add", "-A")
        git(self.memory, "commit", "-q", "-m", "first")
        git(self.memory, "push", "-q", "origin", "main")
        other = base / "session-copy"
        git(base, "clone", "-q", str(self.origin), str(other))
        for n in (1, 2):
            (other / ("later-%d.md" % n)).write_text("later\n", encoding="utf-8")
            git(other, "add", "-A")
            git(other, "commit", "-q", "-m", "later %d" % n)
        git(other, "push", "-q", "origin", "main")
        git(self.memory, "fetch", "-q", "origin")


class MemoryStatusTests(unittest.TestCase):
    """GET /_boards-status.json: how far the memory checkout the boards come from lags, and the
    tracked files changed or staged there that would block it catching up."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="serve-boards-git-"))
        self.addCleanup(shutil.rmtree, self.base, True)

    def test_behind_counts_the_commits_on_origin_main_the_checkout_lacks(self):
        repo = MemoryCheckout(self.base)
        status = serve_boards.memory_status(repo.memory)
        self.assertEqual(sorted(status), ["behind", "changed", "checked"])
        self.assertEqual(status["behind"], 2)
        self.assertEqual(status["changed"], [])
        self.assertIsNotNone(datetime.datetime.fromisoformat(status["checked"]).tzinfo)
        git(repo.memory, "merge", "-q", "--ff-only", "origin/main")
        self.assertEqual(serve_boards.memory_status(repo.memory)["behind"], 0)

    def test_changed_lists_tracked_files_changed_or_staged_and_never_untracked_ones(self):
        repo = MemoryCheckout(self.base)
        (repo.memory / "note-00.md").write_text("changed\n", encoding="utf-8")
        (repo.memory / "note-01.md").write_text("staged\n", encoding="utf-8")
        git(repo.memory, "add", "note-01.md")
        (repo.memory / "untracked.md").write_text("new\n", encoding="utf-8")
        status = serve_boards.memory_status(repo.memory)
        self.assertEqual(status["behind"], 2)
        self.assertEqual(status["changed"], ["note-00.md", "note-01.md"])

    def test_changed_holds_at_most_twenty_paths(self):
        repo = MemoryCheckout(self.base, files=25)
        for n in range(25):
            (repo.memory / ("note-%02d.md" % n)).write_text("changed\n", encoding="utf-8")
        self.assertEqual(len(serve_boards.memory_status(repo.memory)["changed"]), 20)

    def test_a_git_failure_gives_behind_null_and_an_error_only(self):
        plain = self.base / "not-a-repository"
        plain.mkdir()
        status = serve_boards.memory_status(plain)
        self.assertEqual(sorted(status), ["behind", "error"])
        self.assertIsNone(status["behind"])
        self.assertTrue(status["error"])
        self.assertNotIn(str(plain), status["error"])    # git's own words, with paths, stay on the server

    def test_a_git_that_hangs_is_stopped_and_reported(self):
        repo = MemoryCheckout(self.base)
        with mock.patch.object(serve_boards.subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 5)):
            status = serve_boards.memory_status(repo.memory)
        self.assertEqual((status["behind"], sorted(status)), (None, ["behind", "error"]))


class StatusEndpointTests(unittest.TestCase):
    """The endpoint on a real socket, under the same Host and path rules as every page."""

    @classmethod
    def setUpClass(cls):
        cls.base = Path(tempfile.mkdtemp(prefix="serve-boards-status-"))
        cls.addClassCleanup(shutil.rmtree, cls.base, True)
        repo = MemoryCheckout(cls.base)
        site = Site(cls.base / "site")
        handler = type("H", (serve_boards.Handler,), {"table": site.table, "memory": repo.memory,
                                                       "log_message": lambda *a: None})
        cls.server = serve_boards.http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.server.shutdown)

    get = ServerTests.get

    def test_the_status_is_served_as_json_with_nothing_else_in_it(self):
        status, ctype, body = self.get("/_boards-status.json")
        self.assertEqual(status, 200)
        self.assertIn("application/json", ctype)
        data = json.loads(body)
        self.assertEqual(sorted(data), ["behind", "changed", "checked"])
        self.assertEqual(data["behind"], 2)

    def test_the_status_is_refused_to_another_host(self):
        self.assertEqual(self.get("/_boards-status.json", host="attacker.example")[0], 403)
        self.assertEqual(self.get("/_boards-status.json", host="127.0.0.1")[0], 200)

    def test_only_the_one_status_path_answers(self):
        self.assertEqual(self.get("/_boards-status.json?t=1")[0], 200)
        for path in ("/_boards-status.json/x", "/projects/_boards-status.json", "/_boards-status.jsonx"):
            with self.subTest(path=path):
                self.assertEqual(self.get(path)[0], 404)


if __name__ == "__main__":
    unittest.main()
