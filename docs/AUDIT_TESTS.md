# Audit Test Reference

This document explains each journal-entry test in plain audit language — useful
both for reviewers and for talking through the project in an interview.

> **Why journal-entry testing?** Under auditing standards (e.g. CAS 240 / ISA
> 240, "The Auditor's Responsibilities Relating to Fraud"), auditors are
> required to test journal entries for evidence of management override of
> controls. The tests below are the classic data-driven procedures used to
> identify entries warranting further investigation.

| # | Test | What it looks for | Why it matters | Risk weight |
|---|------|-------------------|----------------|-------------|
| 1 | **Unbalanced entry** | Debits ≠ credits within an entry | A valid entry must balance; an imbalance signals a data integrity or override issue | 50 |
| 2 | **Duplicate entry** | Two entry IDs with identical accounting content | Possible double-posting or duplicate payment | 30 |
| 3 | **Just below threshold** | Amount just under the approval limit | Potential deliberate structuring to avoid review/approval | 25 |
| 4 | **Backdated entry** | Posted well after its effective date | May indicate period-cutoff manipulation | 20 |
| 5 | **Rare poster** | Entry by a user who rarely posts | Unusual preparers carry higher override risk | 12 |
| 6 | **Weekend posting** | Posted on Saturday/Sunday | Entries outside the normal cycle are higher risk | 10 |
| 7 | **After-hours posting** | Posted outside business hours | Same rationale as weekend postings | 10 |
| 8 | **Round dollar** | Suspiciously round amount (multiple of 1,000) | Estimates/manual top-side adjustments are often round | 8 |

## Risk scoring

Each entry accumulates the weights of every test it fails. The total is bucketed
into a band:

| Band | Score range |
|------|-------------|
| None | 0 |
| Low | 1–19 |
| Medium | 20–49 |
| High | 50+ |

All thresholds and weights live in [`config/config.yaml`](../config/config.yaml)
so an engagement team can tune them without touching code — mirroring how D&A
parameters are tailored per audit.

## Dual implementation

Every test is implemented **twice** and cross-checked at runtime:

- **pandas** — [`src/je_tests.py`](../src/je_tests.py), for flexible in-memory analysis.
- **SQL** — [`sql/je_tests.sql`](../sql/je_tests.sql), portable ANSI-style SQL
  that can be pointed at a real client database (SQL Server, Oracle, etc.).

The pipeline asserts both implementations return the same number of findings,
demonstrating that the SQL pushed down to the database matches the Python logic.
