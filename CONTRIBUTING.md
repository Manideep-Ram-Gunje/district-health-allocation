# Contributing

## Before you change anything

1. Read [`resources/Codebase_Guide.pdf`](resources/Codebase_Guide.pdf) — 15 minutes.
2. Get the pipeline running end to end (below). If you have not reproduced the
   current numbers, you cannot tell whether your change broke something.
3. Skim [`docs/build-log.md`](docs/build-log.md). It records why things are the
   way they are, including several decisions that look odd until you know what
   went wrong first.

## Setup

```bash
git clone git@github.com:Manideep-Ram-Gunje/district-health-allocation.git
cd district-health-allocation

make venv                  # installs requirements-pipeline.txt
cp .env.example .env

sudo apt install -y postgresql postgresql-client
sudo systemctl enable --now postgresql
make db-create

make pipeline              # ~5 minutes
make test                  # 82 tests, all must pass
```

If `make test` does not pass on a clean checkout, stop and open an issue —
that is a bug in the project, not in your machine.

## The rules

**Configuration over code.** Indicators, weights, budget, constraints, IPHS
norms and sampling settings all live in `config/*.yml`. If you find yourself
editing a number inside a `.py` or `.sql` file, it probably belongs in config.

**Every claim needs a test.** The project's credibility rests on its numbers
being reproducible. If you add a finding, add the assertion that would fail if
it stopped being true. See `tests/test_allocation.py` for the pattern — each
test's docstring explains *why it exists*, usually naming the bug it caught.

**Fail loudly.** A missing config key raises rather than returning NULL. An
infeasible allocation errors rather than returning a plausible list. Silent
degradation is the failure mode this project is built to avoid — one such bug
reported an allocation with 12 facilities in one state as violating nothing.

**Never hand-edit generated files.** Anything in `reports/`,
`data/processed/` or `data/interim/` is output. Regenerate it.

**Document what broke.** When something fails in an interesting way, add it to
`docs/build-log.md` while you still remember. That file is the most valuable
thing in the repository.

## Making a change

```bash
git checkout -b describe-your-change
# edit
make pipeline && make test
git add -A && git commit -m "clear description of what and why"
git push -u origin describe-your-change
```

Then open a Pull Request on GitHub. In the description, say what changed, what
you verified, and which numbers moved.

### If a number changes

Any change to `config/` or `sql/` can move the results. When that happens:

```bash
make pipeline              # regenerate everything
make snapshot              # refresh the files the deployed app reads
make test
```

Then check `reports/` and update `README.md` and `resources/` if a headline
figure moved. The deployed app is only as current as the committed snapshot.

## Adding a phase

Phases are numbered and independent. To add one:

1. `src/phaseN_thing.py` with a `main() -> int` returning 0 on success
2. A make target, added to the `pipeline` target in dependency order
3. A generated report in `reports/`
4. `tests/test_thing.py`
5. An entry in `docs/build-log.md`

Follow `src/phase7_residual.py` — it is the smallest complete example.

## Code style

- Explain **why**, not what. The code says what it does; comments should say
  why it does it that way, and what happens if you do it the obvious way instead.
- Keep functions small enough to test directly.
- Type hints on function signatures.
- SQL is formatted for reading: one clause per line, comments above each view
  explaining the decision it encodes.

## Reporting a problem

Open an issue with: what you ran, what you expected, what happened, and the
output of `make test`. If a number looks wrong, name the report it came from —
every figure in this project is traceable to a command that regenerates it.
