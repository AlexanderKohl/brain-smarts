"""Plant records of a fictional garden club: the module the split-file tests split."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
sys.path.insert(0, str(HERE / "vendor"))

import leafutil  # noqa: E402

NAME_RE = re.compile(r"^[A-Za-z ]{1,40}$")
MAX_BEDS = 12
_cache = None
started = leafutil.stamp()


@dataclass
class Plant:
    name: str
    kind: str = "herb"
    tags: list[str] = field(default_factory=list)


# Trims a plant name and checks it.
def clean_name(name: str) -> str:
    name = name.strip()
    if not NAME_RE.match(name):
        raise ValueError(name)
    return name


def describe(plant: Plant) -> str:
    return f"{plant.name} ({plant.kind})"


def watering_days(kind: str) -> int:
    return {"herb": 2, "tree": 7}.get(kind, 3)


def load_plants(path: Path | None = None) -> list[Plant]:
    path = path or DATA / "plants.json"
    return [Plant(**p) for p in json.loads(path.read_text(encoding="utf-8"))]


def cached_plants() -> list[Plant]:
    global _cache
    if _cache is None:
        _cache = load_plants()
    return _cache


def module_name() -> str:
    return __name__


def leaf_count(name: str) -> int:
    return leafutil.leaves(name)


def report() -> list[str]:
    return [f"{describe(p)} every {watering_days(p.kind)} days" for p in load_plants()]


if __name__ == "__main__":
    print("\n".join(report()))
