-- These queries are runnable examples for interview discussion; the automated exporter does not execute this file.

-- 1. Top 100 test customers by final competition-model probability.
SELECT f.id, f.city_type, s.customer_segment, p.predicted_probability
FROM ev_customer_features f
JOIN ev_model_predictions p ON p.id = f.id
JOIN ev_customer_segments s ON s.id = f.id
WHERE f.source_set = 'test'
ORDER BY p.predicted_probability DESC
LIMIT 100;

-- 2. Segment performance against the population baseline.
WITH base AS (
    SELECT AVG(will_buy_ev = 'Yes') AS overall_rate
    FROM ev_customer_features WHERE source_set = 'train'
)
SELECT s.customer_segment, COUNT(*) AS customers,
       AVG(f.will_buy_ev = 'Yes') AS purchase_rate,
       AVG(f.will_buy_ev = 'Yes') - base.overall_rate AS lift_vs_overall
FROM ev_customer_segments s
JOIN ev_customer_features f ON f.id = s.id
CROSS JOIN base
WHERE f.source_set = 'train'
GROUP BY s.customer_segment, base.overall_rate
ORDER BY lift_vs_overall DESC;

-- 3. Rank subsidy groups inside each city.
WITH grouped AS (
    SELECT city_type, subsidy_available, COUNT(*) AS customers,
           AVG(will_buy_ev = 'Yes') AS purchase_rate
    FROM ev_customer_features
    WHERE source_set = 'train'
    GROUP BY city_type, subsidy_available
)
SELECT *, DENSE_RANK() OVER (PARTITION BY city_type ORDER BY purchase_rate DESC) AS city_rank
FROM grouped;

-- 4. Find customers that exist in features but not predictions.
SELECT f.id, f.source_set
FROM ev_customer_features f
LEFT JOIN ev_model_predictions p ON p.id = f.id
WHERE p.id IS NULL;

-- 5. Compare current decile with the preceding decile.
WITH d AS (
    SELECT prediction_decile, AVG(predicted_probability) AS avg_score
    FROM ev_model_predictions WHERE source_set = 'test'
    GROUP BY prediction_decile
)
SELECT prediction_decile, avg_score,
       LAG(avg_score) OVER (ORDER BY prediction_decile) AS preceding_decile_score
FROM d;

-- 6. Retrieve the strongest recorded model result.
SELECT model_name, model_version, validation_type, roc_auc
FROM ev_model_metrics
WHERE roc_auc IS NOT NULL
ORDER BY roc_auc DESC
LIMIT 1;

-- 7. Count customers with weak infrastructure but high model propensity.
SELECT COUNT(*) AS customers
FROM ev_customer_features f
JOIN ev_model_predictions p ON p.id = f.id
WHERE f.home_charging_possible = 'No'
  AND f.charging_stations_near_home + f.charging_stations_near_work <= 3
  AND p.prediction_decile <= 2;

-- 8. Reconcile source-set labels across joined tables.
SELECT COUNT(*) AS source_mismatches
FROM ev_customer_features f
JOIN ev_model_predictions p ON p.id = f.id
JOIN ev_customer_segments s ON s.id = f.id
WHERE f.source_set <> p.source_set OR f.source_set <> s.source_set;

-- 9. Return the second-highest-propensity segment per city.
WITH ranked AS (
    SELECT f.city_type, s.customer_segment, AVG(p.predicted_probability) AS avg_score,
           DENSE_RANK() OVER (PARTITION BY f.city_type ORDER BY AVG(p.predicted_probability) DESC) AS rnk
    FROM ev_customer_features f
    JOIN ev_model_predictions p ON p.id = f.id
    JOIN ev_customer_segments s ON s.id = f.id
    GROUP BY f.city_type, s.customer_segment
)
SELECT * FROM ranked WHERE rnk = 2;

-- 10. Show repeated experiments for the same model and version.
SELECT model_name, model_version, COUNT(*) AS metric_rows,
       MIN(roc_auc) AS minimum_auc, MAX(roc_auc) AS maximum_auc
FROM ev_model_metrics
GROUP BY model_name, model_version
HAVING COUNT(*) > 1
ORDER BY metric_rows DESC;
