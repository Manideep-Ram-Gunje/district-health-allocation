# Resources

Presentation deliverables. Everything here is **generated from** the analysis in
the parent repository — none of it is authored independently, and none of it is
an input to the pipeline.

| File | What it is | Audience |
|---|---|---|
| `Project_Report.pdf` | 10-page written report, large type | Recruiter or interviewer, non-specialist |
| `Project_Deck.pptx` | 12-slide deck with speaker notes | 10-minute walkthrough |
| `Recommendation_Memo.md` | One-page policy-style memo | Shows the analysis translated into a decision |

## Where the numbers come from

Every figure quoted in these documents is produced by the pipeline and can be
regenerated:

```bash
make pipeline    # rebuilds everything from raw data
make test        # 82 tests
```

The authoritative sources are `reports/` (six generated reports) and
`docs/build-log.md` (the full build record, including every failure).

## Keeping them current

These documents are **snapshots**. If the pipeline changes, they do not update
themselves — regenerate them and check the figures against `reports/` before
sharing. The build log records what each number was at the time it was written.
