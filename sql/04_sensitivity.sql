-- ===========================================================================
-- Weight sensitivity results.
--
-- One row per (district, regime). Two regimes are stored — a uniform stress
-- test and a realistic centred one — because "how sensitive is it?" has two
-- honest answers depending on how sceptical you are about the weights.
-- ===========================================================================

DROP VIEW  IF EXISTS core.v_allocation_confidence CASCADE;
DROP TABLE IF EXISTS core.weight_sensitivity CASCADE;

CREATE TABLE core.weight_sensitivity (
    district_id       integer  NOT NULL REFERENCES core.district(district_id),
    regime            text     NOT NULL,
    draws             integer  NOT NULL,
    times_in_top_n    integer  NOT NULL,
    rank_stability    numeric(6,5) NOT NULL,
    mean_need_index   numeric(10,8),
    p05_need_index    numeric(10,8),
    p95_need_index    numeric(10,8),
    mean_rank         numeric(8,2),
    best_rank         integer,
    worst_rank        integer,
    ilp_runs          integer,
    times_allocated   integer,
    ilp_stability     numeric(6,5),
    classification    text     NOT NULL,
    PRIMARY KEY (district_id, regime),
    CONSTRAINT classification_known
        CHECK (classification IN ('robust', 'contested', 'excluded')),
    CONSTRAINT stability_is_a_proportion
        CHECK (rank_stability BETWEEN 0 AND 1)
);

COMMENT ON COLUMN core.weight_sensitivity.rank_stability IS
    'Share of draws where the district lands in the top N by need index. Ignores equity constraints.';
COMMENT ON COLUMN core.weight_sensitivity.ilp_stability IS
    'Share of re-solved ILPs where the district is actually allocated. The meaningful measure for an allocated district, because the constrained optimum deliberately reaches outside the national top N.';
COMMENT ON COLUMN core.weight_sensitivity.classification IS
    'Based on ilp_stability where available, else rank_stability. See config/sensitivity.yml.';

-- ---------------------------------------------------------------------------
-- The table to bring to a defence: the optimal 25, with how well each survives
-- both a realistic and an adversarial re-weighting.
-- ---------------------------------------------------------------------------

CREATE VIEW core.v_allocation_confidence AS
SELECT
    d.nfhs_state,
    d.nfhs_district,
    d.region,
    d.terrain,
    a.need_index,
    c.ilp_stability   AS ilp_stability_centred,
    c.rank_stability  AS rank_stability_centred,
    c.classification  AS classification_centred,
    u.ilp_stability   AS ilp_stability_uniform,
    u.rank_stability  AS rank_stability_uniform,
    u.classification  AS classification_uniform,
    c.mean_rank,
    c.best_rank,
    c.worst_rank
FROM core.allocation a
JOIN core.district d USING (district_id)
LEFT JOIN core.weight_sensitivity c
       ON c.district_id = a.district_id AND c.regime = 'centred'
LEFT JOIN core.weight_sensitivity u
       ON u.district_id = a.district_id AND u.regime = 'uniform'
WHERE a.scenario = 'optimal';
