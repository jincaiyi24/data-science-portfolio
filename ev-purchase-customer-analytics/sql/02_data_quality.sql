-- name: data_quality
SELECT 'feature_rows' AS check_name, COUNT(*) AS check_value FROM ev_customer_features
UNION ALL SELECT 'feature_distinct_ids', COUNT(DISTINCT id) FROM ev_customer_features
UNION ALL SELECT 'train_rows', SUM(source_set = 'train') FROM ev_customer_features
UNION ALL SELECT 'test_rows', SUM(source_set = 'test') FROM ev_customer_features
UNION ALL SELECT 'train_target_nulls', SUM(source_set = 'train' AND will_buy_ev IS NULL) FROM ev_customer_features
UNION ALL SELECT 'test_target_non_nulls', SUM(source_set = 'test' AND will_buy_ev IS NOT NULL) FROM ev_customer_features
UNION ALL SELECT 'prediction_nulls', SUM(predicted_probability IS NULL) FROM ev_model_predictions
UNION ALL SELECT 'prediction_out_of_range', SUM(predicted_probability NOT BETWEEN 0 AND 1) FROM ev_model_predictions
UNION ALL SELECT 'segment_nulls', SUM(customer_segment IS NULL) FROM ev_customer_segments;
