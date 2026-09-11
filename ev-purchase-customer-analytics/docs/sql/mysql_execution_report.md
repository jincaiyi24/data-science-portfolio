# MySQL Execution Report

## Environment

- Execution date: 2026-09-12
- Server: MySQL 8.0.42 on localhost:3306
- Database: `ev_customer_analytics`
- Client: SQLAlchemy 2 + PyMySQL
- Credentials: project-local restricted account loaded from ignored `.env`; password absent from code and logs

## Loaded tables

| Table | Rows | Source |
|---|---:|---|
| `ev_customer_features` | 955,236 | Official train + test features |
| `ev_model_predictions` | 955,236 | Final blend OOF + final blend test prediction |
| `ev_customer_segments` | 955,236 | Existing multi-seed business-model segmentation |
| `ev_model_metrics` | 55 | Existing model, fold, seed, ablation and ensemble tables |

## Validation evidence

- Database checks: 13/13 PASS
- Named analytical exports: 13/13 completed
- Python-SQL reconciliations: 18/18 PASS
- Maximum reconciliation difference: 0
- Prediction/segment join coverage: 100% for train and test
- Missing or out-of-range probabilities: 0

## Performance observation

Primary-key joins use `eq_ref` lookups. Full-population aggregations scan roughly the labelled or scored population and use temporary sorting for grouped/window results; this is expected for queries that return population-wide summaries. The live plans are preserved in `outputs/sql/query_performance_report.md`.

## Scope boundary

This execution validates the database implementation, not a new model run. The final competition result remains OOF ROC-AUC 0.945713 and Kaggle Public ROC-AUC 0.94589. The existing business segmentation continues to use the multi-seed base-feature model with OOF ROC-AUC 0.941993.
