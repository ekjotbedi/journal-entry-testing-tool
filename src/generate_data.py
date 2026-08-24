"""Generate realistic synthetic general-ledger / journal-entry data.

Real client data can never be committed to a public repo, so this module
fabricates a believable general ledger. Crucially, it *deliberately* injects
the kinds of anomalies that auditors test for (weekend postings, round-dollar
amounts, unbalanced entries, etc.) so the test suite has something to find.

Run directly::

    python -m src.generate_data
"""
from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from .config_loader import load_config, resolve_path

# A small, realistic-looking chart of accounts (code -> name, normal balance).
CHART_OF_ACCOUNTS = [
    ("1000", "Cash", "debit"),
    ("1100", "Accounts Receivable", "debit"),
    ("1200", "Inventory", "debit"),
    ("1500", "Property, Plant & Equipment", "debit"),
    ("2000", "Accounts Payable", "credit"),
    ("2100", "Accrued Liabilities", "credit"),
    ("2500", "Long-Term Debt", "credit"),
    ("3000", "Common Stock", "credit"),
    ("3100", "Retained Earnings", "credit"),
    ("4000", "Sales Revenue", "credit"),
    ("5000", "Cost of Goods Sold", "debit"),
    ("6000", "Salaries Expense", "debit"),
    ("6100", "Rent Expense", "debit"),
    ("6200", "Utilities Expense", "debit"),
    ("6300", "Marketing Expense", "debit"),
]

# Posting users. A few high-volume users and several rare ones. The rare users
# are the ones the "rare poster" test should surface.
COMMON_USERS = [
    ("U001", "A. Patel"),
    ("U002", "J. Smith"),
    ("U003", "M. Garcia"),
    ("U004", "L. Chen"),
    ("U005", "R. Okafor"),
]
# A pool of occasional posters. Because rare-user entries are spread across
# many of these, each individual rare user ends up with only a handful of
# entries - exactly what the "rare poster" test is designed to surface.
RARE_USERS = [
    (f"U9{n:02d}", name)
    for n, name in enumerate(
        [
            "Temp Contractor", "System Admin", "External Consultant",
            "Interim Controller", "Audit Adjuster", "Treasury Backup",
            "Month-End Helper", "Acquisition Team", "Tax Provision",
            "Year-End Contractor", "Restructuring Lead", "Integration Analyst",
        ]
    )
]

SOURCES = ["AP Module", "AR Module", "Payroll", "Manual", "Bank Feed"]

DESCRIPTIONS = [
    "Monthly accrual",
    "Vendor invoice",
    "Customer payment",
    "Payroll run",
    "Depreciation",
    "Bank reconciliation adjustment",
    "Reclassification",
    "Prepaid amortization",
    "Revenue recognition",
    "Expense reimbursement",
]


