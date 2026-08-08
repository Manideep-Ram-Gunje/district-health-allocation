-- ===========================================================================
-- District Health Infrastructure Allocation System — base schema
--
-- Two schemas, deliberately separated:
--   staging  verbatim copies of the source files. No cleaning, no casting.
--            If a number is a question mark in the PDF, it is a question mark
--            here. This is what lets us prove the transformation later.
--   core     modelled, typed, constrained. Everything downstream reads here.
--
-- Idempotent: re-running drops and rebuilds. Safe because nothing in this
-- database is authored by hand — it is all reconstructible from data/raw.
-- ===========================================================================

DROP SCHEMA IF EXISTS core CASCADE;
DROP SCHEMA IF EXISTS staging CASCADE;

CREATE SCHEMA staging;
CREATE SCHEMA core;

COMMENT ON SCHEMA staging IS 'Verbatim source data. Text columns throughout — no casting on load.';
COMMENT ON SCHEMA core    IS 'Modelled and constrained. The analytics layer reads only from here.';

-- ---------------------------------------------------------------------------
-- staging
-- ---------------------------------------------------------------------------

CREATE TABLE staging.nfhs5_raw (
    state           text,
    district        text,
    indicator_text  text,
    nfhs5           text,      -- text on purpose: source contains 'NA' and '*'
    nfhs4           text,
    flag_nfhs5      text,
    flag_nfhs4      text
);
COMMENT ON COLUMN staging.nfhs5_raw.nfhs5 IS
    'Left as text. The source encodes missingness as NA and small-sample suppression as *; casting on load would destroy the distinction.';

CREATE TABLE staging.census2011_raw (
    census_code      integer,
    census_state     text,
    census_district  text,
    population       bigint,
    rural_hh         bigint,
    urban_hh         bigint,
    total_hh         bigint
);

-- ---------------------------------------------------------------------------
-- core.indicator — the NFHS-5 factsheet indicator catalogue
--
-- Keyed on the factsheet NUMBER, not the name. Eight indicators have more than
-- one name string in the source because of PDF extraction artefacts, and one
-- of them (49, full immunisation) is in our index. Keying on name would split
-- that series in two. See docs/build-log.md, Phase 0 challenge 4.
-- ---------------------------------------------------------------------------

CREATE TABLE core.indicator (
    indicator_id       smallint PRIMARY KEY,
    indicator_key      text UNIQUE,          -- our short name; null if not in the index
    name_as_published  text NOT NULL,
    domain             text,                 -- maternal | child | nutrition
    higher_is_worse    boolean,
    in_index           boolean NOT NULL DEFAULT false,
    name_variants      smallint NOT NULL DEFAULT 1,
    CONSTRAINT indicator_id_range CHECK (indicator_id BETWEEN 1 AND 104),
    CONSTRAINT index_members_fully_specified CHECK (
        NOT in_index OR (indicator_key IS NOT NULL
                         AND domain IS NOT NULL
                         AND higher_is_worse IS NOT NULL)
    )
);
COMMENT ON COLUMN core.indicator.name_variants IS
    'Count of distinct name strings seen in the source for this number. >1 means PDF extraction noise.';

-- ---------------------------------------------------------------------------
-- core.district — one row per NFHS-5 district, with its Census 2011 lineage
-- ---------------------------------------------------------------------------

CREATE TABLE core.district (
    district_id        serial PRIMARY KEY,
    nfhs_state         text NOT NULL,
    nfhs_district      text NOT NULL,
    region             text NOT NULL,
    census_code        integer,
    census_state       text,
    census_district    text,
    match_tier         text NOT NULL,
    match_score        numeric(5,2),
    is_apportioned     boolean NOT NULL DEFAULT false,
    n_sharing_parent   smallint NOT NULL DEFAULT 1,
    population_alloc   bigint,
    rural_share        numeric(6,4),
    rural_population   bigint,
    UNIQUE (nfhs_state, nfhs_district),
    CONSTRAINT rural_not_exceeding_total CHECK (
        rural_population IS NULL OR population_alloc IS NULL
        OR rural_population <= population_alloc
    ),
    CONSTRAINT rural_share_is_a_share CHECK (
        rural_share IS NULL OR (rural_share >= 0 AND rural_share <= 1)
    ),
    CONSTRAINT apportioned_implies_siblings CHECK (
        is_apportioned = (n_sharing_parent > 1)
    )
);
COMMENT ON COLUMN core.district.is_apportioned IS
    'True where several NFHS-5 districts share one Census 2011 parent (a post-2011 split). Parent population is divided equally among children.';
COMMENT ON COLUMN core.district.region IS
    'Zonal Council grouping. Drives the minimum-one-facility-per-region equity constraint in Phase 3.';

CREATE INDEX district_state_idx  ON core.district (nfhs_state);
CREATE INDEX district_region_idx ON core.district (region);

-- ---------------------------------------------------------------------------
-- core.district_indicator — the long fact table, 705 x 104
-- ---------------------------------------------------------------------------

CREATE TABLE core.district_indicator (
    district_id   integer  NOT NULL REFERENCES core.district(district_id) ON DELETE CASCADE,
    indicator_id  smallint NOT NULL REFERENCES core.indicator(indicator_id),
    value_nfhs5   numeric(8,2),
    value_nfhs4   numeric(8,2),
    flag_nfhs5    text,
    PRIMARY KEY (district_id, indicator_id)
);
COMMENT ON TABLE core.district_indicator IS
    'NULL value_nfhs5 means genuinely absent OR suppressed for small sample size; flag_nfhs5 distinguishes the two.';

CREATE INDEX district_indicator_ind_idx ON core.district_indicator (indicator_id);

-- ---------------------------------------------------------------------------
-- core.weight_scheme — named weight vectors from config/indicators.yml
--
-- Stored in the database rather than only in YAML so the SQL analytics layer
-- can compute the Need Index without a round trip through Python, and so the
-- Streamlit app can offer schemes by name.
-- ---------------------------------------------------------------------------

CREATE TABLE core.weight_scheme (
    scheme         text NOT NULL,
    indicator_key  text NOT NULL REFERENCES core.indicator(indicator_key),
    weight         numeric(9,6) NOT NULL CHECK (weight >= 0),
    PRIMARY KEY (scheme, indicator_key)
);

-- ---------------------------------------------------------------------------
-- core.load_audit — provenance for the run that produced this database
-- ---------------------------------------------------------------------------

CREATE TABLE core.load_audit (
    loaded_at      timestamptz NOT NULL DEFAULT now(),
    source_key     text NOT NULL,
    filename       text,
    sha256         text,
    rows_loaded    bigint,
    PRIMARY KEY (loaded_at, source_key)
);
COMMENT ON TABLE core.load_audit IS
    'Which file, which checksum, how many rows. Makes "is this database current?" answerable.';
