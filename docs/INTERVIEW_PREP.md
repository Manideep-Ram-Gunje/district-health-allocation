# Interview Preparation

Everything here is true and verifiable. Do not memorise phrasing — understand
the reasoning, then say it in your own words.

---

## The 30-second version

> "India allocates rural health facilities largely on population counts, even
> though district-level health *outcome* data is public. I built a system that
> ingests NFHS-5 survey data and Census population, reconciles a decade of
> district boundary changes, scores 696 districts on a composite need index in
> SQL, and solves a budget-constrained integer program for where 25 new
> Sub-Centres should go. Then I tested how much of that answer survives 10,000
> alternative weightings — 11 of the 25 are robust, 14 depend on assumptions,
> and I say which."

Then stop. Let them pick where to go.

---

## The five questions you will get

### 1. "How did you join datasets with mismatched keys?"

NFHS-5 uses 2019–21 district boundaries; Census 2011 predates Telangana, the
J&K reorganisation, and dozens of splits. No official crosswalk exists in
machine-readable form.

Three layers:

- **State-restricted matching.** There's an Aurangabad in both Maharashtra and
  Bihar, a Bilaspur in both Chhattisgarh and Himachal. Matching nationally gives
  confident wrong answers.
- **A directional-token guard.** This is the interesting part — see question 2.
- **A hand-built override table** of 76 post-2011 districts mapped to their
  Census parents, with creation years.

**Validation:** total population across all 705 districts reconciles to the
published Census total to within **7 people** — the gap is exactly Chandigarh
plus Lakshadweep, which have no NFHS factsheet.

### 2. "Tell me about a bug you found."

The best story in the project.

Fuzzy matching didn't fail loudly — it failed *plausibly*. Districts created
after 2011 differ from an existing district by one directional word, and
`token_sort_ratio` scored those pairs 80–90, inside any sane threshold:

| District | Wrongly matched to | Score |
|---|---|---|
| Delhi `South East` | `North East` | 80 |
| `North Garo Hills` | `South Garo Hills` | 88 |
| `South West Khasi Hills` | `West Khasi Hills` | 84 |

Each would have given a district its **sibling's** population — and the output
would have looked perfect, because a high match score is exactly what you check.

Raising the threshold doesn't work: the bad match scores 80 while the genuine
rename Darjeeling → Darjiling scores 84. So the fix refuses a match outright
when directional tokens disagree, forcing those districts to human resolution.

### 3. "Why those weights?"

*"I don't defend them."*

The weight vector is a value judgement — whether stunting matters as much as
institutional births — and no data settles it. So I measured how much the answer
depends on it: 10,000 Dirichlet-sampled weightings, with the full optimisation
re-solved 400 times.

**11 of 25 districts are robust** under plausible disagreement. 14 are
contested. Under an adversarial regime that allows 80% weight on one indicator,
only 2 survive — and I report that too.

One subtlety worth raising unprompted: judging an allocated district by whether
it stays in the *national top 25* is the wrong test. The constrained optimum
deliberately reaches outside that list, because the cap forbids 12 districts
from Bihar. So districts are judged on surviving a full re-solve instead.

### 4. "What did optimisation buy you over sorting?"

*"Not a bigger number — I checked."*

An earlier version claimed a **+13% optimisation premium**. It was measured
against a greedy baseline sorted by the *need index* while the objective was
*coverage gain*. A straw man. Sorted correctly, greedy reaches the identical
optimum. I withdrew the claim.

That's a property of the problem: the objective is linear and the per-state caps
form a **partition matroid**, which is exactly the structure greedy solves
optimally. Verified across 11 constraint configurations.

So what does the ILP buy?

1. **A proof.** Without it you don't know greedy was optimal — and at a region
   floor of 2 or more, my greedy was silently returning *infeasible* answers
   that scored higher than the optimum. That's how I found the bug.
