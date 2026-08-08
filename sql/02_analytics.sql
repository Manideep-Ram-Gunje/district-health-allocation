-- ===========================================================================
-- Analytics layer — the Composite Need Index and everything derived from it.
--
-- Materialised views, built as a chain so each step is separately inspectable.
-- If someone challenges the index in an interview, every intermediate stage
-- can be selected from and shown:
--
--   mv_indicator_score      direction-normalised raw values
--   mv_indicator_percentile percentile rank within the national distribution
--   mv_need_index           weighted composite, per weighting scheme
--   mv_district_score       need + population + coverage terms
--   mv_peer_benchmark       district against its state and region
--   v_supply_degeneracy     executable proof of a methodological finding
--
-- Idempotent. Re-running drops and rebuilds the whole chain.
-- ===========================================================================

DROP MATERIALIZED VIEW IF EXISTS core.mv_peer_benchmark CASCADE;
DROP MATERIALIZED VIEW IF EXISTS core.mv_district_score CASCADE;
DROP MATERIALIZED VIEW IF EXISTS core.mv_need_index CASCADE;
DROP MATERIALIZED VIEW IF EXISTS core.mv_indicator_percentile CASCADE;
DROP MATERIALIZED VIEW IF EXISTS core.mv_indicator_score CASCADE;
DROP VIEW IF EXISTS core.v_supply_degeneracy CASCADE;

-- ---------------------------------------------------------------------------
-- 1. Direction normalisation
--
-- Four of the seven indicators are GOOD things (institutional births, ANC
-- visits). Three are BAD things (stunting, anaemia). Before they can be
-- combined they must point the same way. After this view, higher ALWAYS means
-- greater need.
--
-- Districts with a NULL value are simply absent here — they are not imputed.
-- ---------------------------------------------------------------------------

CREATE MATERIALIZED VIEW core.mv_indicator_score AS
SELECT
    di.district_id,
    i.indicator_id,
    i.indicator_key,
    i.domain,
    i.higher_is_worse,
    di.value_nfhs5                                                   AS raw_value,
    CASE WHEN i.higher_is_worse
         THEN di.value_nfhs5
         ELSE 100 - di.value_nfhs5
    END                                                              AS need_value
FROM core.district_indicator di
JOIN core.indicator i USING (indicator_id)
WHERE i.in_index
  AND di.value_nfhs5 IS NOT NULL;

COMMENT ON MATERIALIZED VIEW core.mv_indicator_score IS
    'Direction-normalised indicator values. Higher = greater need, always.';

-- ---------------------------------------------------------------------------
-- 2. Percentile rank within the national distribution
--
-- Raw indicator values are not comparable across indicators: institutional
-- births ranges roughly 20-100 while stunting ranges 6-60. Averaging them
-- directly would let the widest-spread indicator dominate the index by
-- accident. Converting each to its percentile rank within the national
-- distribution puts every indicator on the same 0-1 scale, so the weight
-- vector is the ONLY thing determining influence.
--
-- percent_rank() is used rather than cume_dist() so the least-needy district
-- scores exactly 0 and the neediest exactly 1.
-- ---------------------------------------------------------------------------

-- percent_rank() returns double precision. It is cast to numeric here, once,
-- so the entire index chain downstream is exact decimal arithmetic rather than
-- binary floating point. Two practical consequences: round(x, n) works (there
-- is no two-argument round() for double precision in Postgres), and the need
-- index is bit-for-bit reproducible across machines.
CREATE MATERIALIZED VIEW core.mv_indicator_percentile AS
SELECT
    s.*,
    (percent_rank() OVER (PARTITION BY s.indicator_id ORDER BY s.need_value))::numeric
                                                                     AS need_percentile
FROM core.mv_indicator_score s;

CREATE INDEX mv_ind_pct_district_idx ON core.mv_indicator_percentile (district_id);
CREATE INDEX mv_ind_pct_key_idx      ON core.mv_indicator_percentile (indicator_key);

COMMENT ON MATERIALIZED VIEW core.mv_indicator_percentile IS
    'Percentile rank of each district within the national distribution of each indicator. 0 = least need, 1 = most need.';

-- ---------------------------------------------------------------------------
-- 3. Composite Need Index, per weighting scheme
--
-- Weighted mean of the percentile ranks. Weights are renormalised over the
-- indicators actually PRESENT for that district, so a district missing one
-- indicator is scored on the six it has rather than being penalised to zero
-- or silently imputed to the mean.
--
-- indicators_present is carried forward so downstream views can enforce the
-- missingness floor, and so a sceptical reader can see which districts were
-- scored on partial data.
-- ---------------------------------------------------------------------------

CREATE MATERIALIZED VIEW core.mv_need_index AS
SELECT
    p.district_id,
    w.scheme,
    count(*)                                                         AS indicators_present,
    sum(w.weight)                                                    AS weight_covered,
    sum(w.weight * p.need_percentile) / sum(w.weight)                AS need_index
FROM core.mv_indicator_percentile p
JOIN core.weight_scheme w ON w.indicator_key = p.indicator_key
GROUP BY p.district_id, w.scheme;

