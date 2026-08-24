# Power BI Dashboard Guide

The Python pipeline writes three Power BI–ready CSVs to `data/output/`. This
guide walks through building an **audit-style risk dashboard** on top of them.
No `.pbix` file is committed (they are large binaries), but following these
steps reproduces the intended dashboard in ~15 minutes.

## 1. Data sources

| File | Grain | Role in the model |
|------|-------|-------------------|
| `journal_entries.csv` | one row per GL **line** | Detail / drill-through table |
| `entry_risk_scores.csv` | one row per **entry** | Main fact table |
| `findings.csv` | one row per (entry, failed test) | Findings bridge table |

## 2. Load the data

1. **Home → Get Data → Text/CSV**, load all three files from `data/output/`.
2. In **Power Query**, set data types:
   - `posting_datetime`, `entry_date` → Date/Time
   - `total_amount`, `risk_score` → Decimal / Whole number
3. **Close & Apply**.

## 3. Model relationships

Create these relationships (Model view):

```
entry_risk_scores[entry_id]  1 --- *  journal_entries[entry_id]
entry_risk_scores[entry_id]  1 --- *  findings[entry_id]
```

Set the cross-filter direction to **Single** (from `entry_risk_scores` out).

## 4. Suggested DAX measures

```DAX
Total Entries      = DISTINCTCOUNT(entry_risk_scores[entry_id])
Flagged Entries    = CALCULATE([Total Entries], entry_risk_scores[risk_score] > 0)
High Risk Entries  = CALCULATE([Total Entries], entry_risk_scores[risk_band] = "High")
Flag Rate %        = DIVIDE([Flagged Entries], [Total Entries])
Total Debit        = SUM(journal_entries[debit])
Avg Risk Score     = AVERAGE(entry_risk_scores[risk_score])
```

## 5. Recommended report pages

### Page 1 — Executive Summary
- **Cards:** Total Entries, Flagged Entries, High Risk Entries, Flag Rate %.
- **Donut:** count of entries by `risk_band`.
- **Bar:** findings count by `test_name` (from `findings`).
- **Slicers:** `fiscal_period`, `source`, `risk_band`.

### Page 2 — Risk Register
- **Table** from `entry_risk_scores`: `entry_id`, `posting_datetime`,
  `user_name`, `total_amount`, `flags`, `risk_score`, `risk_band`.
- Sort by `risk_score` descending. Apply conditional formatting
  (red/amber/green) on `risk_band`.
- Enable **drill-through** to a detail page filtered by `entry_id`.

### Page 3 — Trends
- **Line chart:** flagged entries by `fiscal_period`.
- **Matrix:** `user_name` (rows) × `test_name` (columns), values = count —
  surfaces users associated with many flags.

## 6. Color guidance (audit convention)

| Risk band | Color |
|-----------|-------|
| High | `#C00000` (red) |
| Medium | `#ED7D31` (amber) |
| Low | `#FFC000` (yellow) |
| None | `#70AD47` (green) |

## 7. Refreshing

Re-run `python -m src.run_pipeline` to regenerate the CSVs, then click
**Refresh** in Power BI. Because the generator is seeded, results are stable
between runs unless you change `config/config.yaml`.
