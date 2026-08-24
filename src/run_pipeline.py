"""End-to-end pipeline: generate -> load -> test -> score -> report.

This is the single command a user (or a CI job) runs to produce everything the
Power BI dashboard consumes::

    python -m src.run_pipeline

Outputs (written to ``data/output/``):
    journal_entries.csv      - the full ledger (Power BI fact table)
    findings.csv             - one row per (entry, failed test)
    entry_risk_scores.csv    - per-entry risk score + band (Power BI fact table)
    summary.json             - headline metrics for quick review
    audit_report.xlsx        - multi-tab workbook for non-technical reviewers
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import pandas as pd

from . import __version__
from .config_loader import load_config, resolve_path
from .database import load_dataframe, get_connection, run_sql_tests
from .generate_data import generate_dataset
from .je_tests import run_all_tests, score_entries


def _print_header(title: str) -> None:
    print(f"\n=== {title} ===")


def build_summary(df: pd.DataFrame, findings: pd.DataFrame,
                  scores: pd.DataFrame) -> Dict:
    """Headline metrics for the JSON summary and console output."""
    by_test = (
        findings.groupby("test_name")["entry_id"].nunique().sort_values(
            ascending=False
        )
        if not findings.empty
        else pd.Series(dtype=int)
    )
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool_version": __version__,
        "total_lines": int(len(df)),
        "total_entries": int(df["entry_id"].nunique()),
        "total_debit": round(float(df["debit"].sum()), 2),
        "total_credit": round(float(df["credit"].sum()), 2),
        "flagged_entries": int((scores["risk_score"] > 0).sum()),
        "high_risk_entries": int((scores["risk_band"] == "High").sum()),
        "medium_risk_entries": int((scores["risk_band"] == "Medium").sum()),
        "findings_by_test": {k: int(v) for k, v in by_test.items()},
    }


def write_outputs(out_dir: Path, df: pd.DataFrame, findings: pd.DataFrame,
                  scores: pd.DataFrame, summary: Dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    df.to_csv(out_dir / "journal_entries.csv", index=False)
    findings.to_csv(out_dir / "findings.csv", index=False)
    scores.to_csv(out_dir / "entry_risk_scores.csv", index=False)

    with (out_dir / "summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    # A reviewer-friendly Excel workbook (one tab per artefact).
    with pd.ExcelWriter(out_dir / "audit_report.xlsx", engine="openpyxl") as xl:
        pd.DataFrame([summary]).T.rename(columns={0: "value"}).to_excel(
            xl, sheet_name="Summary"
        )
        scores.to_excel(xl, sheet_name="Risk Scores", index=False)
        findings.to_excel(xl, sheet_name="Findings", index=False)
        # Top 100 highest-risk entries for a quick reviewer glance.
        scores.head(100).to_excel(xl, sheet_name="Top Risks", index=False)


def run(config_path: str | None = None, use_sql: bool = True) -> Dict:
    """Execute the full pipeline. Returns the summary dict."""
    cfg = load_config(config_path)

    _print_header("1/5 Generating synthetic general ledger")
    df = generate_dataset(cfg)
    raw_path = resolve_path(cfg["paths"]["raw_data"])
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(raw_path, index=False)
    print(f"  {len(df):,} lines / {df['entry_id'].nunique():,} entries "
          f"-> {raw_path.relative_to(resolve_path('.'))}")

    _print_header("2/5 Loading into SQLite")
    db_path = resolve_path(cfg["paths"]["database"])
    conn = get_connection(db_path)
    try:
        load_dataframe(conn, df)
    finally:
        conn.close()
    print(f"  Loaded into {db_path.relative_to(resolve_path('.'))}")

    _print_header("3/5 Running audit tests (pandas)")
    findings = run_all_tests(df, cfg)
    print(f"  {len(findings):,} findings across "
          f"{findings['entry_id'].nunique() if not findings.empty else 0:,} entries")

    if use_sql:
        _print_header("3b/5 Cross-checking with SQL tests")
        sql_findings = run_sql_tests(db_path)
        py_count = len(findings)
        sql_count = len(sql_findings)
        match = "MATCH" if py_count == sql_count else "DIFF"
        print(f"  pandas findings={py_count:,} | SQL findings={sql_count:,} "
              f"-> {match}")

    _print_header("4/5 Scoring entries by risk")
    scores = score_entries(df, findings, cfg)
    print(f"  High risk: {(scores['risk_band'] == 'High').sum():,} | "
          f"Medium: {(scores['risk_band'] == 'Medium').sum():,} | "
          f"Low: {(scores['risk_band'] == 'Low').sum():,}")

    _print_header("5/5 Writing outputs")
    summary = build_summary(df, findings, scores)
    out_dir = resolve_path(cfg["paths"]["output_dir"])
    write_outputs(out_dir, df, findings, scores, summary)
    for name in ["journal_entries.csv", "findings.csv", "entry_risk_scores.csv",
                 "summary.json", "audit_report.xlsx"]:
        print(f"  wrote {(out_dir / name).relative_to(resolve_path('.'))}")

    print("\nDone. Open data/output/audit_report.xlsx or connect Power BI to "
          "the CSVs (see powerbi/README.md).")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Journal Entry Testing pipeline end-to-end."
    )
    parser.add_argument("--config", default=None,
                        help="Path to a config YAML (default: config/config.yaml)")
    parser.add_argument("--no-sql", action="store_true",
                        help="Skip the SQL cross-check step.")
    args = parser.parse_args()
    run(config_path=args.config, use_sql=not args.no_sql)


if __name__ == "__main__":
    main()
