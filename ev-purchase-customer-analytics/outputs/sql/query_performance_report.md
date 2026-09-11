# MySQL Query Performance

Generated with MySQL `EXPLAIN` on the live project tables.

## purchase_propensity

|   id | select_type   | table   | partitions   | type   | possible_keys   | key            |   key_len | ref                        |   rows |   filtered | Extra                                        |
|-----:|:--------------|:--------|:-------------|:-------|:----------------|:---------------|----------:|:---------------------------|-------:|-----------:|:---------------------------------------------|
|    1 | SIMPLE        | p       |              | index  | PRIMARY         | idx_propensity |         8 |                            | 946335 |        100 | Using index; Using temporary; Using filesort |
|    1 | SIMPLE        | f       |              | eq_ref | PRIMARY         | PRIMARY        |         8 | ev_customer_analytics.p.id |      1 |        100 |                                              |

## segment_analysis

|   id | select_type   | table      | partitions   | type   | possible_keys              | key                |   key_len | ref                        |   rows |   filtered | Extra           |
|-----:|:--------------|:-----------|:-------------|:-------|:---------------------------|:-------------------|----------:|:---------------------------|-------:|-----------:|:----------------|
|    1 | PRIMARY       | <derived2> |              | ALL    |                            |                    |           |                            | 475209 |        100 | Using filesort  |
|    2 | DERIVED       | f          |              | ref    | PRIMARY,idx_feature_source | idx_feature_source |        34 | const                      | 475209 |        100 | Using temporary |
|    2 | DERIVED       | s          |              | eq_ref | PRIMARY,idx_segment        | PRIMARY            |         8 | ev_customer_analytics.f.id |      1 |        100 |                 |

## city_segment_ranking

|   id | select_type   | table      | partitions   | type   | possible_keys              | key                |   key_len | ref                        |   rows |   filtered | Extra           |
|-----:|:--------------|:-----------|:-------------|:-------|:---------------------------|:-------------------|----------:|:---------------------------|-------:|-----------:|:----------------|
|    1 | PRIMARY       | <derived2> |              | ALL    |                            |                    |           |                            | 475209 |        100 | Using filesort  |
|    2 | DERIVED       | f          |              | ref    | PRIMARY,idx_feature_source | idx_feature_source |        34 | const                      | 475209 |        100 | Using temporary |
|    2 | DERIVED       | p          |              | eq_ref | PRIMARY                    | PRIMARY            |         8 | ev_customer_analytics.f.id |      1 |        100 |                 |
|    2 | DERIVED       | s          |              | eq_ref | PRIMARY                    | PRIMARY            |         8 | ev_customer_analytics.f.id |      1 |        100 |                 |

## Index interpretation

- Customer slicing uses indexes on city, subsidy, source set and segment.
- Propensity ranking uses the prediction probability/decile index; window queries may still sort because ranking requires an ordered result.
- Foreign-key joins use primary-key lookups on `id`, so join coverage checks avoid full Cartesian work.
- Low-cardinality indexes help filtered reporting but are not expected to replace scans for full-population aggregates.
