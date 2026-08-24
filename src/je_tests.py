"""Journal-entry audit tests implemented in pandas.

Each test inspects the general ledger and returns a tidy "findings" DataFrame
with one row per (entry_id, test_name) flag. The findings are then aggregated
into a per-entry risk score that drives the Power BI dashboard.

These mirror standard audit "journal entry testing" procedures used during an
external audit to identify entries warranting further investigation.
"""
from __future__ import annotations

from typing import Callable, Dict, List

import pandas as pd

FINDING_COLUMNS = ["entry_id", "test_name", "detail"]


# ---------------------------------------------------------------------------
# Individual tests. Each returns a findings DataFrame (may be empty).
# ---------------------------------------------------------------------------
def _empty_findings() -> pd.DataFrame:
    return pd.DataFrame(columns=FINDING_COLUMNS)


def _findings(entry_ids, test_name: str, detail: str) -> pd.DataFrame:
    entry_ids = list(dict.fromkeys(entry_ids))  # de-dupe, preserve order
    if not entry_ids:
        return _empty_findings()
    return pd.DataFrame(
        {"entry_id": entry_ids, "test_name": test_name, "detail": detail}
    )


def test_unbalanced_entries(df: pd.DataFrame, cfg: Dict) -> pd.DataFrame:
    """Debits must equal credits within each journal entry."""
    tol = cfg["tests"]["balance_tolerance"]
    sums = df.groupby("entry_id")[["debit", "credit"]].sum()
    imbalance = (sums["debit"] - sums["credit"]).abs()
    flagged = sums.index[imbalance > tol]
    return _findings(flagged, "unbalanced_entry",
                     "Debits do not equal credits")


def test_weekend_postings(df: pd.DataFrame, cfg: Dict) -> pd.DataFrame:
    """Entries posted on Saturday or Sunday."""
    dt = pd.to_datetime(df["posting_datetime"])
    weekend = df.loc[dt.dt.weekday >= 5, "entry_id"]
    return _findings(weekend, "weekend_posting", "Posted on a weekend")


def test_after_hours_postings(df: pd.DataFrame, cfg: Dict) -> pd.DataFrame:
    """Entries posted outside normal business hours."""
    start = cfg["tests"]["business_hours_start"]
    end = cfg["tests"]["business_hours_end"]
    hour = pd.to_datetime(df["posting_datetime"]).dt.hour
    mask = (hour < start) | (hour >= end)
    return _findings(df.loc[mask, "entry_id"], "after_hours_posting",
                     f"Posted outside {start:02d}:00-{end:02d}:00")


def test_round_dollar(df: pd.DataFrame, cfg: Dict) -> pd.DataFrame:
    """Suspiciously round amounts (e.g. exactly 25,000.00)."""
    mult = cfg["tests"]["round_dollar_multiple"]
    min_amt = cfg["tests"]["round_dollar_min_amount"]
    amount = df["debit"] + df["credit"]
    mask = (amount >= min_amt) & (amount % mult == 0)
    return _findings(df.loc[mask, "entry_id"], "round_dollar",
                     f"Amount is a round multiple of {mult:,}")


def test_just_below_threshold(df: pd.DataFrame, cfg: Dict) -> pd.DataFrame:
    """Amounts just under an approval limit (possible review avoidance)."""
    threshold = cfg["tests"]["approval_threshold"]
    tol = cfg["tests"]["just_below_tolerance"]
    lower = threshold * (1 - tol)
    amount = df["debit"] + df["credit"]
    mask = (amount >= lower) & (amount < threshold)
    return _findings(df.loc[mask, "entry_id"], "just_below_threshold",
                     f"Amount within {tol:.0%} below approval limit "
                     f"{threshold:,}")


def test_rare_users(df: pd.DataFrame, cfg: Dict) -> pd.DataFrame:
    """Entries from users who post very few entries overall."""
    max_entries = cfg["tests"]["rare_user_max_entries"]
    per_user = df.groupby("user_id")["entry_id"].nunique()
    rare_users = per_user.index[per_user <= max_entries]
    mask = df["user_id"].isin(rare_users)
    return _findings(df.loc[mask, "entry_id"], "rare_user",
                     f"Posted by a user with <= {max_entries} total entries")


