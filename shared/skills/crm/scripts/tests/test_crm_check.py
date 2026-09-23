"""Tests for crm_check.py and for the starter node staying in step with the skill templates.

Run from the brain root:
    python -m unittest discover -s shared/skills/crm/scripts/tests -v

Every name, address and number below is fictional.
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
SKILL = SCRIPTS.parent
SMARTS = SKILL.parents[2]
sys.path.insert(0, str(SCRIPTS))

import crm_check  # noqa: E402

STAMP = "2026-01-05T09:00:00+10:00"


def contact(cid: str, title: str, **fields: str) -> str:
    meta = {
        "id": cid,
        "title": title,
        "type": "contact",
        "schema_version": "0.2",
        "contract": "/CONTRACT.md",
        "contact_kind": "person",
        "preferred_reply_persona": "null",
        "newsletter": "false",
        "newsletter_read_detail": "null",
        "receiving_personas": "[]",
        "emails": "[]",
        "phones": "[]",
        "created": STAMP,
        "updated": STAMP,
    }
    meta.update(fields)
    lines = "\n".join(f"{k}: {v}" for k, v in meta.items())
    return f"---\n{lines}\n---\n\n# {title}\n\n## Notes\n\n- 2026-01-05: fictional.\n"


def persona(key: str) -> str:
    return (
        f"---\nid: persona-{key}\ntitle: {key}\ntype: persona\nschema_version: 0.2\n"
        f"contract: /CONTRACT.md\npersona_key: {key}\ncompany: personal\n"
        f"google_account_alias: personal\ncreated: {STAMP}\nupdated: {STAMP}\n---\n\n# {key}\n"
    )


def run(*argv: str, cwd: Path) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = crm_check.main(list(argv), cwd=cwd)
    return code, out.getvalue()


class CrmCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="brain-crm-"))
        (self.root / "CONTRACT.md").write_text("---\nid: contract\n---\n", encoding="utf-8")
        self.node = self.root / "memory" / "projects" / "contacts"
        (self.node / "contacts").mkdir(parents=True)
        (self.node / "personas").mkdir()
        self.write("personas/persona-personal.md", persona("personal"))
        self.write(
            "contacts/contact-ada-example.md",
            contact(
                "contact-ada-example",
                "Ada Example",
                emails="\n  - " + "ada@example.com".title(),
                phones="\n  - +99-555-010-001",
                preferred_reply_persona="personal",
                receiving_personas="[personal]",
            ),
        )
        self.write(
            "contacts/contact-example-plumbing-news.md",
            contact(
                "contact-example-plumbing-news",
                "Example Plumbing News",
                contact_kind="newsletter",
                newsletter="true",
                newsletter_read_detail="subject",
                emails="[news@example.net]",
            ),
        )
        self.write("contacts/_TEMPLATE.md", contact("template", "TEMPLATE", contact_kind="bogus"))

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel: str, text: str) -> None:
        (self.node / rel).write_text(text, encoding="utf-8")

    def test_clean_register_validates_and_template_is_ignored(self) -> None:
        code, out = run("validate", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("PASS: 0 error(s), 0 warning(s)", out)

    def test_default_node_is_found_from_the_brain_root(self) -> None:
        self.assertEqual(crm_check.resolve_node(None, self.root / "memory"), self.node)

    def test_google_config_names_the_node(self) -> None:
        other = self.root / "memory" / "projects" / "register"
        shutil.copytree(self.node, other)
        config = self.root.joinpath(*crm_check.GOOGLE_CONFIG)
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"crm_root": "/memory/projects/register"}), encoding="utf-8")
        self.assertEqual(crm_check.resolve_node(None, self.root), other)
        self.assertEqual(crm_check.resolve_node("/memory/projects/contacts", self.root), self.node)

    def test_newsletter_needs_read_detail(self) -> None:
        self.write(
            "contacts/contact-example-offers.md",
            contact("contact-example-offers", "Example Offers", contact_kind="newsletter"),
        )
        code, out = run("validate", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("contact-example-offers.md: newsletter needs newsletter_read_detail", out)

    def test_unknown_persona_kind_and_id_mismatch_are_errors(self) -> None:
        self.write(
            "contacts/contact-bo-sample.md",
            contact(
                "contact-bo-sampel",
                "Bo Sample",
                contact_kind="friend",
                preferred_reply_persona="example-company",
            ),
        )
        code, out = run("validate", cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("unknown contact_kind friend", out)
        self.assertIn("unknown persona example-company", out)
        self.assertIn("does not match the file name", out)

    def test_newsletter_reply_persona_is_a_warning(self) -> None:
        self.write(
            "contacts/contact-example-digest.md",
            contact(
                "contact-example-digest",
                "Example Digest",
                contact_kind="newsletter",
                newsletter_read_detail="body",
                preferred_reply_persona="personal",
            ),
        )
        code, out = run("validate", cwd=self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("WARN: contacts/contact-example-digest.md: newsletter has preferred_reply_persona", out)

    def test_find_by_email_phone_and_name(self) -> None:
        for argv in (
            ("find", "--email", "ada@example.com"),
            ("find", "--phone", "0555 010 001"),
            ("find", "--name", "ada"),
            ("find", "--name", "Ada", "--email", "ada@example.com".upper()),
        ):
            code, out = run(*argv, cwd=self.root)
            self.assertEqual(code, 0)
            self.assertIn("contact-ada-example\tAda Example", out, argv)
            self.assertIn("1 match(es)", out, argv)
        _, out = run("find", "--name", "ada", "--email", "news@example.net", cwd=self.root)
        self.assertIn("0 match(es)", out)

    def test_duplicates_by_email_and_name(self) -> None:
        self.write(
            "contacts/contact-ada-example-2.md",
            contact("contact-ada-example-2", "Ada  Example", emails="[ada@example.com]"),
        )
        code, out = run("--json", "duplicates", cwd=self.root)
        self.assertEqual(code, 1)
        groups = json.loads(out)
        self.assertEqual(
            {(g["by"], g["value"]) for g in groups},
            {("email", "ada@example.com"), ("name", "ada example")},
        )
        for group in groups:
            self.assertEqual(group["contacts"], ["contact-ada-example", "contact-ada-example-2"])

    def test_missing_node_exits_2(self) -> None:
        code, out = run("--node", "/memory/projects/nowhere", "validate", cwd=self.root)
        self.assertEqual(code, 2)
        self.assertIn("CRM node not found", out)

    def test_a_node_path_rewritten_by_git_bash_names_the_fix(self) -> None:
        code, out = run("--node", "C:/Program Files/Git/memory/projects/contacts", "validate", cwd=self.root)
        self.assertEqual(code, 2)
        self.assertIn("MSYS_NO_PATHCONV=1", out)


class StarterNodeInStepTest(unittest.TestCase):
    """The memory skeleton's starter node is a copy of the skill templates, ids aside."""

    PAIRS = {
        "node-README.template.md": "README.md",
        "node-RULES.template.md": "RULES.md",
        "contact.template.md": "contacts/_TEMPLATE.md",
        "persona.template.md": "personas/_TEMPLATE.md",
    }

    def test_templates_match(self) -> None:
        starter = SMARTS / "shared" / "templates" / "memory-skeleton" / "projects" / "contacts"
        for template, copy in self.PAIRS.items():
            source = (SKILL / "templates" / template).read_text(encoding="utf-8").splitlines()
            target = (starter / copy).read_text(encoding="utf-8").splitlines()
            strip = lambda lines: [line for line in lines if not line.startswith("id: ")]  # noqa: E731
            self.assertEqual(strip(source), strip(target), f"{template} differs from {copy}")
            self.assertTrue(any(line.startswith("id: template-contacts-") for line in target), copy)


if __name__ == "__main__":
    unittest.main()
