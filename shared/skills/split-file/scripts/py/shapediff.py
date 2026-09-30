"""Flattening and an ordered line comparison for shape snapshots: a moved line shows as removed in
one place and added in another.

Part of the split-file skill (canonical copy: /shared/skills/split-file/).
"""

from __future__ import annotations


def flatten(value, prefix: str = "", out: list[str] | None = None) -> list[str]:
    out = [] if out is None else out
    if isinstance(value, list):
        for v in value:
            if isinstance(v, (dict, list)):
                flatten(v, f"{prefix}[]", out)
            else:
                out.append(f"{prefix}: {v}")
    elif isinstance(value, dict):
        for key, v in value.items():
            flatten(v, f"{prefix} > {key}" if prefix else str(key), out)
    else:
        out.append(f"{prefix}: {value}")
    return out


def diff_lines(a: list[str], b: list[str]) -> list[str]:
    n, m = len(a), len(b)
    lcs = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            lcs[i][j] = lcs[i + 1][j + 1] + 1 if a[i] == b[j] else max(lcs[i + 1][j], lcs[i][j + 1])
    out, i, j = [], 0, 0
    while i < n and j < m:
        if a[i] == b[j]:
            i, j = i + 1, j + 1
        elif lcs[i + 1][j] >= lcs[i][j + 1]:
            out.append(f"- {a[i]}")
            i += 1
        else:
            out.append(f"+ {b[j]}")
            j += 1
    out += [f"- {x}" for x in a[i:]] + [f"+ {x}" for x in b[j:]]
    return out
