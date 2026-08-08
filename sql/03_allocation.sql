-- ===========================================================================
-- Allocation results.
--
-- One row per (scenario, scheme, district) for every SELECTED district.
-- Scenarios are named strategies — 'optimal', 'greedy_feasible',
-- 'naive_top25' — so they can be compared with a single group-by rather than
-- by juggling CSV files.
-- ===========================================================================

DROP VIEW  IF EXISTS core.v_allocation_summary CASCADE;
DROP TABLE IF EXISTS core.allocation CASCADE;

CREATE TABLE core.allocation (
    scenario       text     NOT NULL,
    scheme         text     NOT NULL,
    district_id    integer  NOT NULL REFERENCES core.district(district_id),
    pick_rank      integer,
    need_index     numeric(10,8),
    coverage_gain  numeric(14,4),
    PRIMARY KEY (scenario, scheme, district_id)
);

COMMENT ON TABLE core.allocation IS
    'Selected districts per allocation scenario. Only winners are stored; absence means not selected.';
COMMENT ON COLUMN core.allocation.pick_rank IS
    'Order of selection for greedy/naive scenarios. NULL for the ILP, which selects a set, not a sequence.';

CREATE INDEX allocation_scenario_idx ON core.allocation (scenario, scheme);

-- ---------------------------------------------------------------------------
-- Scenario comparison, including the equity constraints each one breaches.
--
-- This is the view that answers "what did optimisation buy you over sorting?"
-- ---------------------------------------------------------------------------

CREATE VIEW core.v_allocation_summary AS
WITH picked AS (
    SELECT a.scenario, a.scheme, a.district_id, a.coverage_gain,
           d.nfhs_state, d.region, d.terrain, d.rural_population
    FROM core.allocation a
    JOIN core.district d USING (district_id)
),
by_state AS (
    SELECT scenario, scheme, nfhs_state, count(*) AS n
    FROM picked GROUP BY 1, 2, 3
)
SELECT
    p.scenario,
    p.scheme,
    count(*)                                            AS facilities,
    count(DISTINCT p.nfhs_state)                        AS states_covered,
    count(DISTINCT p.region)                            AS regions_covered,
    sum(p.coverage_gain)                                AS total_coverage_gain,
    sum(p.rural_population)                             AS rural_population_in_selected,
    count(*) FILTER (WHERE p.terrain <> 'plains')       AS hilly_or_tribal_picks,
    (SELECT max(n) FROM by_state b
      WHERE b.scenario = p.scenario AND b.scheme = p.scheme)
                                                        AS max_in_any_state,
    (SELECT string_agg(b.nfhs_state || ' (' || b.n || ')', ', ' ORDER BY b.n DESC)
       FROM by_state b
      WHERE b.scenario = p.scenario AND b.scheme = p.scheme
        AND b.n > (SELECT value FROM core.param WHERE key = 'max_per_state'))
                                                        AS states_over_cap
FROM picked p
GROUP BY p.scenario, p.scheme;

COMMENT ON VIEW core.v_allocation_summary IS
    'Per-scenario totals and equity-constraint breaches. states_over_cap is NULL when the scenario is feasible.';
