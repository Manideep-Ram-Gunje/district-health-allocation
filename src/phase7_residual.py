"""Phase 7 — is a district unhealthy because it is poor, or because it is badly served?

The Need Index answers "how bad are health outcomes here". It cannot separate
two very different districts:

  * poor district, poor health  — outcomes are roughly what its socioeconomic
    profile predicts. The binding constraint is poverty.
  * poor district, WORSE health than predicted — outcomes fall below what its
    literacy, electrification, sanitation and water access would lead you to
    expect. Something other than poverty is failing.

A new Sub-Centre plausibly helps the second far more than the first. So we
model the need index from Census 2011 socioeconomic variables and study the
RESIDUALS. A large positive residual means health outcomes are worse than the
district's own material conditions predict — a health-system signal rather than
a poverty signal.

This is deliberately a modest model. The point is not predictive accuracy; a
high R-squared here would just mean health outcomes track poverty, which we
already believe. The point is what the model CANNOT explain.

    python -m src.phase7_residual
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import KFold, cross_val_predict, cross_val_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.config import DATA_INTERIM, DATA_PROCESSED, REPORTS, engine, load_yaml, raw_path

SEED = 42

# Census 2011 columns -> interpretable rates. Every feature is a SHARE, so
# district size cannot leak in as a predictor of health outcomes.
FEATURES = {
    "literacy_rate":        ("Literate", "Population"),
    "female_literacy_rate": ("Female_Literate", "Female"),
    "sc_share":             ("SC", "Population"),
    "st_share":             ("ST", "Population"),
    "electrified_hh":       ("Housholds_with_Electric_Lighting", "Households"),
    "latrine_hh":           ("Having_latrine_facility_within_the_premises_Total_Households", "Households"),
    "tapwater_hh":          ("Main_source_of_drinking_water_Tapwater_Households", "Households"),
    "lpg_hh":               ("LPG_or_PNG_Households", "Households"),
    "agri_worker_share":    ("Agricultural_Workers", "Workers"),
    "worker_share":         ("Workers", "Population"),
    "rural_hh_share":       ("Rural_Households", "Households"),
}


def build_frame() -> pd.DataFrame:
    cen = pd.read_csv(raw_path("census2011_districts"), low_memory=False)
    cen = cen.rename(columns={"District code": "census_code"})

    X = pd.DataFrame({"census_code": cen.census_code})
    for name, (num, den) in FEATURES.items():
        if num not in cen.columns or den not in cen.columns:
            raise KeyError(f"Census column missing for {name}: {num} / {den}")
        X[name] = (cen[num] / cen[den].replace(0, np.nan)).clip(0, 1)

    xw = pd.read_csv(DATA_INTERIM / "crosswalk.csv")
    xw = xw.dropna(subset=["census_code"])[["nfhs_state", "nfhs_district", "census_code"]]
    xw["census_code"] = xw.census_code.astype(int)

    scheme = load_yaml("indicators.yml")["default_scheme"]
    with engine().connect() as cx:
        need = pd.read_sql(f"""
            select d.district_id, d.nfhs_state, d.nfhs_district, d.region, d.terrain,
                   d.rural_population, s.need_index
            from core.mv_district_score s
            join core.district d using (district_id)
            where s.scheme = '{scheme}'""", cx)

    df = need.merge(xw, on=["nfhs_state", "nfhs_district"], how="inner") \
             .merge(X, on="census_code", how="inner")
    return df.dropna(subset=list(FEATURES))


def main() -> int:
    print("=== Phase 7: socioeconomic residual model ===")
    df = build_frame()
    X = df[list(FEATURES)].to_numpy()
    y = df["need_index"].to_numpy(dtype=float)
    print(f"  districts={len(df)}, features={X.shape[1]}")

    cv = KFold(n_splits=5, shuffle=True, random_state=SEED)
    models = {
        "ridge": make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-3, 3, 25))),
        "random_forest": RandomForestRegressor(
            n_estimators=500, min_samples_leaf=3, random_state=SEED, n_jobs=-1),
    }

    scores, preds = {}, {}
    for name, m in models.items():
        r2 = cross_val_score(m, X, y, cv=cv, scoring="r2")
        mae = -cross_val_score(m, X, y, cv=cv, scoring="neg_mean_absolute_error")
        preds[name] = cross_val_predict(m, X, y, cv=cv)
        scores[name] = {"r2_mean": r2.mean(), "r2_std": r2.std(), "mae": mae.mean()}
        print(f"  {name:<14} 5-fold R2 = {r2.mean():.3f} (sd {r2.std():.3f})   MAE = {mae.mean():.4f}")

    best = max(scores, key=lambda k: scores[k]["r2_mean"])
    print(f"  best: {best}")

    # Out-of-fold predictions, so a district's residual is never computed from
    # a model that saw that district during training.
    df["predicted_need"] = preds[best]
    df["residual"] = df.need_index - df.predicted_need
    df["residual_z"] = (df.residual - df.residual.mean()) / df.residual.std()

    # Feature importance from a model fit on everything, for interpretation only.
    rf = RandomForestRegressor(n_estimators=500, min_samples_leaf=3,
                               random_state=SEED, n_jobs=-1).fit(X, y)
    imp = (pd.Series(rf.feature_importances_, index=list(FEATURES))
             .sort_values(ascending=False))

    with engine().connect() as cx:
        alloc = set(pd.read_sql(
            "select district_id from core.allocation where scenario='optimal'",
            cx).district_id)
    df["allocated"] = df.district_id.isin(alloc)

    out = DATA_PROCESSED / "residuals.csv"
    df.to_csv(out, index=False)
    write_report(df, scores, best, imp)
    print(f"\n  residuals -> {out}")
    print(f"  report    -> {REPORTS / 'residual_report.md'}")

    under = df.nlargest(15, "residual")
    print(f"\n  worst 8 vs socioeconomic expectation:")
    for r in under.head(8).itertuples():
        print(f"    {r.nfhs_district:<24} {r.nfhs_state:<16} "
              f"actual={r.need_index:.3f} predicted={r.predicted_need:.3f} "
              f"resid={r.residual:+.3f}{'  [allocated]' if r.allocated else ''}")
    print("\nPHASE 7 COMPLETE")
    return 0


def write_report(df, scores, best, imp) -> None:
    n_alloc = int(df.allocated.sum())
    over = df.nlargest(15, "residual")
    under = df.nsmallest(10, "residual")
    hit = int(over.head(25).allocated.sum())

    L = ["# Socioeconomic Residual Model", "",
         "## The question this answers", "",
         "The Need Index says *how bad* health outcomes are. It cannot distinguish a "
         "district whose outcomes are poor **because it is poor** from one whose "
         "outcomes are poor **beyond what its poverty explains**. A new Sub-Centre "
         "plausibly helps the second far more than the first.", "",
         "So the need index is modelled from Census 2011 socioeconomic variables — "
         "literacy, electrification, sanitation, piped water, cooking fuel, caste "
         "composition, workforce structure — and the **residuals** are the object of "
         "interest. A large positive residual means health outcomes are worse than the "
         "district's own material conditions predict.", "",
         "## Model performance", "",
         "5-fold cross-validated. Residuals use **out-of-fold** predictions, so no "
         "district's residual comes from a model that saw it in training.", "",
         "| Model | R² (mean) | R² (sd) | MAE |", "|---|---|---|---|"]
    L += [f"| `{k}` | {v['r2_mean']:.3f} | {v['r2_std']:.3f} | {v['mae']:.4f} |"
          for k, v in scores.items()]
    L += ["", f"Best: **`{best}`**.", "",
          "### Reading the R² correctly", "",
          "A high R² here would **not** be a good result. It would mean health outcomes "
          "are almost entirely explained by material conditions — that the health system "
          "adds nothing measurable beyond poverty. The interesting quantity is the "
          "portion the model *fails* to explain, because that is where a facility can "
          "plausibly move the outcome.", "",
          "## What drives the prediction", "",
          "| Feature | Importance |", "|---|---|"]
    L += [f"| `{k}` | {v:.3f} |" for k, v in imp.items()]

    L += ["", "## Districts performing worse than predicted", "",
          "Positive residual = health outcomes worse than socioeconomic profile "
          "predicts. These are the strongest candidates for a *health-system* "
          "intervention rather than a poverty intervention.", "",
          "| District | State | Actual | Predicted | Residual | Allocated |",
          "|---|---|---|---|---|---|"]
    L += [f"| {r.nfhs_district} | {r.nfhs_state} | {r.need_index:.3f} | "
          f"{r.predicted_need:.3f} | {r.residual:+.3f} | "
          f"{'yes' if r.allocated else 'no'} |" for r in over.itertuples()]

    L += ["", "## Districts performing better than predicted", "",
          "Negative residual = better health outcomes than material conditions would "
          "suggest. Worth studying for what is working.", "",
          "| District | State | Actual | Predicted | Residual |", "|---|---|---|---|---|"]
    L += [f"| {r.nfhs_district} | {r.nfhs_state} | {r.need_index:.3f} | "
          f"{r.predicted_need:.3f} | {r.residual:+.3f} |" for r in under.itertuples()]

    L += ["", "## Relationship to the allocation", "",
          f"{hit} of the 15 worst-residual districts are in the allocated {n_alloc}. "
          "The allocation is driven by the need index, not by residuals, so overlap is "
          "informative rather than circular: where they agree, a district is both badly "
          "off *and* badly off beyond its means.", "",
          "## Limitations", "",
          "1. **Correlation, not causation.** A positive residual is consistent with a "
          "weak health system, but also with measurement error, migration, or omitted "
          "variables. It is a screening signal, not a diagnosis.",
          "2. **Predictors are from 2011, outcomes from 2019–21.** Socioeconomic "
          "conditions changed over the decade; the model cannot see that.",
          "3. **Census socioeconomic variables are themselves district aggregates**, so "
          "within-district inequality is invisible.",
          "4. The residual is not used to drive the allocation. It is offered as a "
          "second lens, and mixing it into the objective without a causal argument "
          "would be indefensible."]

    (REPORTS / "residual_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
