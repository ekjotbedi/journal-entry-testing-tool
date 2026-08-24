-- ---------------------------------------------------------------------------
-- Journal Entry Testing Tool - SQL audit tests
-- ---------------------------------------------------------------------------
-- Each block is a standard journal-entry test, returning a common shape:
--     entry_id | test_name | detail
-- The blocks are combined with UNION ALL so one execution returns every
-- finding. Thresholds mirror config/config.yaml (kept in sync intentionally).
--
-- Validated on SQLite. Notes for porting to SQL Server / Oracle are inline.
-- ---------------------------------------------------------------------------

-- (1) Unbalanced entries: debits must equal credits within an entry.
SELECT entry_id,
       'unbalanced_entry' AS test_name,
       'Debits do not equal credits' AS detail
FROM journal_entries
GROUP BY entry_id
HAVING ABS(SUM(debit) - SUM(credit)) > 0.01

UNION ALL

-- (2) Weekend postings.
--   SQLite: strftime('%w') -> 0=Sunday .. 6=Saturday.
--   SQL Server: DATEPART(WEEKDAY, posting_datetime).
SELECT DISTINCT entry_id,
       'weekend_posting' AS test_name,
       'Posted on a weekend' AS detail
FROM journal_entries
WHERE CAST(strftime('%w', posting_datetime) AS INTEGER) IN (0, 6)

UNION ALL

-- (3) After-hours postings (outside 07:00-19:00).
--   SQL Server: DATEPART(HOUR, posting_datetime).
SELECT DISTINCT entry_id,
       'after_hours_posting' AS test_name,
       'Posted outside 07:00-19:00' AS detail
FROM journal_entries
WHERE CAST(strftime('%H', posting_datetime) AS INTEGER) < 7
   OR CAST(strftime('%H', posting_datetime) AS INTEGER) >= 19

UNION ALL

-- (4) Round-dollar amounts: a whole multiple of 1,000 and >= 1,000.
SELECT DISTINCT entry_id,
       'round_dollar' AS test_name,
       'Amount is a round multiple of 1,000' AS detail
FROM journal_entries
WHERE (debit + credit) >= 1000
  AND CAST((debit + credit) AS INTEGER) = (debit + credit)
  AND (CAST((debit + credit) AS INTEGER) % 1000) = 0

UNION ALL

-- (5) Amounts just below the 10,000 approval threshold (review avoidance).
SELECT DISTINCT entry_id,
       'just_below_threshold' AS test_name,
       'Amount within 3% below approval limit 10,000' AS detail
FROM journal_entries
WHERE (debit + credit) >= 9700
  AND (debit + credit) < 10000

UNION ALL

-- (6) Backdated entries: posted more than 7 days after the entry date.
--   SQL Server: DATEDIFF(DAY, entry_date, posting_datetime) > 7.
SELECT DISTINCT entry_id,
       'backdated_entry' AS test_name,
       'Posted more than 7 days after the entry date' AS detail
FROM journal_entries
WHERE julianday(date(posting_datetime)) - julianday(entry_date) > 7

UNION ALL

-- (7) Rare posters: users responsible for <= 15 distinct entries overall.
SELECT DISTINCT je.entry_id,
       'rare_user' AS test_name,
       'Posted by a user with <= 15 total entries' AS detail
FROM journal_entries je
WHERE je.user_id IN (
        SELECT user_id
        FROM journal_entries
        GROUP BY user_id
        HAVING COUNT(DISTINCT entry_id) <= 15
)

UNION ALL

-- (8) Duplicate entries: distinct entry_ids with identical accounting content.
--   Build a per-entry signature from its ordered lines, then find collisions.
SELECT entry_id,
       'duplicate_entry' AS test_name,
       'Identical accounting content to another entry' AS detail
FROM (
    SELECT entry_id, signature
    FROM (
        SELECT entry_id,
               group_concat(account_code || ':' || debit || ':' || credit, '|')
                   AS signature
        FROM (
            SELECT entry_id, account_code, debit, credit
            FROM journal_entries
            ORDER BY entry_id, account_code, debit, credit
        )
        GROUP BY entry_id
    )
    WHERE signature IN (
        SELECT signature
        FROM (
            SELECT entry_id,
                   group_concat(account_code || ':' || debit || ':' || credit, '|')
                       AS signature
            FROM (
                SELECT entry_id, account_code, debit, credit
                FROM journal_entries
                ORDER BY entry_id, account_code, debit, credit
            )
            GROUP BY entry_id
        )
        GROUP BY signature
        HAVING COUNT(*) > 1
    )
);
