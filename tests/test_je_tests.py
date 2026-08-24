"""Unit tests for the audit tests, data generator and scoring.

These use small, hand-built DataFrames with known anomalies so each test's
behaviour is unambiguous. Run with::

    pytest -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from src import je_tests
from src.config_loader import load_config
from src.generate_data import generate_dataset
from src.je_tests import run_all_tests, score_entries


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _line(entry_id, line_no, account_code, debit, credit,
          posting="2025-03-12 10:00:00", entry_date="2025-03-12",
          user_id="U001", user_name="A. Patel"):
    return {
        "row_id": 0,
        "entry_id": entry_id,
        "line_number": line_no,
        "entry_date": entry_date,
        "posting_datetime": posting,
        "fiscal_period": 3,
        "user_id": user_id,
        "user_name": user_name,
        "source": "Manual",
        "account_code": account_code,
        "account_name": "Test",
        "description": "Test",
        "debit": debit,
        "credit": credit,
    }


# ---------------------------------------------------------------------------
# Individual test behaviours
# ---------------------------------------------------------------------------
def test_unbalanced_detects_imbalance(cfg):
    df = pd.DataFrame([
        _line("JE-1", 1, "1000", 100.0, 0.0),
        _line("JE-1", 2, "4000", 0.0, 95.0),   # 5.00 imbalance
        _line("JE-2", 1, "1000", 50.0, 0.0),
        _line("JE-2", 2, "4000", 0.0, 50.0),   # balanced
    ])
    flagged = set(je_tests.test_unbalanced_entries(df, cfg)["entry_id"])
    assert flagged == {"JE-1"}


def test_weekend_posting(cfg):
    df = pd.DataFrame([
        _line("JE-1", 1, "1000", 10.0, 0.0, posting="2025-03-15 10:00:00"),  # Sat
        _line("JE-2", 1, "1000", 10.0, 0.0, posting="2025-03-12 10:00:00"),  # Wed
    ])
    flagged = set(je_tests.test_weekend_postings(df, cfg)["entry_id"])
    assert flagged == {"JE-1"}


def test_after_hours(cfg):
    df = pd.DataFrame([
        _line("JE-1", 1, "1000", 10.0, 0.0, posting="2025-03-12 03:00:00"),
        _line("JE-2", 1, "1000", 10.0, 0.0, posting="2025-03-12 23:30:00"),
        _line("JE-3", 1, "1000", 10.0, 0.0, posting="2025-03-12 12:00:00"),
    ])
    flagged = set(je_tests.test_after_hours_postings(df, cfg)["entry_id"])
    assert flagged == {"JE-1", "JE-2"}


def test_round_dollar(cfg):
    df = pd.DataFrame([
        _line("JE-1", 1, "1000", 5000.0, 0.0),    # round
        _line("JE-2", 1, "1000", 4999.99, 0.0),   # not round
        _line("JE-3", 1, "1000", 500.0, 0.0),     # round but below min
    ])
    flagged = set(je_tests.test_round_dollar(df, cfg)["entry_id"])
    assert flagged == {"JE-1"}


def test_just_below_threshold(cfg):
    df = pd.DataFrame([
        _line("JE-1", 1, "1000", 9800.0, 0.0),   # just below 10k
        _line("JE-2", 1, "1000", 5000.0, 0.0),   # well below
        _line("JE-3", 1, "1000", 10500.0, 0.0),  # above
    ])
    flagged = set(je_tests.test_just_below_threshold(df, cfg)["entry_id"])
    assert flagged == {"JE-1"}


def test_backdated(cfg):
    df = pd.DataFrame([
        _line("JE-1", 1, "1000", 10.0, 0.0,
              posting="2025-03-12 10:00:00", entry_date="2025-01-01"),
        _line("JE-2", 1, "1000", 10.0, 0.0,
              posting="2025-03-12 10:00:00", entry_date="2025-03-11"),
    ])
    flagged = set(je_tests.test_backdated_entries(df, cfg)["entry_id"])
    assert flagged == {"JE-1"}


def test_rare_user(cfg):
    rows = []
    # U001 posts many entries; U900 posts only one.
    for i in range(40):
        rows.append(_line(f"COMMON-{i}", 1, "1000", 10.0, 0.0, user_id="U001"))
    rows.append(_line("RARE-1", 1, "1000", 10.0, 0.0,
                      user_id="U900", user_name="Temp"))
    df = pd.DataFrame(rows)
    flagged = set(je_tests.test_rare_users(df, cfg)["entry_id"])
    assert "RARE-1" in flagged
    assert "COMMON-0" not in flagged


def test_duplicate(cfg):
    df = pd.DataFrame([
        _line("JE-1", 1, "1000", 100.0, 0.0),
        _line("JE-1", 2, "4000", 0.0, 100.0),
        _line("JE-2", 1, "1000", 100.0, 0.0),   # identical content to JE-1
        _line("JE-2", 2, "4000", 0.0, 100.0),
        _line("JE-3", 1, "1000", 7.0, 0.0),     # unique
        _line("JE-3", 2, "4000", 0.0, 7.0),
    ])
    flagged = set(je_tests.test_duplicate_entries(df, cfg)["entry_id"])
    assert flagged == {"JE-1", "JE-2"}


# ---------------------------------------------------------------------------
# Scoring & integration
# ---------------------------------------------------------------------------
def test_scoring_assigns_bands(cfg):
    df = pd.DataFrame([
        _line("JE-1", 1, "1000", 100.0, 0.0),
        _line("JE-1", 2, "4000", 0.0, 90.0),   # unbalanced -> high weight
    ])
    findings = run_all_tests(df, cfg)
    scores = score_entries(df, findings, cfg)
    row = scores[scores["entry_id"] == "JE-1"].iloc[0]
    assert row["risk_score"] >= cfg["risk_weights"]["unbalanced_entry"]
    assert row["risk_band"] in {"Medium", "High"}


def test_no_findings_is_clean(cfg):
    df = pd.DataFrame([
        _line("JE-1", 1, "1000", 123.45, 0.0),
        _line("JE-1", 2, "4000", 0.0, 123.45),
    ])
    # Single common user, weekday daytime, balanced, non-round -> only the
    # rare-user test could fire (one entry <= 15). Confirm scoring still works.
    findings = run_all_tests(df, cfg)
    scores = score_entries(df, findings, cfg)
    assert len(scores) == 1
    assert set(scores.columns) >= {"entry_id", "risk_score", "risk_band"}


def test_generator_is_reproducible(cfg):
    df1 = generate_dataset(cfg)
    df2 = generate_dataset(cfg)
    pd.testing.assert_frame_equal(df1, df2)


def test_generator_produces_anomalies(cfg):
    df = generate_dataset(cfg)
    findings = run_all_tests(df, cfg)
    # The generator injects every anomaly type, so each test should fire.
    found_tests = set(findings["test_name"])
    expected = {
        "unbalanced_entry", "weekend_posting", "after_hours_posting",
        "round_dollar", "just_below_threshold", "rare_user",
        "backdated_entry", "duplicate_entry",
    }
    assert expected.issubset(found_tests)
