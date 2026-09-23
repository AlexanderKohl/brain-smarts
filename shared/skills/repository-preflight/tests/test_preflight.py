"""Behavioural tests for the repository preflight validator.

Every fixture is built fresh in a temporary directory from invented content: the owner is
"Example Owner", the project is "example-project", and no identifier is real (SMART-RULE-0008).

Run from the brain root:
    python -m unittest discover -s shared/skills/repository-preflight/tests -v
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import preflight  # noqa: E402

TS = "2026-01-01T09:00:00+10:00"
HAS_GIT = shutil.which("git") is not None


def md(identifier: str, body: str = "", **fields: object) -> str:
    """A Markdown file with valid required front matter plus extra fields."""
    lines = [
        "---",
        f"id: {identifier}",
        f"title: {identifier}",
        f"type: {fields.pop('type', 'note')}",
        "schema_version: 0.2",
        "contract: /CONTRACT.md",
        f"created: {TS}",
        f"updated: {TS}",
    ]
    for key, value in fields.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + textwrap.dedent(body)


def readme(identifier: str, folders: list[str], **fields: object) -> str:
    body = "#### Folders\n\n" + "".join(f"##### `{name}/`\n\nA folder.\n\n" for name in folders)
    return md(identifier, body, type="node_readme", **fields)


class Brain:
    """A fictional two-repository brain in a temporary directory."""

    def __init__(self, with_memory: bool = True, contract_version: str = "1.0.0") -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "brain"
        self.root.mkdir()
        self.version = contract_version
        self.write("CONTRACT.md", md("brain-contract", "# Contract\n", type="contract",
                                     contract_version=contract_version, owner="brain-owner"))
        self.write("RULES.md", md("brain-root-rules", "# Rules\n", type="rules", owner="brain-owner"))
        self.write("shared/README.md", readme("shared-readme", []))
        folders = ["shared"] + (["memory"] if with_memory else [])
        self.write("README.md", readme("brain-root-readme", folders, owner="brain-owner"))
        self.write_manifest("repository-manifest.json")
        if with_memory:
            self.add_memory()

    def add_memory(self) -> None:
        self.write("memory/README.md", readme("memory-readme", ["tasks"], owner="Example Owner"))
        self.write("memory/OWNER.md", md("owner-profile", "# Owner\n", type="owner_profile",
                                         owner="Example Owner", owner_name="Example Owner"))
        self.write("memory/RULES.md", md("owner-rules", "# Owner rules\n", type="rules"))
        self.write("memory/tasks/README.md", readme("tasks-readme", ["open"]))
        self.write("memory/tasks/open/README.md", readme("tasks-open-readme", []))
        self.write("memory/tasks/STATE.md", md("tasks-state", "# State\n\n| Task | Status |\n|---|---|\n",
                                               type="state"))
        self.write_manifest("memory/repository-manifest.json")

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def write_manifest(self, relative: str) -> None:
        self.write(relative, json.dumps({"contract_version": self.version}) + "\n")

    def run(self, writing: bool = False) -> preflight.Result:
        return preflight.run(self.root, writing)

    def close(self) -> None:
        self._tmp.cleanup()


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=Example Tester", "-c", "user.email=tester@example.com",
         "-c", "commit.gpgsign=false", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    )


def init_repo(repo: Path) -> None:
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "fixture")


class BrainTestCase(unittest.TestCase):
    def make(self, **kwargs: object) -> Brain:
        brain = Brain(**kwargs)  # type: ignore[arg-type]
        self.addCleanup(brain.close)
        return brain


class LayoutTests(BrainTestCase):
    def test_mechanics_alone_passes_with_a_memory_absent_warning(self) -> None:
        result = self.make(with_memory=False).run()
        self.assertEqual(result.errors, [])
        self.assertFalse(result.memory_present)
        self.assertTrue(any("memory checkout absent" in w for w in result.warnings))

    def test_mechanics_with_memory_passes_and_validates_memory_files(self) -> None:
        brain = self.make()
        result = brain.run()
        self.assertEqual(result.errors, [], result.errors)
        self.assertTrue(result.memory_present)
        self.assertGreater(result.layer_markdown_files["memory"], 0)

    def test_memory_file_without_front_matter_is_an_error(self) -> None:
        brain = self.make()
        brain.write("memory/KNOWLEDGE.md", "# No front matter\n")
        result = brain.run()
        self.assertIn("/memory/KNOWLEDGE.md: missing opening YAML delimiter", result.errors)

    def test_raw_evidence_in_memory_is_exempt(self) -> None:
        brain = self.make()
        brain.write("memory/raw/2026/01/source-0001/original.md", "evidence, no front matter\n")
        self.assertEqual(brain.run().errors, [])

    def test_root_raw_folder_is_still_exempt_for_a_single_repository_brain(self) -> None:
        brain = self.make(with_memory=False)
        brain.write("raw/2026/01/source-0001/original.md", "evidence\n")
        self.assertEqual(brain.run().errors, [])

    def test_duplicate_id_across_the_two_repositories_is_an_error(self) -> None:
        brain = self.make()
        brain.write("shared/NOTE.md", md("same-id"))
        brain.write("memory/NOTE.md", md("same-id"))
        errors = brain.run().errors
        self.assertTrue(any(e.startswith("duplicate id same-id") and "/memory/NOTE.md" in e
                            for e in errors), errors)

    def test_undocumented_memory_folder_is_warned_on_the_root_readme(self) -> None:
        brain = self.make(with_memory=False)
        (brain.root / "memory").mkdir()
        warnings = brain.run().warnings
        self.assertIn("/README.md: undocumented immediate folders: memory", warnings)

    def test_discover_root_from_inside_memory_finds_the_mechanics_root(self) -> None:
        brain = self.make()
        self.assertEqual(preflight.discover_root(brain.root / "memory" / "tasks"), brain.root.resolve())

    def test_a_lone_memory_checkout_is_reported_as_such(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lone = Path(tmp) / "memory"
            lone.mkdir()
            (lone / "OWNER.md").write_text(md("owner-profile"), encoding="utf-8")
            with self.assertRaisesRegex(FileNotFoundError, "looks like a memory checkout"):
                preflight.discover_root(lone)


class ReferenceTests(BrainTestCase):
    def test_memory_reference_resolves_into_the_memory_checkout(self) -> None:
        brain = self.make()
        brain.write("memory/projects/example-project/README.md", readme("example-project-readme", []))
        brain.write("memory/NOTE.md", md("note", project_refs=["/memory/projects/example-project"]))
        self.assertEqual(brain.run().errors, [])

    def test_broken_memory_reference_is_an_error_when_memory_is_present(self) -> None:
        brain = self.make()
        brain.write("memory/NOTE.md", md("note", project_refs=["/memory/projects/missing"]))
        self.assertIn("/memory/NOTE.md: broken project_refs reference /memory/projects/missing",
                      brain.run().errors)

    def test_memory_reference_is_a_warning_not_an_error_when_memory_is_absent(self) -> None:
        brain = self.make(with_memory=False)
        brain.write("shared/NOTE.md", md("note", source_refs=["/memory/sources/source-0001.md"]))
        result = brain.run()
        self.assertEqual(result.errors, [])
        self.assertTrue(any("/memory/sources/source-0001.md not checked" in w for w in result.warnings))

    def test_memory_file_may_reference_a_mechanics_skill(self) -> None:
        brain = self.make()
        brain.write("shared/skills/example-skill/SKILL.md", md("skill-example", type="skill"))
        brain.write("shared/skills/README.md", readme("skills-readme", ["example-skill"]))
        brain.write("shared/README.md", readme("shared-readme", ["skills"]))
        brain.write("memory/NOTE.md", md("note", skill_refs=["/shared/skills/example-skill"]))
        self.assertEqual(brain.run().errors, [])

    def test_anchor_must_match_a_heading_start(self) -> None:
        brain = self.make()
        brain.write("memory/LOG.md", md("log", "## 2026-01-01T09:00:00+10:00 Example entry\n", type="log"))
        brain.write("memory/A.md", md("a", source_refs=["/memory/LOG.md#2026-01-01T09:00:00+10:00"]))
        brain.write("memory/B.md", md("b", source_refs=["/memory/LOG.md#2026-01-02T09:00:00+10:00"]))
        errors = brain.run().errors
        self.assertNotIn("/memory/A.md: broken source_refs anchor /memory/LOG.md#2026-01-01T09:00:00+10:00", errors)
        self.assertIn("/memory/B.md: broken source_refs anchor /memory/LOG.md#2026-01-02T09:00:00+10:00", errors)

    def test_skeleton_templates_are_not_reference_checked(self) -> None:
        brain = self.make(with_memory=False)
        brain.write("shared/templates/memory-skeleton/NOTE.md",
                    md("template-note", project_refs=["/memory/projects/not-yet"]))
        brain.write("shared/templates/README.md", readme("templates-readme", ["memory-skeleton"]))
        brain.write("shared/README.md", readme("shared-readme", ["templates"]))
        result = brain.run()
        self.assertEqual(result.errors, [])
        self.assertFalse(any("not-yet" in w for w in result.warnings))

    def add_skeleton(self, brain: Brain) -> None:
        brain.write("shared/templates/memory-skeleton/projects/example-project/README.md",
                    readme("template-example-project-readme", []))

    def test_mechanics_reference_to_a_path_the_skeleton_provides_passes(self) -> None:
        brain = self.make()
        self.add_skeleton(brain)
        brain.write("memory/projects/example-project/README.md", readme("example-project-readme", []))
        brain.write("shared/NOTE.md", md("note", project_refs=["/memory/projects/example-project"]))
        self.assertEqual(brain.run().errors, [])

    def test_mechanics_reference_to_an_owner_specific_memory_path_is_an_error(self) -> None:
        brain = self.make()
        self.add_skeleton(brain)
        # It resolves in this owner's memory, but another owner's memory would not have it.
        brain.write("memory/sources/source-0001.md", md("source-0001"))
        brain.write("shared/NOTE.md", md("note", source_refs=["/memory/sources/source-0001.md"]))
        errors = brain.run().errors
        self.assertTrue(any(e.startswith("/shared/NOTE.md: source_refs reference /memory/sources/source-0001.md "
                                         "is an owner-specific memory path")
                            and "owner's memory copy" in e for e in errors), errors)

    def test_owner_specific_reference_is_an_error_even_without_memory(self) -> None:
        brain = self.make(with_memory=False)
        self.add_skeleton(brain)
        brain.write("shared/NOTE.md", md("note", evidence=["/memory/projects/owner-only/LOG.md"]))
        self.assertTrue(any("/memory/projects/owner-only/LOG.md is an owner-specific memory path" in e
                            for e in brain.run().errors))

    def test_memory_file_may_reference_owner_specific_memory_paths(self) -> None:
        brain = self.make()
        self.add_skeleton(brain)
        brain.write("memory/sources/source-0001.md", md("source-0001"))
        brain.write("memory/NOTE.md", md("note", source_refs=["/memory/sources/source-0001.md"]))
        self.assertEqual(brain.run().errors, [])

    def test_unindented_list_items_are_read(self) -> None:
        brain = self.make()
        brain.write("memory/NOTE.md", md("note").replace(
            f"updated: {TS}\n---", f"updated: {TS}\nsource_refs:\n- /memory/projects/missing\n---"))
        self.assertIn("/memory/NOTE.md: broken source_refs reference /memory/projects/missing",
                      brain.run().errors)


class IgnoredPathTests(BrainTestCase):
    def test_scratch_folder_is_skipped_without_git(self) -> None:
        brain = self.make()
        brain.write("temp/run/NOTES.md", "# scratch, no front matter\n")
        self.assertEqual(brain.run().errors, [])

    @unittest.skipUnless(HAS_GIT, "git is not available")
    def test_git_ignored_markdown_is_skipped_in_both_repositories(self) -> None:
        brain = self.make()
        brain.write(".gitignore", "memory/\nscratch-*/\n")
        brain.write("memory/.gitignore", "local/\n")
        init_repo(brain.root)
        init_repo(brain.root / "memory")
        brain.write("scratch-probe/NOTES.md", "# no front matter\n")
        brain.write("memory/local/NOTES.md", "# no front matter\n")
        self.assertEqual(brain.run().errors, [])

    @unittest.skipUnless(HAS_GIT, "git is not available")
    def test_reference_to_an_absent_git_ignored_file_is_a_warning(self) -> None:
        brain = self.make()
        brain.write("memory/.gitignore", "recordings/\n")
        brain.write(".gitignore", "memory/\n")
        brain.write("memory/NOTE.md", md("note", source_refs=["/memory/recordings/traffic-0001.json"]))
        init_repo(brain.root)
        init_repo(brain.root / "memory")
        result = brain.run()
        self.assertEqual(result.errors, [])
        self.assertTrue(any("/memory/recordings/traffic-0001.json not checked" in w and "git-ignored" in w
                            for w in result.warnings))


class TaskTests(BrainTestCase):
    def test_open_memory_task_missing_from_state_is_an_error(self) -> None:
        brain = self.make()
        brain.write("memory/tasks/open/TASK-2026-0001.md",
                    md("TASK-2026-0001", type="task", status="ready", owner="Example Owner"))
        self.assertIn("/memory/tasks/open/TASK-2026-0001.md: open task TASK-2026-0001 is not listed "
                      "in /memory/tasks/STATE.md", brain.run().errors)

    def test_open_memory_task_listed_with_its_status_passes(self) -> None:
        brain = self.make()
        brain.write("memory/tasks/open/TASK-2026-0001.md",
                    md("TASK-2026-0001", type="task", status="ready", owner="Example Owner"))
        brain.write("memory/tasks/STATE.md", md("tasks-state", "| `TASK-2026-0001` | **ready** |\n", type="state"))
        self.assertEqual(brain.run().errors, [])

    def test_open_task_listed_with_the_wrong_status_is_an_error(self) -> None:
        brain = self.make()
        brain.write("memory/tasks/open/TASK-2026-0001.md",
                    md("TASK-2026-0001", type="task", status="blocked", owner="Example Owner"))
        brain.write("memory/tasks/STATE.md", md("tasks-state", "| `TASK-2026-0001` | **ready** |\n", type="state"))
        self.assertIn("/memory/tasks/open/TASK-2026-0001.md: /memory/tasks/STATE.md lists TASK-2026-0001 "
                      "without its status word blocked", brain.run().errors)

    def test_waiting_task_requires_next_review(self) -> None:
        brain = self.make()
        brain.write("memory/tasks/completed/TASK-2026-0002.md",
                    md("TASK-2026-0002", type="task", status="waiting"))
        self.assertIn("/memory/tasks/completed/TASK-2026-0002.md: waiting task requires next_review",
                      brain.run().errors)

    def test_single_repository_task_store_is_still_checked(self) -> None:
        brain = self.make(with_memory=False)
        brain.write("tasks/STATE.md", md("tasks-state", type="state"))
        brain.write("tasks/open/TASK-2026-0003.md", md("TASK-2026-0003", type="task", status="ready"))
        self.assertIn("/tasks/open/TASK-2026-0003.md: open task TASK-2026-0003 is not listed in /tasks/STATE.md",
                      brain.run().errors)

    def test_task_template_in_the_skeleton_is_not_a_task(self) -> None:
        brain = self.make(with_memory=False)
        brain.write("shared/templates/memory-skeleton/tasks/templates/TASK_TEMPLATE.md",
                    md("template-TASK-YYYY-NNNN", type="task", status="waiting"))
        self.assertEqual(brain.run().errors, [])


class OwnerTripwireTests(BrainTestCase):
    def test_named_owner_in_a_mechanics_file_is_warned(self) -> None:
        brain = self.make()
        brain.write("shared/NOTE.md", md("note", owner="Example Owner"))
        self.assertIn("/shared/NOTE.md: mechanics file sets owner to a value other than brain-owner",
                      brain.run().warnings)

    def test_named_owner_in_a_memory_file_is_fine(self) -> None:
        brain = self.make()
        brain.write("memory/NOTE.md", md("note", owner="Example Owner"))
        self.assertFalse(any("/memory/NOTE.md" in w for w in brain.run().warnings))

    def test_single_repository_brain_is_not_tripped(self) -> None:
        brain = self.make(with_memory=False)
        brain.write("tasks/STATE.md", md("tasks-state", type="state"))
        brain.write("shared/NOTE.md", md("note", owner="Example Owner"))
        self.assertFalse(any("mechanics file sets owner" in w for w in brain.run().warnings))


class ManifestTests(BrainTestCase):
    def test_mechanics_manifest_version_mismatch_is_an_error(self) -> None:
        brain = self.make()
        brain.write("repository-manifest.json", json.dumps({"contract_version": "0.9.0"}))
        self.assertIn("/repository-manifest.json: contract_version does not match /CONTRACT.md",
                      brain.run().errors)

    def test_memory_manifest_version_mismatch_is_an_error(self) -> None:
        brain = self.make()
        brain.write("memory/repository-manifest.json", json.dumps({"contract_version": "0.9.0"}))
        self.assertIn("/memory/repository-manifest.json: contract_version does not match /CONTRACT.md",
                      brain.run().errors)

    def test_missing_memory_manifest_is_a_warning(self) -> None:
        brain = self.make()
        (brain.root / "memory" / "repository-manifest.json").unlink()
        result = brain.run()
        self.assertEqual(result.errors, [])
        self.assertTrue(any(w.startswith("/memory/repository-manifest.json: missing") for w in result.warnings))

    def test_write_manifest_keeps_memory_paths_out_of_the_mechanics_manifest(self) -> None:
        brain = self.make()
        brain.write("memory/projects/example-project/README.md", md("example-project-readme"))
        (brain.root / "memory" / "projects" / "example-project" / "undocumented").mkdir()
        brain.write("shared/extra/README.md", md("extra-readme"))
        (brain.root / "shared" / "extra" / "child").mkdir()
        brain.run(writing=True)
        mechanics = json.loads((brain.root / "repository-manifest.json").read_text(encoding="utf-8"))
        memory = json.loads((brain.root / "memory" / "repository-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(mechanics["layer"], "mechanics")
        self.assertEqual(memory["layer"], "memory")
        self.assertEqual(mechanics["contract_version"], "1.0.0")
        self.assertNotIn("/memory/", json.dumps(mechanics))
        self.assertTrue(any("example-project" in w for w in memory["validation_warnings"]))
        self.assertTrue(any("/shared/extra/README.md" in w for w in mechanics["validation_warnings"]))
        self.assertGreater(memory["markdown_files"], 0)
        # Once written, both manifests validate.
        self.assertFalse(any("manifest" in e for e in brain.run().errors))

    def test_write_manifest_uses_lf_line_endings(self) -> None:
        brain = self.make()
        brain.run(writing=True)
        for relative in ("repository-manifest.json", "memory/repository-manifest.json"):
            with self.subTest(manifest=relative):
                self.assertNotIn(b"\r\n", (brain.root / relative).read_bytes())

    def test_write_manifest_without_memory_writes_only_the_mechanics_manifest(self) -> None:
        brain = self.make(with_memory=False)
        brain.run(writing=True)
        self.assertTrue((brain.root / "repository-manifest.json").is_file())
        self.assertFalse((brain.root / "memory").exists())


class ProtectedPathTests(unittest.TestCase):
    def test_protection_by_path(self) -> None:
        cases = {
            "AGENTS.md": True,
            "BOOTSTRAP.md": True,
            "CONTRACT.md": True,
            "README.md": True,
            "RULES.md": True,
            "governance/README.md": False,
            "governance/proposals/example-change.md": False,
            "memory/README.md": False,
            "memory/RULES.md": True,
            "memory/governance/proposals/owner-example-change.md": False,
            "memory/projects/example-project/RULES.md": True,
            "memory/tasks/open/TASK-2026-0001.md": False,
            "shared/skills/example-skill/SKILL.md": False,
            "shared/skills/repository-preflight/scripts/preflight.py": True,
            "shared/templates/memory-skeleton/RULES.md": True,
            "shared/templates/node-RULES.template.md": True,
        }
        for path, expected in sorted(cases.items()):
            with self.subTest(path=path):
                self.assertEqual(preflight.is_protected(path), expected)


@unittest.skipUnless(HAS_GIT, "git is not available")
class GovernanceTests(BrainTestCase):
    def make_repos(self, memory_own_repo: bool = True) -> Brain:
        brain = self.make()
        brain.write(".gitignore", "memory/\n")
        init_repo(brain.root)
        if memory_own_repo:
            init_repo(brain.root / "memory")
        return brain

    def accepted_proposal(self, brain: Brain, relative: str, targets: list[str]) -> None:
        brain.write(relative, md("PROPOSAL-" + Path(relative).stem, type="governance_proposal", status="accepted",
                                 accepted_by="brain-owner", accepted_at=TS, target_files=targets))

    def test_clean_repositories_pass(self) -> None:
        self.assertEqual(self.make_repos().run().errors, [])

    def test_uncovered_mechanics_rules_change_is_an_error(self) -> None:
        brain = self.make_repos()
        brain.write("RULES.md", md("brain-root-rules", "# Rules\n\n- A new rule.\n", type="rules",
                                   owner="brain-owner"))
        self.assertIn("/RULES.md: changed protected governance is not covered by an accepted proposal",
                      brain.run().errors)

    def test_mechanics_change_covered_by_a_governance_proposal_passes(self) -> None:
        brain = self.make_repos()
        brain.write("RULES.md", md("brain-root-rules", "# Rules\n\n- A new rule.\n", type="rules",
                                   owner="brain-owner"))
        brain.write("governance/README.md", readme("governance-readme", ["proposals"]))
        brain.write("governance/proposals/README.md", readme("proposals-readme", []))
        self.accepted_proposal(brain, "governance/proposals/example-change.md", ["/RULES.md"])
        brain.write("README.md", readme("brain-root-readme", ["governance", "memory", "shared"],
                                        owner="brain-owner"))
        self.accepted_proposal(brain, "governance/proposals/readme-change.md", ["/README.md"])
        self.assertEqual(brain.run().errors, [])

    def test_uncovered_memory_rules_change_is_an_error(self) -> None:
        brain = self.make_repos()
        brain.write("memory/RULES.md", md("owner-rules", "# Owner rules\n\n- A preference.\n", type="rules"))
        self.assertIn("/memory/RULES.md: changed protected governance is not covered by an accepted proposal",
                      brain.run().errors)

    def test_memory_change_covered_by_a_memory_proposal_passes(self) -> None:
        brain = self.make_repos()
        brain.write("memory/RULES.md", md("owner-rules", "# Owner rules\n\n- A preference.\n", type="rules"))
        brain.write("memory/governance/proposals/README.md", readme("owner-proposals-readme", []))
        self.accepted_proposal(brain, "memory/governance/proposals/owner-example-change.md",
                               ["/memory/RULES.md"])
        errors = brain.run().errors
        self.assertFalse(any("changed protected governance" in e for e in errors), errors)

    def test_accepted_proposal_without_acceptance_evidence_is_an_error(self) -> None:
        brain = self.make_repos()
        brain.write("RULES.md", md("brain-root-rules", "# Rules\n\n- Changed.\n", type="rules",
                                   owner="brain-owner"))
        brain.write("governance/proposals/example-change.md",
                    md("PROPOSAL-example-change", type="governance_proposal", status="accepted",
                       target_files=["/RULES.md"]))
        self.assertIn("/governance/proposals/example-change.md: accepted proposal lacks "
                      "acceptance evidence", brain.run().errors)

    def test_memory_that_is_not_its_own_repository_is_a_warning(self) -> None:
        brain = self.make_repos(memory_own_repo=False)
        result = brain.run()
        self.assertEqual(result.errors, [])
        self.assertTrue(any("is not its own Git repository" in w for w in result.warnings))


if __name__ == "__main__":
    unittest.main()
