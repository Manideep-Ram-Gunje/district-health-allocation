"""Central paths, config loading and DB connection. Import this, never hardcode."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DATA_RAW = ROOT / "data" / "raw"
DATA_INTERIM = ROOT / "data" / "interim"
DATA_PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
SQL_DIR = ROOT / "sql"
MANIFEST = DATA_RAW / "MANIFEST.json"

for _d in (DATA_RAW, DATA_INTERIM, DATA_PROCESSED, REPORTS):
    _d.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / ".env")


@lru_cache(maxsize=None)
def load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def sources() -> dict:
    return load_yaml("sources.yml")["sources"]


def indicators() -> list[dict]:
    return load_yaml("indicators.yml")["indicators"]


def indicator_ids() -> list[int]:
    return [i["id"] for i in indicators()]


def weights(scheme: str | None = None) -> dict[str, float]:
    cfg = load_yaml("indicators.yml")
    scheme = scheme or cfg["default_scheme"]
    return cfg["weighting_schemes"][scheme]["weights"]


def raw_path(source_key: str) -> Path:
    return DATA_RAW / sources()[source_key]["filename"]


# --- database ---------------------------------------------------------------

def db_url() -> str:
    """SQLAlchemy URL. Override wholesale with DATABASE_URL if you prefer."""
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    user = os.getenv("PGUSER", "dhia")
    pwd = os.getenv("PGPASSWORD", "dhia")
    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5433")
    db = os.getenv("PGDATABASE", "dhia")
    return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"


def engine():
    from sqlalchemy import create_engine
    return create_engine(db_url(), future=True)