class JournalEntryGenerator:
    """Builds a synthetic journal-entry dataset from the project config."""

    def __init__(self, config: Dict) -> None:
        self.cfg = config
        gen = config["data_generation"]
        self.seed = gen["seed"]
        self.num_entries = gen["num_entries"]
        self.fiscal_year = gen["fiscal_year"]
        self.rates = gen["anomaly_rates"]
        self.threshold = config["tests"]["approval_threshold"]

        # Seed both RNGs for fully reproducible output.
        random.seed(self.seed)
        np.random.seed(self.seed)

        self._rows: List[Dict] = []
        self._next_entry_seq = 1

    # -- public API --------------------------------------------------------
    def generate(self) -> pd.DataFrame:
        """Generate the dataset and return it as a tidy DataFrame."""
        # Each "entry" produces 2+ lines, so generate until we hit the target
        # number of lines.
        while len(self._rows) < self.num_entries:
            self._make_entry()

        df = pd.DataFrame(self._rows)
        # Trim to the exact requested number of lines for determinism.
        df = df.iloc[: self.num_entries].reset_index(drop=True)
        df = self._finalise(df)
        return df

    # -- entry construction -----------------------------------------------
    def _make_entry(self) -> None:
        entry_id = f"JE{self.fiscal_year}-{self._next_entry_seq:06d}"
        self._next_entry_seq += 1

        posting_dt = self._random_business_datetime()
        entry_date = posting_dt.date()
        source = random.choice(SOURCES)
        description = random.choice(DESCRIPTIONS)

        # --- decide which anomalies (if any) apply to this entry ----------
        flags = {name: (random.random() < rate) for name, rate in self.rates.items()}
        user_id, user_name = self._pick_user(flags["rare_user"])

        # Weekend / after-hours manipulate the timestamp.
        if flags["weekend_posting"]:
            posting_dt = self._shift_to_weekend(posting_dt)
        if flags["after_hours_posting"]:
            posting_dt = posting_dt.replace(hour=random.choice([2, 3, 4, 22, 23]))
        if flags["backdated_entry"]:
            # Posted well after the transaction supposedly occurred.
            entry_date = posting_dt.date() - timedelta(days=random.randint(30, 120))

        amount = self._pick_amount(flags)

        # Build a balanced two-line entry: one debit account, one credit.
        debit_acct = random.choice([a for a in CHART_OF_ACCOUNTS if a[2] == "debit"])
        credit_acct = random.choice([a for a in CHART_OF_ACCOUNTS if a[2] == "credit"])

        debit_amount = amount
        credit_amount = amount
        if flags["unbalanced_entry"]:
            # Introduce a genuine imbalance (a serious red flag).
            credit_amount = round(amount + random.uniform(1, 500), 2)

        lines = [
            self._line(entry_id, 1, posting_dt, entry_date, user_id, user_name,
                       source, description, debit_acct, debit_amount, 0.0),
            self._line(entry_id, 2, posting_dt, entry_date, user_id, user_name,
                       source, description, credit_acct, 0.0, credit_amount),
        ]
        self._rows.extend(lines)

        # Duplicate entry: re-post the same entry under a new id.
        if flags["duplicate_entry"]:
            dup_id = f"JE{self.fiscal_year}-{self._next_entry_seq:06d}"
            self._next_entry_seq += 1
            for ln in lines:
                dup = dict(ln)
                dup["entry_id"] = dup_id
                self._rows.append(dup)

    def _line(self, entry_id, line_no, posting_dt, entry_date, user_id,
              user_name, source, description, account, debit, credit) -> Dict:
        return {
            "entry_id": entry_id,
            "line_number": line_no,
            "entry_date": entry_date.isoformat(),
            "posting_datetime": posting_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "fiscal_period": posting_dt.month,
            "user_id": user_id,
            "user_name": user_name,
            "source": source,
            "account_code": account[0],
            "account_name": account[1],
            "description": description,
            "debit": round(float(debit), 2),
            "credit": round(float(credit), 2),
        }

    # -- helpers -----------------------------------------------------------
    def _pick_user(self, is_rare: bool):
        # Rare-user entries are spread across the large RARE_USERS pool so each
        # such user posts only a few times; everything else is a common poster.
        if is_rare:
            return random.choice(RARE_USERS)
        return random.choice(COMMON_USERS)

    def _pick_amount(self, flags: Dict[str, bool]) -> float:
        if flags["round_dollar"]:
            mult = self.cfg["tests"]["round_dollar_multiple"]
            return float(random.randint(1, 50) * mult)
        if flags["just_below_threshold"]:
            # e.g. 9,750 against a 10,000 limit.
            return round(self.threshold * random.uniform(0.97, 0.999), 2)
        # Normal log-normal-ish spread of amounts.
        return round(float(np.random.lognormal(mean=7.0, sigma=1.1)) + 50, 2)

    def _random_business_datetime(self) -> datetime:
        start = date(self.fiscal_year, 1, 1)
        day_offset = random.randint(0, 364)
        d = start + timedelta(days=day_offset)
        # Nudge onto a weekday so weekend postings are genuinely anomalous.
        while d.weekday() >= 5:
            d += timedelta(days=1)
        t = time(hour=random.randint(8, 18), minute=random.randint(0, 59),
                 second=random.randint(0, 59))
        return datetime.combine(d, t)

    @staticmethod
    def _shift_to_weekend(dt: datetime) -> datetime:
        # Move forward to the nearest Saturday.
        days_ahead = (5 - dt.weekday()) % 7
        days_ahead = days_ahead or 6
        return dt + timedelta(days=days_ahead)

    def _finalise(self, df: pd.DataFrame) -> pd.DataFrame:
        df.insert(0, "row_id", range(1, len(df) + 1))
        # Stable, audit-friendly ordering.
        df = df.sort_values(["entry_id", "line_number"]).reset_index(drop=True)
        return df


def generate_dataset(config: Dict | None = None) -> pd.DataFrame:
    """Convenience wrapper used by the pipeline and tests."""
    cfg = config or load_config()
    return JournalEntryGenerator(cfg).generate()


def main() -> None:
    cfg = load_config()
    df = generate_dataset(cfg)
    out_path = resolve_path(cfg["paths"]["raw_data"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"Generated {len(df):,} journal entry lines "
          f"({df['entry_id'].nunique():,} unique entries) -> {out_path}")


if __name__ == "__main__":
    main()
