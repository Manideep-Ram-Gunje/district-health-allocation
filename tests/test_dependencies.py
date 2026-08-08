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


REQUIREMENTS_FILES = ["requirements.txt", "requirements-pipeline.txt"]


def declared() -> set[str]:
    """Every package declared across ALL requirements files.

    Dependencies are split deliberately: `requirements.txt` is the small set a
    DEPLOYMENT installs (Streamlit Cloud reads that filename and offers no way
    to point elsewhere), while `requirements-pipeline.txt` adds the heavy
    pipeline-only packages — geopandas, psycopg2, scikit-learn, pytest.

    Checking only the root file would report every pipeline import as
    undeclared, which is exactly what happened when the split was introduced.
    """
    out = set()
    for fname in REQUIREMENTS_FILES:
        path = ROOT / fname
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-r"):
                continue
            out.add(re.split(r"[=<>!\[;]", line)[0].strip().lower())
    return out


def test_deployment_requirements_stay_lean():
    """The root file must NOT contain the geospatial or database stack.

    Streamlit Cloud installs requirements.txt and nothing else. geopandas and
    fiona pull in GDAL system libraries, which is the most common cause of a
    failed cloud build — and the deployed app never imports them, because it
    reads the pre-simplified snapshot geojson as plain JSON.
    """
    root = set()
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("-r"):
            root.add(re.split(r"[=<>!\[;]", line)[0].strip().lower())
    forbidden = {"geopandas", "fiona", "psycopg2-binary", "psycopg2",
                 "scikit-learn", "gdal"}
    leaked = root & forbidden
    assert not leaked, (
        f"{sorted(leaked)} must live in requirements-pipeline.txt, not the root "
        "file — they break the Streamlit Cloud build and the app never uses them")


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
