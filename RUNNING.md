# How to run the Decision Brief Generator

Two ways. Pick based on whether you want to install anything.

---

## Option A — look at the output without installing anything

Every deliverable is committed, so you can inspect the result before deciding
whether to run it.

| What | Where |
|---|---|
| **Interactive dashboard** | [misbahhamid-30.github.io/decision-brief-generator](https://misbahhamid-30.github.io/decision-brief-generator/) — opens in a browser, nothing to install |
| Executive brief (Word) | [`outputs/Decision-Brief.docx`](outputs/Decision-Brief.docx) |
| Leadership deck | [`outputs/Decision-Brief.pptx`](outputs/Decision-Brief.pptx) |
| Full analysis, including what was set aside | [`outputs/analysis_report.md`](outputs/analysis_report.md) |
| Data-quality report | [`outputs/data_quality_report.md`](outputs/data_quality_report.md) |
| Verification — 26 independent checks | [`outputs/verification_report.txt`](outputs/verification_report.txt) |
| The same pipeline on a second domain | [`outputs_rides/`](outputs_rides/) |
| Sample of the underlying data | [`data/samples/`](data/samples/) |

The dashboard is a static file — all figures are computed by Python at build
time and baked in. It makes no network calls, so it works offline and when
emailed.

To see the structure of the data without downloading 174 MB, `data/samples/`
holds a 2,000-row extract of every table.

---

## Option B — run it yourself

Works on Windows, macOS and Linux. Commands are shown for PowerShell; on
macOS/Linux use `python3` and forward slashes.

### 0. Get the code

```powershell
git clone https://github.com/MisbahHamid-30/decision-brief-generator.git
cd decision-brief-generator
```

Every command below assumes you are in that folder.

### 1. Install Python 3.10 or newer

Check whether you already have it. Open **PowerShell** and run:

```powershell
python --version
```

If that fails or shows below 3.10, install from
[python.org/downloads](https://www.python.org/downloads/). **Tick "Add Python to
PATH"** on the first screen of the installer — it is off by default and
everything else depends on it.

### 2. Install the Python packages

```powershell
pip install -r requirements.txt
```

Takes a couple of minutes. Installs pandas, numpy, scipy, statsmodels,
matplotlib and PyYAML.

### 3. Install Node.js — only if you want the Word brief and the deck

The analysis, the reports and the HTML dashboard are pure Python and need
nothing further. The `.docx` and `.pptx` renderers are JavaScript.

Check first:

```powershell
node --version
```

If missing, install Node 18+ from [nodejs.org](https://nodejs.org/) (the LTS
build), then from the project folder:

```powershell
npm install
```

That reads `package.json` and creates a `node_modules` folder inside the
project. The builder finds it automatically.

If you skip this step the build still runs — it prints a note and produces
everything except the two Office files.

### 4. Generate the data

**Do not skip this.** The datasets are not in the repository — together they are
~174 MB, and both are reproducible exactly from seeded scripts, so committing
them would be waste. Without this step the pipeline stops with an error telling
you to run it.

```powershell
python src\generate_dummy_data.py      # supply chain → data/careem_quik/
python src\generate_rides_data.py      # marketplace  → data/careem_rides/
```

About a minute each. The seeds are fixed, so you get byte-identical files to the
ones the published outputs were built from. (Alternatively, download them from
the Drive link in the README and unpack each folder into `data/`.)

### 5. Run it

```powershell
python src\build_outputs.py
```

Takes about 60–90 seconds. Output:

```
running analysis ...
  12 findings, 6 actions, net AED 727k/yr
drawing charts ...
rendering dashboard ...
rendering Word brief ...
rendering deck ...
done.
```

---

## The four commands

Run all of these from the project folder.

| Command | Time | What it does |
|---|---|---|
| `python src\build_outputs.py` | ~90s | **Everything.** Analysis, 8 charts, Word brief, deck, dashboard |
| `python src\run_analysis.py` | ~40s | Analysis only — findings and markdown reports, no documents |
| `python src\verify_signals.py` | ~20s | Acceptance test: are the six planted signals in the data? |
| `python src\verify_outputs.py` | ~30s | Independent verification: 26 checks against the raw CSVs |

On macOS or Linux use `python3` and forward slashes: `python3 src/build_outputs.py`.

---

## What you get

Everything lands in `outputs/`.

| File | Open with |
|---|---|
| `Decision-Brief.docx` | Word — the 13-page executive brief |
| `Decision-Brief.pptx` | PowerPoint — the 10-slide deck |
| `dashboard.html` | Any browser — double-click it |
| `analysis_report.md` | Any text editor, or VS Code for formatting |
| `data_quality_report.md` | What was checked, what failed, what was repaired |
| `verification_report.txt` | The 26 checks and their results |
| `findings.json` | Machine-readable, if you want to feed it somewhere else |
| `charts/` | The 8 charts as PNGs, reusable elsewhere |

Each run overwrites the previous one. If you want to keep a version, copy the
`outputs` folder before re-running.

---

## Running it on your own data

Three steps. No analysis code changes.

**1. Create a profile.** Pick a name — say `acme_ops` — then put your CSVs in
`data/<profile>/` and your two config files in `config/<profile>/`. The two
folders must share the same name; that is what ties them together.

**2. Describe them in `config/<profile>/semantic_map.yaml`.** For each file, declare its
role (`fact`, `dimension` or `bridge`), its primary key or grain, its date
column and its foreign keys. Then map your column names to the concepts the
analysis speaks — `sold_units`, `revenue`, `city` and so on. The analysis code
never refers to a raw column name, only to a concept, which is what makes this
portable.

**3. Set your targets and costs in `config/<profile>/business_rules.yaml`** — what good
looks like, and how an operational failure converts into money. Every assumption
here is printed in the brief's appendix so it can be challenged.

Then point the loader at the new folder — one line in `src/ingest.py`:

```python
DEFAULT_DATA = os.path.join(ROOT, "data", "my_data")
```

**Expect to add detectors.** The eight bundled ones are supply-chain specific
(fill rate, supplier reliability, waste concentration, lot size, assortment
tail, replenishment cadence, fleet capacity, seasonality). A different domain
will need its own. Add a function to `src/analysis/detectors.py` taking
`(ds, k, rules)` and returning `list[Finding]`, then register it in
`ALL_DETECTORS`.

**Write an acceptance test.** `verify_signals.py` exists because "the analysis
found five problems" is not a checkable claim. For new data, define at least one
truth you already know and confirm the pipeline finds it unaided.

---

## If something goes wrong

| Symptom | Cause and fix |
|---|---|
| `'python' is not recognized` | Python is not on PATH. Reinstall and tick "Add Python to PATH", or use the full path to `python.exe` |
| `ModuleNotFoundError: No module named 'pandas'` | Step 2 was skipped or ran against a different Python. Try `python -m pip install -r requirements.txt` |
| `skipped brief_docx.js — Node packages not found` | Run `npm install` in the project folder. Everything else still built |
| `skipped ... Node.js is not installed` | Install Node 18+ from nodejs.org, then `npm install` |
| `BLOCKED by the data-quality gate` | Working as designed — the data has a critical integrity failure. Read `outputs/data_quality_report.md`; it names the problem |
| `missing findings.json — run build_outputs.py first` | `verify_outputs.py` was run before a build |
| Charts look wrong or empty | Usually a semantic-map mismatch on new data. Run `python src\ingest.py` alone — it prints a table profile showing what actually loaded |
| Everything runs but no findings appear | Likely the materiality floor in `business_rules.yaml` is set higher than anything in your data. Check the "detected but below the materiality floor" section of `analysis_report.md` |

---

## What each script actually does

Useful if you want to run one stage at a time.

```
src/ingest.py          Load, profile and compact the tables; resolve concepts.
                       Run it alone to see what loaded and how big it is.

src/quality.py         The gate. Run it alone to get the data-quality report
                       without doing any analysis.

src/run_analysis.py    ingest → quality → KPIs → detectors → recommendations.
                       Writes findings.json and analysis_report.md.

src/build_outputs.py   Everything run_analysis.py does, plus charts and the
                       three deliverables.

src/verify_signals.py  Checks the six planted signals are present in the data.
                       Tests the dataset, not the analysis.

src/verify_outputs.py  Checks the brief against a fresh recomputation from the
                       CSVs. Tests the analysis, not the dataset.

src/generate_dummy_data.py
                       Regenerates the synthetic dataset. Only needed if you
                       want different data; the CSVs are already committed.
```
