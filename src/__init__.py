"""Journal Entry Testing Tool - a data & analytics audit toolkit.

Modules
-------
config_loader   : load and validate the YAML configuration.
generate_data   : create realistic synthetic general-ledger data.
database        : load CSV data into SQLite and run SQL-based tests.
je_tests        : Python (pandas) implementations of the audit tests.
run_pipeline    : end-to-end orchestration (generate -> load -> test -> report).
"""

__version__ = "1.0.0"