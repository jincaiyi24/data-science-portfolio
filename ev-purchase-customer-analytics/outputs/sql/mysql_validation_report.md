# MySQL Pipeline Validation

- Checks passed: 13/13
- Overall status: PASS

| check                    |   expected |   actual | status   |
|:-------------------------|-----------:|---------:|:---------|
| feature_row_count        |     955236 |   955236 | PASS     |
| prediction_row_count     |     955236 |   955236 | PASS     |
| segment_row_count        |     955236 |   955236 | PASS     |
| metric_row_count         |         55 |       55 | PASS     |
| feature_duplicate_ids    |          0 |        0 | PASS     |
| prediction_duplicate_ids |          0 |        0 | PASS     |
| segment_duplicate_ids    |          0 |        0 | PASS     |
| train_target_nulls       |          0 |        0 | PASS     |
| test_target_non_nulls    |          0 |        0 | PASS     |
| prediction_nulls         |          0 |        0 | PASS     |
| prediction_out_of_range  |          0 |        0 | PASS     |
| missing_prediction_joins |          0 |        0 | PASS     |
| missing_segment_joins    |          0 |        0 | PASS     |
