"""A stand-in for a third-party module found through sys.path (split-file test fixture)."""


def stamp() -> int:
    return 1


def leaves(name: str) -> int:
    return len(name) * 3
