"""Team lanes on the boards: the team tag, who holds an in-progress card, and the WIP line per team.

Run from the brain root:
    python -m unittest discover -s shared/skills/owner-board/scripts/tests -v

Everything below is fictional.
"""

from __future__ import annotations

import datetime
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import board_config  # noqa: E402
import build_boards  # noqa: E402
import build_status  # noqa: E402
import task_board  # noqa: E402
import team_lanes  # noqa: E402
from board_fixtures import Brain, quiet  # noqa: E402

TODAY = datetime.date(2026, 1, 10)
NOW = datetime.datetime(2026, 1, 10, 9, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=10)))

TASK = """---
id: {id}
title: Fictional task {id}
type: task
schema_version: 0.2
contract: /CONTRACT.md
status: {status}
owner: Sam
priority: normal
created: 2026-01-02T09:00:00+10:00
updated: 2026-01-02T09:00:00+10:00
due: null
next_review: null
waiting_on: null
project_refs:
  - /memory/projects/example-garden
team: {team}
claimed_by: {by}
claimed_at: {at}
---

# Fictional task {id}
"""


class Record:
    def __init__(self, **fields):
        self.fields = fields

    def get(self, key):
        return self.fields.get(key)


class TeamLanesUnitTests(unittest.TestCase):
    """The helpers on their own: colour choice, elapsed time, the lines."""

    def test_a_team_always_gets_the_same_one_of_six_colours(self):
        for label in ("alpha", "beta", "gamma", "delta-two", "x1"):
            first = team_lanes.team_index(label)
            self.assertEqual(first, team_lanes.team_index(label))
            self.assertTrue(0 <= first < 6)
            self.assertIn('class="tag team team-' + str(first) + '">' + label + "<", team_lanes.team_tag(label))
        spread = {team_lanes.team_index(label) for label in ("alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta")}
        self.assertGreater(len(spread), 2, "different labels spread over the palette")

    def test_the_palette_is_defined_for_both_themes_with_the_token_approach(self):
        for n in range(6):
            self.assertEqual(team_lanes.TOKENS.count("--team-" + str(n) + ":"), 3)   # light, dark media, data-theme
        self.assertIn('@media (prefers-color-scheme: dark)', team_lanes.TOKENS)
        self.assertIn(':root[data-theme="dark"]', team_lanes.TOKENS)
        self.assertIn(team_lanes.TOKENS, task_board.TOKENS)
        self.assertIn(".lane.over { color:var(--warn)", task_board.CSS)

    def test_how_long_ago(self):
        stamps = [(0, "just now"), (59, "just now"), (60, "1 min ago"), (45 * 60, "45 min ago"),
                  (3 * 3600 + 20, "3 h ago"), (47 * 3600, "47 h ago"), (48 * 3600, "2 d ago"), (10 * 86400, "10 d ago")]
        for seconds, text in stamps:
            self.assertEqual(team_lanes.ago(NOW - datetime.timedelta(seconds=seconds), NOW), text)

    def test_held_line_names_the_holder_and_the_elapsed_time(self):
        held = team_lanes.held_html(Record(claimed_by="Session <Blue>", claimed_at="2026-01-10T08:48:00+10:00"), NOW)
        self.assertIn("Held by Session &lt;Blue&gt; &middot; claimed 12 min ago", held)
        self.assertIn('data-claimed-at="2026-01-10T08:48:00+10:00"', held)
        self.assertEqual(team_lanes.held_html(Record(claimed_by=None), NOW), "")
        self.assertIn("claimed at an unknown time", team_lanes.held_html(Record(claimed_by="S", claimed_at="soon"), NOW))

    def test_wip_lines_count_in_progress_per_team_and_mark_the_excess(self):
        entries = [("alpha", "in_progress"), ("alpha", "in_progress"), ("alpha", "in_progress"), ("alpha", "ready"),
                   ("beta", "ready"), (None, "in_progress")]
        text = team_lanes.wip_lines(entries, 2)
        self.assertIn('<p class="lane over" data-team="alpha" data-in-progress="3" data-limit="2">', text)
        self.assertIn("&middot; in progress 3 / 2</p>", text)
        self.assertIn('<p class="lane" data-team="beta" data-in-progress="0" data-limit="2">', text)
        self.assertEqual(text.count('<p class="lane'), 2)        # a card without a team is on no lane
        self.assertEqual(team_lanes.wip_lines([(None, "ready")], 2), "")


