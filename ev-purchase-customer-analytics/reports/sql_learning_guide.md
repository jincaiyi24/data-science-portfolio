# SQL Learning Guide

The former one-table SQL sketch has been replaced by a real MySQL pipeline. The source is still one customer dataset, but model predictions, business segments and experiment metrics are genuine derived entities with different update cycles, so they are now represented as four related tables rather than fictional transactions.

- `00_create_database.sql` and `01_schema.sql` define the database, primary/foreign keys, checks and query-oriented indexes.
- `02` through `11` provide named, automatically exported analyses for data quality, profiles, joins, windows, deciles, validation and supported business KPIs.
- `12_interview_queries.sql` contains runnable interview examples without inventing unsupported revenue metrics.
- `scripts/run_mysql_pipeline.py` performs the real chunked load, validation, export, reconciliation and EXPLAIN workflow.
- `docs/sql/SQL_PROJECT_MASTER_GUIDE_CN.md` is the complete 25-chapter Chinese study guide.
- `docs/interview/` contains 50 project questions, 30 coding questions and four presentation scripts.

Execution evidence is stored in `outputs/sql/`. The public package includes aggregate SQL outputs only; local credentials and customer-level data remain excluded.
