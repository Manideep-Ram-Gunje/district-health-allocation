# Deployment

The app runs from a committed snapshot, so a deployment needs **no database**.

---

## 1 · Local, on the lab network

```bash
.venv/bin/streamlit run app/streamlit_app.py --server.address 0.0.0.0
```

Anyone on the same network opens `http://<your-ip>:8501`. Find your IP with
`hostname -I | awk '{print $1}'`.

This path uses the live Postgres if it is running, and the snapshot if not.

---

## 2 · Public URL via Streamlit Community Cloud

Free, and gives a permanent link — which is worth considerably more on a CV than
a repository link, because a recruiter can click it without installing anything.

### Before you push

Confirm the snapshot exists and is committed. Without it the deployed app has no
data and will show an error.

```bash
make snapshot
ls -la data/processed/snapshot/          # districts.parquet, sensitivity.parquet,
                                         # allocation.parquet, districts.geojson
git add -f data/processed/snapshot/
git status --short                       # snapshot files must be staged
```

Also confirm no secrets are going up. `.env` is gitignored, but check:

```bash
git ls-files | grep -E '\.env$|pgpass' && echo "STOP — secrets staged" || echo "clean"
```

### Push to GitHub

Create an **empty public** repository on GitHub first (no README, no
`.gitignore` — the repo already has both), then:

```bash
git remote add origin https://github.com/<username>/district-health-allocation.git
git branch -M main
git push -u origin main
```

If the push is rejected for size, the raw data is the cause — it is gitignored
by design. Confirm with `git count-objects -vH` that the pack is under ~50 MB.

### Deploy

1. Go to <https://share.streamlit.io> and sign in with GitHub.
2. **New app** → pick the repository and the `main` branch.
3. **Main file path:** `app/streamlit_app.py`
4. Open **Advanced settings** and set:
   - Python version: **3.12**
   - Requirements file: **`requirements-app.txt`**
5. Deploy. First build takes 2–4 minutes.

**Use `requirements-app.txt`, not `requirements.txt`.** The full file pulls in
geopandas and fiona, which need GDAL system libraries and are the usual reason a
Streamlit Cloud build fails. The deployed app never touches them — it reads the
pre-simplified snapshot geojson as plain JSON.

### Verify the deployment

The app shows a banner reading *"Running from an exported snapshot"* when there
is no database. On Streamlit Cloud that banner **should** appear — if it does
not, the app has somehow reached a database and something is misconfigured.

Then check:

- the Allocation tab lists 25 districts
- the Map tab renders the choropleth
- setting *minimum per region* to 5 with *maximum per state* at 1 produces the
  infeasibility error rather than a plausible-looking list

---

## Troubleshooting

**Build fails on `fiona` or `GDAL`.** You are using `requirements.txt`. Switch to
`requirements-app.txt` in Advanced settings.

**App loads but shows "No data source".** The snapshot was not committed.
`data/processed/*.parquet` is gitignored; the snapshot directory is re-included
by a negation rule, but `git add -f data/processed/snapshot/` forces it if your
git version disagrees.

**Map tab is empty.** `districts.geojson` is missing from the snapshot. Run
`make geo && make snapshot` and re-push.

**App is slow on first load.** Expected. Streamlit Cloud cold-starts the
container; the ILP itself solves in well under a second.

---

## Keeping the deployment current

The deployed app is only as fresh as the committed snapshot. After changing the
pipeline:

```bash
make pipeline && make test && make snapshot
git add -A && git commit -m "refresh snapshot" && git push
```

Streamlit Cloud redeploys automatically on push.
