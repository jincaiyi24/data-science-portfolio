-- name: join_coverage
SELECT f.source_set,
       COUNT(*) AS feature_rows,
       COUNT(p.id) AS prediction_matches,
       COUNT(s.id) AS segment_matches,
       SUM(p.id IS NULL) AS missing_predictions,
       SUM(s.id IS NULL) AS missing_segments,
       ROUND(COUNT(p.id) / COUNT(*), 8) AS prediction_join_rate,
       ROUND(COUNT(s.id) / COUNT(*), 8) AS segment_join_rate
FROM ev_customer_features f
LEFT JOIN ev_model_predictions p ON p.id = f.id
LEFT JOIN ev_customer_segments s ON s.id = f.id
GROUP BY f.source_set
ORDER BY f.source_set;