2. **Infeasibility detection.** 40 facilities at 1 per state is impossible;
   CBC says so, a heuristic returns a plausible list.
3. **Declarative constraints.** Changing the cap is one config line.
4. **Robustness.** Once constraints couple districts — travel time, shared
   staffing — the matroid structure is gone and greedy loses its guarantee.

### 5. "What's the weakest part?"

*"There's no supply data, so this measures need, not unmet need."*

District-level facility counts aren't published machine-readable. And when I
substituted the norm-implied supply the methodology allows, the adjustment
**cancelled algebraically**:

```
underservice = (need × pop) / (pop / norm) = need × norm
```

Population cancels exactly. A supply-adjusted score would carry zero supply
information while looking like it accounted for infrastructure — and would rank
districts almost identically to raw need, so the error would never look
suspicious. A database view proves it on all 696 districts. I publish no
supply-adjusted figure.

---

## If they push harder

**"Why percentile ranks and not z-scores?"**
Percentile ranking makes no distributional assumption and bounds every indicator
to [0,1], so the weight vector is the only thing determining influence — which
is what makes the sensitivity analysis interpretable. Z-scores would let a
heavy-tailed indicator dominate. The cost is losing magnitude: a district one
point worse gets a full rank step.

**"Did anything surprise you?"**
The first objective selected 25 plains districts and **zero** hilly or tribal
ones, though 23% of candidates are non-plains. The `min()` in the objective
binds for only 2 of 696 districts, so it collapsed to `need × 5000` in plains
and `need × 3000` in hills — a hilly district needed a 67% higher need score to
compete. That inverts the IPHS standard, whose norm is *lower* in hills because
they're harder to reach. It looked like a modelling detail and was a fairness
failure.

**"Is 73,000 rows big data?"**
No, and I wouldn't claim it. The difficulty here isn't volume — it's that two
government sources disagree and there's no key to join on. Clean data of any
size is the same job.

**"How do I know your numbers are right?"**
Every figure is regenerated by a make target and asserted by a test. 82 tests.
The population conservation check is external — it compares against a published
Census total, not against itself.

**"What would you do next?"**
Parse the NFHS PDFs directly instead of relying on a third-party extract, and
cross-validate the two. Then travel-time constraints, which would break the
matroid structure and make the ILP earn its keep properly.

---

## Demo script (2 minutes)

Open the [live app](https://district-health-allocation-pohllxwaukamsafzd5dyh7.streamlit.app/).

1. **Allocation tab.** "25 districts, 11 states, all 6 regions. The Stability
   column is how often each survives re-weighting."
2. **Switch the objective** to *Raw population coverage*. "9 districts change,
   and every hilly and tribal one disappears. That's a policy choice, not a
   technical one, so it's exposed rather than hardcoded."
3. **Set min-per-region to 5, max-per-state to 1.** "The solver refuses and
   explains why. A heuristic would have returned a plausible-looking list."

Step 3 is the one to end on. It proves the optimiser is running live.

---

## Things not to say

- ❌ "These are the 25 districts that need facilities most." → It measures need,
  not unmet need.
- ❌ "We achieved a 13% improvement." → Withdrawn. Explain why instead.
- ❌ "The model is 65.7% accurate." → It's R² on a residual model whose *point*
  is what it fails to explain.
- ❌ Claiming big data, Spark, or streaming. None are here.
- ❌ Presenting it as a policy recommendation. It is a portfolio project on
  public data.

---

## Numbers to know cold

| Figure | Value |
|---|---|
| Districts reconciled | 705 of 705 (100%) |
| Districts scored | 696 (9 are fully urban) |
| Population conservation error | 7 people |
| Facilities allocated | 25 across 11 states, 6 regions |
| Terrain mix | 16 plains, 5 hilly, 4 tribal |
| Robust / contested | 11 / 14 |
| Weightings tested | 10,000 per regime, 400 ILP re-solves |
| Residual model R² | 0.657 out-of-fold |
| Tests | 82 |
