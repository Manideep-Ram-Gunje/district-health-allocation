"""Guard against environment drift.

Every third-party module the code imports must be declared in requirements.txt,
and every optional dependency the code relies on indirectly must be too. This
exists because `tabulate` — an optional dependency of `pandas.to_markdown()`
that is never imported by name — was present in the development environment and
absent from requirements, so Phase 2 ran clean in one place and crashed in
another after all the real work had succeeded.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CODE_DIRS = ["src", "tests", "app"]

# import name -> distribution name on PyPI
ALIASES = {
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "psycopg2": "psycopg2-binary",
    "sklearn": "scikit-learn",
    "PIL": "pillow",
    "pulp": "pulp",
    "fiona": "geopandas",     # pulled in by geopandas
    "shapely": "shapely",
}

STDLIB = {
    "__future__", "abc", "argparse", "collections", "contextlib", "csv",
    "dataclasses", "datetime", "decimal", "enum", "functools", "glob",
    "hashlib", "io", "itertools", "json", "logging", "math", "os", "pathlib",
    "random", "re", "shutil", "string", "subprocess", "sys", "tempfile",
    "textwrap", "time", "typing", "unicodedata", "urllib", "uuid", "warnings",
    "zipfile",
}

# pandas methods that need an undeclared-by-default package
IMPLICIT = {
    "to_markdown": "tabulate",
    "read_parquet": "pyarrow",
    "to_parquet": "pyarrow",
    "read_excel": "openpyxl",
}


def declared() -> set[str]:
    txt = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    out = set()
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.add(re.split(r"[=<>!\[;]", line)[0].strip().lower())
    return out


def source_files() -> list[Path]:
    """All project Python files EXCEPT this one.

    Self-exclusion is not cosmetic: this module contains the literal strings
    'read_excel' and 'openpyxl' in its own lookup table, so scanning itself
    reports a dependency the project does not actually have.
    """
    me = Path(__file__).resolve()
    return [p for d in CODE_DIRS for p in (ROOT / d).rglob("*.py")
            if (ROOT / d).exists() and p.resolve() != me]


def imported_modules() -> set[str]:
    """Collect top-level imports by parsing the AST, not by regex.

    A regex over source text also matches SQL embedded in triple-quoted
    strings — `from core.district d join ...` reads as an import of a module
    called `core`, and `from r a join r b` as one called `r`. Parsing the
    syntax tree only ever sees real import statements.
    """
    mods: set[str] = set()
    for p in source_files():
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:      # skip relative imports
                    mods.add(node.module.split(".")[0])
    return {m for m in mods if m not in STDLIB and m != "src"}


def test_every_import_is_declared():
    missing = sorted(
        m for m in imported_modules()
        if ALIASES.get(m, m).lower() not in declared()
    )
    assert not missing, f"imported but not in requirements.txt: {missing}"


@pytest.mark.parametrize("method,package", sorted(IMPLICIT.items()))
def test_implicit_dependencies_are_declared(method: str, package: str):
    used = any(method in p.read_text(encoding="utf-8") for p in source_files())
    if not used:
        pytest.skip(f"{method} not used")
    assert package in declared(), (
        f"code calls .{method}() which needs '{package}', "
        f"but it is not in requirements.txt")
