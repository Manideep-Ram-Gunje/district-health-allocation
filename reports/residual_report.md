# Socioeconomic Residual Model

## The question this answers

The Need Index says *how bad* health outcomes are. It cannot distinguish a district whose outcomes are poor **because it is poor** from one whose outcomes are poor **beyond what its poverty explains**. A new Sub-Centre plausibly helps the second far more than the first.

So the need index is modelled from Census 2011 socioeconomic variables — literacy, electrification, sanitation, piped water, cooking fuel, caste composition, workforce structure — and the **residuals** are the object of interest. A large positive residual means health outcomes are worse than the district's own material conditions predict.

## Model performance

5-fold cross-validated. Residuals use **out-of-fold** predictions, so no district's residual comes from a model that saw it in training.

| Model | R² (mean) | R² (sd) | MAE |
|---|---|---|---|
| `ridge` | 0.537 | 0.027 | 0.1112 |
| `random_forest` | 0.657 | 0.023 | 0.0949 |

Best: **`random_forest`**.

### Reading the R² correctly

A high R² here would **not** be a good result. It would mean health outcomes are almost entirely explained by material conditions — that the health system adds nothing measurable beyond poverty. The interesting quantity is the portion the model *fails* to explain, because that is where a facility can plausibly move the outcome.

## What drives the prediction

| Feature | Importance |
|---|---|
| `electrified_hh` | 0.423 |
| `st_share` | 0.142 |
| `literacy_rate` | 0.083 |
| `worker_share` | 0.065 |
| `tapwater_hh` | 0.064 |
| `female_literacy_rate` | 0.058 |
| `sc_share` | 0.041 |
| `latrine_hh` | 0.035 |
| `lpg_hh` | 0.031 |
| `agri_worker_share` | 0.029 |
| `rural_hh_share` | 0.029 |

## Districts performing worse than predicted

Positive residual = health outcomes worse than socioeconomic profile predicts. These are the strongest candidates for a *health-system* intervention rather than a poverty intervention.

| District | State | Actual | Predicted | Residual | Allocated |
|---|---|---|---|---|---|
| Kamrup Metropolitan | Assam | 0.622 | 0.171 | +0.451 | no |
| Mewat | Haryana | 0.835 | 0.461 | +0.374 | yes |
| Jalgaon | Maharashtra | 0.724 | 0.380 | +0.345 | no |
| Deoghar | Jharkhand | 0.919 | 0.584 | +0.335 | yes |
| Unakoti | Tripura | 0.867 | 0.574 | +0.293 | yes |
| Patna | Bihar | 0.810 | 0.536 | +0.274 | no |
| Pakur | Jharkhand | 0.919 | 0.652 | +0.267 | yes |
| Dhule | Maharashtra | 0.717 | 0.457 | +0.260 | no |
| Dumka | Jharkhand | 0.827 | 0.567 | +0.259 | no |
| Doda | Jammu Kashmir | 0.725 | 0.467 | +0.258 | no |
| Paschim Barddhaman | West Bengal | 0.683 | 0.429 | +0.254 | no |
| Pauri Garhwal | Uttarakhand | 0.638 | 0.387 | +0.251 | no |
| Jalna | Maharashtra | 0.660 | 0.410 | +0.250 | no |
| Dhanbad | Jharkhand | 0.700 | 0.459 | +0.241 | no |
| Kurnool | Andhra Pradesh | 0.593 | 0.352 | +0.241 | no |

## Districts performing better than predicted

Negative residual = better health outcomes than material conditions would suggest. Worth studying for what is working.

| District | State | Actual | Predicted | Residual |
|---|---|---|---|---|
| Balangir | Odisha | 0.218 | 0.575 | -0.357 |
| South Goa | Goa | 0.063 | 0.405 | -0.342 |
| Kandhamal | Odisha | 0.287 | 0.623 | -0.336 |
| Chamarajanagar | Karnataka | 0.178 | 0.503 | -0.325 |
| Wayanad | Kerala | 0.111 | 0.427 | -0.316 |
| Nayagarh | Odisha | 0.172 | 0.459 | -0.287 |
| Dharmapuri | Tamil Nadu | 0.109 | 0.389 | -0.280 |
| Jharsuguda | Odisha | 0.226 | 0.496 | -0.270 |
| Porbandar | Gujarat | 0.138 | 0.405 | -0.267 |
| North  District | Sikkim | 0.337 | 0.600 | -0.264 |

## Relationship to the allocation

4 of the 15 worst-residual districts are in the allocated 25. The allocation is driven by the need index, not by residuals, so overlap is informative rather than circular: where they agree, a district is both badly off *and* badly off beyond its means.

## Limitations

1. **Correlation, not causation.** A positive residual is consistent with a weak health system, but also with measurement error, migration, or omitted variables. It is a screening signal, not a diagnosis.
2. **Predictors are from 2011, outcomes from 2019–21.** Socioeconomic conditions changed over the decade; the model cannot see that.
3. **Census socioeconomic variables are themselves district aggregates**, so within-district inequality is invisible.
4. The residual is not used to drive the allocation. It is offered as a second lens, and mixing it into the objective without a causal argument would be indefensible.