def test_backdated_entries(df: pd.DataFrame, cfg: Dict) -> pd.DataFrame:
    """Posting date materially later than the transaction (entry) date."""
    posting = pd.to_datetime(df["posting_datetime"]).dt.normalize()
    entry = pd.to_datetime(df["entry_date"])
    gap_days = (posting - entry).dt.days
    mask = gap_days > 7
    return _findings(df.loc[mask, "entry_id"], "backdated_entry",
                     "Posted more than 7 days after the entry date")


def test_duplicate_entries(df: pd.DataFrame, cfg: Dict) -> pd.DataFrame:
    """Distinct entry ids that share identical accounting content."""
    # Build a signature per entry from its sorted lines.
    work = df.copy()
    work["signature"] = (
        work["account_code"].astype(str)
        + "|" + work["debit"].round(2).astype(str)
        + "|" + work["credit"].round(2).astype(str)
    )
    sigs = (
        work.sort_values(["entry_id", "signature"])
        .groupby("entry_id")["signature"]
        .apply(lambda s: "##".join(s))
    )
    dup_mask = sigs.duplicated(keep=False)
    flagged = sigs.index[dup_mask]
    return _findings(flagged, "duplicate_entry",
                     "Identical accounting content to another entry")


# Registry of all tests, in a stable order.
ALL_TESTS: List[Callable[[pd.DataFrame, Dict], pd.DataFrame]] = [
    test_unbalanced_entries,
    test_duplicate_entries,
    test_just_below_threshold,
    test_backdated_entries,
    test_weekend_postings,
    test_after_hours_postings,
    test_round_dollar,
    test_rare_users,
]


# ---------------------------------------------------------------------------
# Orchestration & scoring
# ---------------------------------------------------------------------------
def run_all_tests(df: pd.DataFrame, cfg: Dict) -> pd.DataFrame:
    """Run every test and return the combined findings DataFrame."""
    parts = [test(df, cfg) for test in ALL_TESTS]
    parts = [p for p in parts if not p.empty]
    if not parts:
        return _empty_findings()
    return pd.concat(parts, ignore_index=True)


def score_entries(df: pd.DataFrame, findings: pd.DataFrame,
                  cfg: Dict) -> pd.DataFrame:
    """Aggregate findings into a per-entry risk score.

    Returns one row per unique journal entry with its total amount, the list of
    tests it failed, the cumulative risk score and a risk band.
    """
    weights = cfg["risk_weights"]

    entry_summary = (
        df.groupby("entry_id")
        .agg(
            entry_date=("entry_date", "first"),
            posting_datetime=("posting_datetime", "first"),
            user_id=("user_id", "first"),
            user_name=("user_name", "first"),
            source=("source", "first"),
            total_debit=("debit", "sum"),
            total_credit=("credit", "sum"),
            line_count=("line_number", "count"),
        )
        .reset_index()
    )
    entry_summary["total_amount"] = entry_summary[["total_debit", "total_credit"]].max(axis=1)

    if findings.empty:
        entry_summary["flags"] = ""
        entry_summary["flag_count"] = 0
        entry_summary["risk_score"] = 0
    else:
        f = findings.copy()
        f["weight"] = f["test_name"].map(weights).fillna(0).astype(int)
        scores = f.groupby("entry_id")["weight"].sum()
        flags = f.groupby("entry_id")["test_name"].apply(
            lambda s: ", ".join(sorted(set(s)))
        )
        flag_counts = f.groupby("entry_id")["test_name"].nunique()

        entry_summary["risk_score"] = (
            entry_summary["entry_id"].map(scores).fillna(0).astype(int)
        )
        entry_summary["flags"] = entry_summary["entry_id"].map(flags).fillna("")
        entry_summary["flag_count"] = (
            entry_summary["entry_id"].map(flag_counts).fillna(0).astype(int)
        )

    entry_summary["risk_band"] = pd.cut(
        entry_summary["risk_score"],
        bins=[-1, 0, 19, 49, 10_000],
        labels=["None", "Low", "Medium", "High"],
    ).astype(str)

    return entry_summary.sort_values(
        ["risk_score", "total_amount"], ascending=False
    ).reset_index(drop=True)
