-- ---------------------------------------------------------------------------
-- Journal Entry Testing Tool - database schema
-- ---------------------------------------------------------------------------
-- Portable SQL (validated on SQLite; trivially adaptable to SQL Server/Oracle).
-- One row per journal-entry LINE. A journal entry is the set of lines sharing
-- an entry_id, and the debits within an entry must equal the credits.
-- ---------------------------------------------------------------------------

DROP TABLE IF EXISTS journal_entries;

CREATE TABLE journal_entries (
    row_id            INTEGER PRIMARY KEY,
    entry_id          TEXT    NOT NULL,   -- groups lines into one journal entry
    line_number       INTEGER NOT NULL,   -- line sequence within the entry
    entry_date        TEXT    NOT NULL,   -- transaction (effective) date
    posting_datetime  TEXT    NOT NULL,   -- when it was actually recorded
    fiscal_period     INTEGER NOT NULL,   -- accounting month (1-12)
    user_id           TEXT    NOT NULL,   -- who posted it
    user_name         TEXT    NOT NULL,
    source            TEXT    NOT NULL,   -- sub-ledger / module of origin
    account_code      TEXT    NOT NULL,
    account_name      TEXT    NOT NULL,
    description       TEXT,
    debit             REAL    NOT NULL DEFAULT 0,
    credit            REAL    NOT NULL DEFAULT 0
);

-- Indexes that mirror how the audit tests filter/group the data.
CREATE INDEX idx_je_entry  ON journal_entries (entry_id);
CREATE INDEX idx_je_user   ON journal_entries (user_id);
CREATE INDEX idx_je_period ON journal_entries (fiscal_period);
