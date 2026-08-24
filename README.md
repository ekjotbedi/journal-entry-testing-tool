# Journal Entry Testing Tool

> A data & analytics audit toolkit that ingests a general ledger, runs the
> standard **journal-entry tests** auditors use to detect anomalies and
> potential fraud, scores each entry by risk, and produces **Power BI–ready**
> outputs.

**Tech stack:** Python (pandas) · SQL (SQLite, portable to SQL Server/Oracle) ·
Power BI · Excel · pytest · GitHub Actions CI

---

## Why this project

External audit teams are required (under CAS 240 / ISA 240) to test journal
entries for signs of management override of controls. Doing this by hand across
millions of rows is impossible — so audit **Data & Analytics (D&A)** teams build
exactly this kind of tool: acquire the ledger, transform it, run analytical
tests, and present the results to the engagement team.

This project reproduces that lifecycle end-to-end on **synthetic** data (no real
client data is ever used), with the anomalies deliberately injected so the tests
have something to find.

> 📄 See [`docs/AUDIT_TESTS.md`](docs/AUDIT_TESTS.md) for a plain-language
> explanation of every test and why it matters.

---

## What it does

```
            ┌─────────────────┐
            │ Synthetic GL    │  generate_data.py  (config-driven, seeded)
            │ 2,500 entries   │
            └────────┬────────┘
                     │  CSV
            ┌────────▼────────┐
            │  SQLite load    │  database.py + sql/schema.sql
            └────────┬────────┘
        ┌────────────┴────────────┐
        │                         │
┌───────▼────────┐       ┌────────▼────────┐
│ pandas tests   │  ===  │   SQL tests     │   results cross-checked
│ je_tests.py    │ MATCH │  je_tests.sql   │   at runtime
└───────┬────────┘       └─────────────────┘
        │  risk scoring
┌───────▼─────────────────────────────────┐
│ Outputs (data/output/):                 │
│  • entry_risk_scores.csv  ── Power BI    │
│  • findings.csv           ── Power BI    │
│  • journal_entries.csv    ── Power BI    │
│  • audit_report.xlsx      ── reviewers   │
│  • summary.json           ── metrics     │
└──────────────────────────────────────────┘
```

### The eight audit tests

| Test | Flags |
|------|-------|
| Unbalanced entry | Debits ≠ credits |
| Duplicate entry | Identical content under two entry IDs |
| Just below threshold | Amount structured under an approval limit |
| Backdated entry | Posted long after its effective date |
| Rare poster | Entry by an unusual user |
| Weekend posting | Posted Sat/Sun |
| After-hours posting | Posted outside business hours |
| Round dollar | Suspiciously round amount |

Each entry receives a weighted **risk score** and a band (`High` / `Medium` /
`Low` / `None`).

---

## Quick start

> Requires **Python 3.10+**.

```bash
# 1. Clone and enter the project
git clone <your-repo-url> journal-entry-testing-tool
cd journal-entry-testing-tool

# 2. (Recommended) create a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the full pipeline
python -m src.run_pipeline
```

You'll see:

```
=== 1/5 Generating synthetic general ledger ===
  5,000 lines / 2,500 entries -> data\raw\journal_entries.csv
...
=== 3b/5 Cross-checking with SQL tests ===
  pandas findings=559 | SQL findings=559 -> MATCH
...
Done. Open data/output/audit_report.xlsx or connect Power BI to the CSVs.
```

Then open `data/output/audit_report.xlsx`, or build the dashboard following
[`powerbi/README.md`](powerbi/README.md).

---

## Project structure

```
journal-entry-testing-tool/
├── config/
│   └── config.yaml            # thresholds, anomaly rates, risk weights
├── src/
│   ├── config_loader.py       # load & validate config
│   ├── generate_data.py       # synthetic general-ledger generator
│   ├── database.py            # SQLite load + SQL test runner
│   ├── je_tests.py            # the 8 audit tests + risk scoring (pandas)
│   └── run_pipeline.py        # end-to-end orchestration (entry point)
├── sql/
│   ├── schema.sql             # table definition + indexes
│   └── je_tests.sql           # the 8 audit tests in portable SQL
├── tests/
│   └── test_je_tests.py       # 12 unit tests (pytest)
├── powerbi/
│   └── README.md              # step-by-step dashboard build guide
├── docs/
│   └── AUDIT_TESTS.md         # plain-language test reference
├── data/                      # generated artefacts (git-ignored)
├── .github/workflows/ci.yml   # runs pipeline + tests on every push
├── requirements.txt
├── LICENSE
└── README.md
```

---

## Running the tests

```bash
python -m pytest -q
```

```
............                                                             [100%]
12 passed
```

The suite checks each audit test against hand-built data with known anomalies,
verifies the generator is reproducible, and confirms risk scoring assigns the
correct bands.

---

## Configuration

Everything tunable lives in [`config/config.yaml`](config/config.yaml):

- **`tests`** — approval threshold, business hours, balance tolerance, etc.
- **`risk_weights`** — how many points each failed test contributes.
- **`data_generation`** — dataset size, fiscal year, and how often each anomaly
  is injected.

Change a value, re-run `python -m src.run_pipeline`, and every output updates.

---

## How this maps to a D&A audit role

| Job requirement | Where it shows up |
|-----------------|-------------------|
| Data acquisition, movement & transformation | `generate_data.py` → CSV → SQLite → outputs |
| SQL scripting & debugging | `sql/schema.sql`, `sql/je_tests.sql` |
| Python for financial analysis | `je_tests.py`, `run_pipeline.py` |
| Power BI visualization | `powerbi/README.md` |
| Communicating technical results to audit teams | `audit_report.xlsx`, `docs/AUDIT_TESTS.md` |
| Well-structured audit documentation | this README + docs + inline comments |

---

## Notes & assumptions

- All data is **synthetic and seeded** — results are reproducible and contain no
  real or sensitive information.
- SQLite is used as a zero-install stand-in for an enterprise database; the SQL
  is written in a portable style with porting notes for SQL Server / Oracle.
- This is an educational portfolio project and is **not** a substitute for
  professional audit judgement or licensed audit software.

## License

[MIT](LICENSE)