class TeamLanesBoardTests(unittest.TestCase):
    """The lanes as drawn on a generated board page."""

    def setUp(self):
        self.brain = Brain()
        for patch in (mock.patch.object(task_board, "local_today", return_value=TODAY),
                      mock.patch.object(team_lanes, "local_now", return_value=NOW)):
            patch.start()
            self.addCleanup(patch.stop)
        store = self.brain.memory / "tasks"
        (store / "open" / "TASK-2026-0901-beds.md").unlink()
        self.add("TASK-2026-0920", "ready", "alpha")
        self.add("TASK-2026-0921", "in_progress", "alpha", "Session Alpha One", "2026-01-10T08:30:00+10:00")
        self.add("TASK-2026-0922", "in_progress", "alpha", "Session Alpha Two", "2026-01-09T09:00:00+10:00")
        self.add("TASK-2026-0923", "in_progress", "alpha", "Session Alpha Three", "2026-01-10T08:59:30+10:00")
        self.add("TASK-2026-0924", "in_progress", "beta", "Session Beta", "2026-01-10T07:00:00+10:00")
        self.add("TASK-2026-0925", "ready", "null")
        self.add("TASK-2026-0926", "in_progress", "null")

    def tearDown(self):
        self.brain.close()

    def add(self, tid, status, team, by="null", at="null"):
        text = TASK.format(id=tid, status=status, team=team, by=by, at=at)
        (self.brain.memory / "tasks" / "open" / (tid + "-fictional.md")).write_text(text, encoding="utf-8")

    def set_wip_limit(self, limit):
        path = self.brain.memory / "skills" / "owner-board" / "config" / "boards.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("tasks", {})["wip_limit"] = limit
        path.write_text(json.dumps(data), encoding="utf-8")

    def page(self):
        config = self.brain.config()
        quiet(build_status.build, config, config.board("garden"), False)
        quiet(build_boards.build, config, None, "2026-01-10 09:00")
        text = (self.brain.memory / "projects/example-garden/status/status.html").read_text(encoding="utf-8")
        return text[text.index('<section class="tasks"'):text.index("</section>")]

    def card(self, section, tid):
        start = section.index('data-task="' + tid + '"')
        return section[start:section.index("</article>", start)]

    def test_every_card_shows_its_team_in_its_lane_colour(self):
        section = self.page()
        alpha = team_lanes.team_tag("alpha")
        for tid in ("TASK-2026-0920", "TASK-2026-0921", "TASK-2026-0922", "TASK-2026-0923"):
            self.assertIn(alpha, self.card(section, tid), tid)
        self.assertIn(team_lanes.team_tag("beta"), self.card(section, "TASK-2026-0924"))
        for tid in ("TASK-2026-0925", "TASK-2026-0926"):
            self.assertNotIn('class="tag team', self.card(section, tid), tid)

    def test_an_in_progress_card_says_who_holds_it_and_since_when(self):
        section = self.page()
        self.assertIn("Held by Session Alpha One &middot; claimed 30 min ago", self.card(section, "TASK-2026-0921"))
        self.assertIn("Held by Session Alpha Two &middot; claimed 24 h ago", self.card(section, "TASK-2026-0922"))
        self.assertIn("Held by Session Alpha Three &middot; claimed just now", self.card(section, "TASK-2026-0923"))
        self.assertIn("Held by Session Beta &middot; claimed 2 h ago", self.card(section, "TASK-2026-0924"))
        self.assertNotIn("Held by", self.card(section, "TASK-2026-0926"))

    def test_the_wip_line_per_team_sits_above_the_columns_with_the_default_limit(self):
        section = self.page()
        lanes = section[section.index('<div class="lanes">'):section.index('<div class="tboard">')]
        self.assertIn('<p class="lane over" data-team="alpha" data-in-progress="3" data-limit="2">'
                      + team_lanes.team_tag("alpha") + " &middot; in progress 3 / 2</p>", lanes)
        self.assertIn('<p class="lane" data-team="beta" data-in-progress="1" data-limit="2">'
                      + team_lanes.team_tag("beta") + " &middot; in progress 1 / 2</p>", lanes)
        self.assertEqual(lanes.count('<p class="lane'), 2)
        self.assertEqual(board_config.TASKS_DEFAULTS["wip_limit"], 2)

    def test_the_limit_comes_from_boards_json(self):
        self.set_wip_limit(3)
        section = self.page()
        self.assertIn('<p class="lane" data-team="alpha" data-in-progress="3" data-limit="3">', section)
        self.assertNotIn("lane over", section)
        self.assertIn("in progress 3 / 3", section)

    def test_a_board_without_teams_draws_no_lanes_and_the_personal_page_draws_its_own(self):
        store = self.brain.memory / "tasks" / "open"
        for path in store.glob("TASK-2026-092*.md"):
            path.unlink()
        self.add("TASK-2026-0930", "ready", "null")
        self.assertNotIn('class="lanes"', self.page())
        # A personal-board task with a team is on the personal page's own lane line.
        text = TASK.format(id="TASK-2026-0931", status="in_progress", team="gamma", by="Session Gamma",
                           at="2026-01-10T08:00:00+10:00").replace("  - /memory/projects/example-garden", "  - /memory/projects/elsewhere")
        (store / "TASK-2026-0931-fictional.md").write_text(text, encoding="utf-8")
        config = self.brain.config()
        quiet(build_boards.build, config, None, "2026-01-10 09:00")
        personal = (self.brain.memory / "boards" / "personal.html").read_text(encoding="utf-8")
        self.assertIn('<p class="lane" data-team="gamma" data-in-progress="1" data-limit="2">', personal)
        self.assertIn("Held by Session Gamma &middot; claimed 1 h ago", personal)
        self.assertIn(team_lanes.TOKENS, personal)


if __name__ == "__main__":
    unittest.main()