CREATE INDEX mv_need_index_idx ON core.mv_need_index (scheme, district_id);

COMMENT ON COLUMN core.mv_need_index.weight_covered IS
    'Sum of weights for indicators present. Below 1 means the district was scored on partial data and its weights were renormalised.';

-- ---------------------------------------------------------------------------
-- 4. District score — need combined with population and IPHS geometry
--
-- population_at_risk   spec metric: need x rural population
-- required_facilities  IPHS-implied Sub-Centres for this district's rural
--                      population at its terrain-specific catchment norm
-- coverage_gain        need-weighted population one NEW facility would bring
--                      within catchment. Capped at the catchment norm because
--                      a single Sub-Centre cannot serve more than that.
--
-- coverage_gain is the ILP objective coefficient in Phase 3.
-- ---------------------------------------------------------------------------

CREATE MATERIALIZED VIEW core.mv_district_score AS
SELECT
    d.district_id,
    d.nfhs_state,
    d.nfhs_district,
    d.region,
    d.terrain,
    d.catchment_norm,
    d.rural_population,
    d.is_apportioned,
    n.scheme,
    n.need_index,
    n.indicators_present,
    n.need_index * d.rural_population                                AS population_at_risk,
    ceil(d.rural_population::numeric / d.catchment_norm)             AS required_facilities,
    n.need_index * LEAST(d.catchment_norm, d.rural_population)       AS coverage_gain
FROM core.district d
JOIN core.mv_need_index n USING (district_id)
WHERE n.indicators_present >= core.get_param('min_indicators_present')
  AND d.rural_population > 0;

CREATE INDEX mv_district_score_idx ON core.mv_district_score (scheme, need_index DESC);

COMMENT ON COLUMN core.mv_district_score.coverage_gain IS
    'Objective coefficient for the Phase 3 ILP: need_index x min(catchment_norm, rural_population).';

-- ---------------------------------------------------------------------------
-- 5. Peer benchmarking
--
-- A district scoring 0.7 means something different in Kerala than in Bihar.
-- These columns let the app answer "is this district bad, or is its whole
-- state bad?" — which is the question a State Health Society actually asks,
-- since it allocates within its own state.
-- ---------------------------------------------------------------------------

CREATE MATERIALIZED VIEW core.mv_peer_benchmark AS
SELECT
    s.district_id,
    s.scheme,
    s.nfhs_state,
    s.region,
    s.need_index,
    rank()       OVER (PARTITION BY s.scheme ORDER BY s.need_index DESC)
                                                                     AS national_rank,
    rank()       OVER (PARTITION BY s.scheme, s.nfhs_state ORDER BY s.need_index DESC)
                                                                     AS state_rank,
    count(*)     OVER (PARTITION BY s.scheme, s.nfhs_state)           AS districts_in_state,
    avg(s.need_index) OVER (PARTITION BY s.scheme, s.nfhs_state)      AS state_mean_need,
    avg(s.need_index) OVER (PARTITION BY s.scheme, s.region)          AS region_mean_need,
    s.need_index - avg(s.need_index) OVER (PARTITION BY s.scheme, s.nfhs_state)
                                                                     AS gap_to_state_mean
FROM core.mv_district_score s;

CREATE INDEX mv_peer_idx ON core.mv_peer_benchmark (scheme, national_rank);

-- ---------------------------------------------------------------------------
-- 6. The supply adjustment degeneracy — an executable proof
--
-- Spec section 6.3 asks for underservice = population at risk / existing
-- facilities, falling back to NORM-IMPLIED facilities where counts are
-- unavailable (which they are — see config/sources.yml `unavailable:`).
--
-- Substituting norm-implied supply makes the ratio collapse:
--
--     underservice = (need x rural_pop) / (rural_pop / norm)
--                  = need x norm
--
-- The population term cancels exactly. The "supply-adjusted" score is just
-- the need index times a terrain constant — it carries no supply information
-- whatsoever, and would rank districts almost identically to the raw need
-- index while LOOKING like it accounts for existing infrastructure.
--
-- This view demonstrates the cancellation on the real data rather than
-- asserting it. ratio_check should be 1.0 for every row.
--
-- Consequence: we do NOT ship a supply-adjusted underservice score. The
-- supply side enters the model only through the terrain-specific catchment
-- norm in coverage_gain. This is stated in the README, not buried.
-- ---------------------------------------------------------------------------

CREATE VIEW core.v_supply_degeneracy AS
SELECT
    district_id,
    nfhs_state,
    nfhs_district,
    terrain,
    scheme,
    need_index,
    population_at_risk,
    rural_population::numeric / catchment_norm                       AS norm_implied_facilities,
    population_at_risk / (rural_population::numeric / catchment_norm)
                                                                     AS underservice_if_computed,
    need_index * catchment_norm                                      AS algebraic_prediction,
    round((population_at_risk / (rural_population::numeric / catchment_norm))
          / NULLIF(need_index * catchment_norm, 0), 10)              AS ratio_check
FROM core.mv_district_score;

COMMENT ON VIEW core.v_supply_degeneracy IS
    'Proof that norm-implied supply adjustment cancels: ratio_check is 1.0 for every district. See README.';
