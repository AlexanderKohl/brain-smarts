#!/usr/bin/env python3
"""Generate the learning index and board from the learning records.

Commands:
  build [--out DIR] [--root DIR]   write index.md and board.md (default: the real learning folder)
  check [--dir DIR] [--root DIR]   build in memory; exit 1 when a committed view differs

The views are derived output. Nothing else writes them (SMART-RULE-0028, learning-maintenance skill).
Standard library only.
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

LEARNING_DIR = Path("memory/projects/brain-development/data/learning")
CATEGORY_ORDER = ["decisions-and-constraints", "goals-and-preferences", "observed-behaviour",
                  "recovery-methods", "working-methods"]
CATEGORY_LABEL = {"decisions-and-constraints": "Decisions and constraints",
                  "goals-and-preferences": "Goals and preferences",
                  "observed-behaviour": "Observed behaviour",
                  "recovery-methods": "Recovery methods",
                  "working-methods": "Working methods"}
ORDER_TEXT = "category, newest record first (created), then title"
DERIVED_RE = re.compile(r"^Derived at \S+ ")
UPDATED_RE = re.compile(r"^updated: .*$", re.M)
WEEKLY_LINE = ("- The weekly review's due date is held by its repeating reminder task in the "
               "brain-development task store and shown by `python shared/skills/tasks/scripts/tasks.py review`; "
               "these views carry no date.")
FOOTER = "This view is derived, not governance or a substitute for the evidence and owner decisions in each record."


def now_stamp(now=None):
    now = now or (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=10))
    return now.strftime("%Y-%m-%dT%H:%M:%S") + "+10:00"


def find_root(start=None):
    here = Path(start or __file__).resolve()
    for parent in [here] + list(here.parents):
        if (parent / "CONTRACT.md").is_file():
            return parent
    raise SystemExit("learning_views: no CONTRACT.md above " + str(here))


def parse_front_matter(text):
    """Return top-level key/value pairs; raise ValueError when the front matter is unusable."""
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("no front matter")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise ValueError("front matter is not closed")
    data = {}
    for line in lines[1:end]:
        if not line.strip() or line[0] in " \t-#":
            continue
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not m:
            raise ValueError("unreadable line: " + line[:60])
        value = m.group(2).strip()
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except ValueError:
                raise ValueError("bad quoted value for " + m.group(1))
        elif value.startswith("'") and value.endswith("'") and len(value) > 1:
            value = value[1:-1].replace("''", "'")
        data[m.group(1)] = value
    return data


def read_file(path):
    return Path(path).read_text(encoding="utf-8")


def collect_records(root):
    """Return (records, not_read) from every data/learnings folder under /memory/."""
    records, not_read = [], []
    for path in sorted((root / "memory").glob("**/data/learnings/*.md")):
        rel = "/" + path.relative_to(root).as_posix()
        try:
            text = read_file(path)
        except (OSError, UnicodeDecodeError) as exc:
            not_read.append((rel, "cannot read: " + str(exc)))
            continue
        if not re.search(r"^type:\s*learning\s*$", text.split("\n---", 1)[0], re.M):
            continue
        try:
            fm = parse_front_matter(text)
            if not fm.get("id") or not fm.get("title"):
                raise ValueError("id or title missing")
        except ValueError as exc:
            not_read.append((rel, str(exc)))
            continue
        fm["_path"] = rel
        records.append(fm)
    return records, not_read


def collect_digests(learning_dir):
    digests = []
    for path in sorted(learning_dir.glob("digest-*.md")):
        try:
            fm = parse_front_matter(read_file(path))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if fm.get("id"):
            digests.append(fm)
    return digests


def count_inbox(learning_dir):
    count = 0
    for path in sorted((learning_dir / "inbox").glob("*.md")):
        try:
            fm = parse_front_matter(read_file(path))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if fm.get("status") == "pending":
            count += 1
    return count


def category_key(record):
    slug = record.get("category", "")
    rank = CATEGORY_ORDER.index(slug) if slug in CATEGORY_ORDER else len(CATEGORY_ORDER)
    return rank, slug


def category_label(slug):
    return CATEGORY_LABEL.get(slug) or (slug.replace("-", " ").capitalize() if slug else "Uncategorised")


def review_cell(record):
    status = record.get("review_status", "unknown")
    independence = record.get("review_independence", "")
    cell = record.get("evidence_status", "unknown").split(",")[0].strip() or "unknown"
    if status != "reviewed":
        return cell + " / " + status
    if independence == "independent":
        return cell + " / reviewed, independent"
    if independence == "same_model":
        return cell + " / reviewed (same model)"
    if independence == "unknown":
        return cell + " / reviewed, independence unknown"
    return cell + " / reviewed (independence not recorded)"


def review_bucket(record):
    status = record.get("review_status", "unknown")
    if status != "reviewed":
        return status
    return {"independent": "reviewed independently", "same_model": "reviewed by the same model",
            "unknown": "reviewed with independence unknown"}.get(
                record.get("review_independence", ""), "reviewed with independence not recorded")


def cell_text(value):
    return value.replace("|", "\\|").replace("\n", " ")


def counts_line(records):
    buckets, evidence = {}, {}
    for r in records:
        buckets[review_bucket(r)] = buckets.get(review_bucket(r), 0) + 1
        ev = r.get("evidence_status", "unknown").split(",")[0].strip() or "unknown"
        evidence[ev] = evidence.get(ev, 0) + 1
    review = ", ".join("%d %s" % (n, k) for k, n in sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0])))
    ev = ", ".join("%d %s" % (n, k) for k, n in sorted(evidence.items(), key=lambda kv: (-kv[1], kv[0])))
    return "- Records: %d; %s. Evidence: %s. Review status does not imply empirical confirmation." % (
        len(records), review or "none", ev or "none")


def digest_line(digests):
    if not digests:
        return "- Digests: none recorded."
    parts = []
    for d in sorted(digests, key=lambda d: d.get("id", "")):
        if d.get("delivery_status") == "delivered" and d.get("delivered"):
            parts.append("`%s` delivered %s" % (d["id"], d["delivered"]))
        else:
            parts.append("`%s` is %s and not yet delivered" % (d["id"], d.get("delivery_status") or "of unknown status"))
    return "- Digests: " + "; ".join(parts) + ". These views are not a delivered digest."


def inbox_line(count):
    if count == 0:
        return "- Inbox: no pending artifacts. Inspect the inbox at integration checkpoints."
    return "- Inbox: %d pending artifact(s) in `/memory/projects/brain-development/data/learning/inbox/`; inspect them at integration checkpoints." % count


def sorted_records(records):
    by_title = sorted(records, key=lambda r: r["title"].lower())
    by_created = sorted(by_title, key=lambda r: r.get("created", ""), reverse=True)
    return sorted(by_created, key=category_key)


def build_views(root, now=None):
    """Return (views, problems): views maps file name to body text without front matter."""
    learning_dir = root / LEARNING_DIR
    records, not_read = collect_records(root)
    digests = collect_digests(learning_dir)
    inbox = count_inbox(learning_dir)
    problems = ["not read: %s (%s)" % item for item in not_read]
    rows = []
    for r in sorted_records(records):
        action = (r.get("next_action") or "").strip()
        if not action:
            problems.append("next_action missing: " + r["_path"])
            action = "not set"
        rows.append((category_label(r.get("category", "")), r, action))
    stamp = now_stamp(now)
    header = ["Derived at %s from canonical learning records. Order: %s." % (stamp, ORDER_TEXT), "",
              "- Any session may integrate in its own working copy under SMART-RULE-0038. There is no designated writer or learning lock.",
              counts_line(records), digest_line(digests), WEEKLY_LINE, inbox_line(inbox)]
    for path, reason in not_read:
        header.append("- Not read: %s (%s)" % (path, reason))
    views = {}
    for name, with_id in (("index.md", True), ("board.md", False)):
        title = "Learning discovery index" if with_id else "Learning review board"
        table = ["| Category | Learning ID | Canonical home | Evidence / review | Next action |", "|---|---|---|---|---|"] \
            if with_id else ["| Category | Learning | Evidence / review | Next action |", "|---|---|---|---|"]
        for cat, r, action in rows:
            link = "[%s](%s)" % (cell_text(r["title"]), r["_path"])
            cells = [cat, r["id"], link] if with_id else [cat, link]
            table.append("| " + " | ".join(cells + [review_cell(r), cell_text(action)]) + " |")
        views[name] = "# %s\n\n%s\n\n%s\n\n%s\n" % (title, "\n".join(header), "\n".join(table), FOOTER)
    return views, problems


def front_matter(name, created, updated):
    ident, title = (("brain-learning-index", "Learning discovery index") if name == "index.md"
                    else ("brain-learning-board", "Learning review board"))
    return ("---\nid: %s\ntitle: %s\ntype: generated\nschema_version: 0.2\ncontract: /CONTRACT.md\n"
            "created: %s\nupdated: %s\n---\n\n") % (ident, title, created, updated)


def mask(text):
    text = UPDATED_RE.sub("updated: -", text, count=1)
    return "\n".join("Derived at - " if DERIVED_RE.match(line) else line for line in text.split("\n"))


def existing_created(path, default):
    try:
        return parse_front_matter(read_file(path)).get("created") or default
    except (OSError, UnicodeDecodeError, ValueError):
        return default


def render(name, body, created, updated):
    return front_matter(name, created, updated) + body


def cmd_build(root, out_dir, now=None):
    views, problems = build_views(root, now)
    target = Path(out_dir) if out_dir else root / LEARNING_DIR
    target.mkdir(parents=True, exist_ok=True)
    stamp = now_stamp(now)
    for name, body in views.items():
        path = target / name
        fresh = render(name, body, existing_created(path, stamp), stamp)
        if path.is_file() and mask(read_file(path)) == mask(fresh):
            print("%s: unchanged" % path)
            continue
        path.write_text(fresh, encoding="utf-8", newline="\n")
        print("%s: written" % path)
    for line in problems:
        print("problem: " + line)
    return 0


def first_difference(a, b):
    la, lb = mask(a).split("\n"), mask(b).split("\n")
    for i in range(max(len(la), len(lb))):
        x = la[i] if i < len(la) else "(end of file)"
        y = lb[i] if i < len(lb) else "(end of file)"
        if x != y:
            return i + 1, x[:160], y[:160]
    return None


def cmd_check(root, directory, now=None):
    views, problems = build_views(root, now)
    target = Path(directory) if directory else root / LEARNING_DIR
    failed = bool(problems)
    for line in problems:
        print("check: " + line)
    for name, body in views.items():
        path = target / name
        try:
            committed = read_file(path)
        except (OSError, UnicodeDecodeError) as exc:
            print("check: %s cannot be read (%s)" % (path, exc))
            failed = True
            continue
        created = existing_created(path, "-")
        diff = first_difference(committed, render(name, body, created, "-"))
        if diff:
            failed = True
            print("check: %s differs from a fresh build at line %d\n  committed: %s\n  fresh:     %s" % (
                path, diff[0], diff[1], diff[2]))
    if not failed:
        print("check: index.md and board.md match the records")
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--out")
    b.add_argument("--root")
    c = sub.add_parser("check")
    c.add_argument("--dir")
    c.add_argument("--root")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else find_root()
    if args.command == "build":
        return cmd_build(root, args.out)
    return cmd_check(root, args.dir)


if __name__ == "__main__":
    sys.exit(main())
