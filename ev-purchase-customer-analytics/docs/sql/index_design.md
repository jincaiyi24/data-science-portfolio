# MySQL Index Design

| Table | Index | Columns | Primary use |
|---|---|---|---|
| `ev_customer_features` | `PRIMARY` | `id` | Stable customer lookup and joins |
| `ev_customer_features` | `idx_feature_source` | `source_set` | Train/test filtering |
| `ev_customer_features` | `idx_city_type` | `city_type` | City profiles and slices |
| `ev_customer_features` | `idx_subsidy` | `subsidy_available` | Subsidy comparisons |
| `ev_customer_features` | `idx_home_charging` | `home_charging_possible` | Charging-access analysis |
| `ev_model_predictions` | `PRIMARY` | `id` | One prediction per customer |
| `ev_model_predictions` | `idx_propensity` | `predicted_probability DESC` | Top-customer ranking |
| `ev_model_predictions` | `idx_prediction_decile` | `source_set, prediction_decile` | Train/test decile analysis |
| `ev_customer_segments` | `idx_segment` | `customer_segment` | Segment filters and aggregation |
| `ev_customer_segments` | `idx_high_potential` | `high_potential_flag` | High-potential audience filters |
| `ev_model_metrics` | `idx_metric_model` | `model_name, model_version` | Model history lookup |
| `ev_model_metrics` | `idx_metric_auc` | `roc_auc DESC` | Best-result retrieval |

The low-cardinality indexes are useful for selective slices but may not be chosen for full-population aggregates. The generated `outputs/sql/query_performance_report.md` records the live MySQL `EXPLAIN` plans; those plans, not the mere presence of an index, determine whether the design helps a query.
