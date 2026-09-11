-- name: city_segment_ranking
WITH city_segment AS (
    SELECT f.city_type, s.customer_segment,
           COUNT(*) AS customers,
           AVG(p.predicted_probability) AS final_model_propensity,
           AVG(f.will_buy_ev = 'Yes') AS observed_purchase_rate
    FROM ev_customer_features f
    JOIN ev_model_predictions p ON p.id = f.id
    JOIN ev_customer_segments s ON s.id = f.id
    WHERE f.source_set = 'train'
    GROUP BY f.city_type, s.customer_segment
)
SELECT city_type, customer_segment, customers,
       ROUND(customers / SUM(customers) OVER (PARTITION BY city_type), 6) AS share_within_city,
       ROUND(final_model_propensity, 6) AS final_model_propensity,
       ROUND(observed_purchase_rate, 6) AS observed_purchase_rate,
       DENSE_RANK() OVER (PARTITION BY city_type ORDER BY final_model_propensity DESC) AS rank_within_city,
       ROUND(final_model_propensity - LAG(final_model_propensity) OVER (
           PARTITION BY city_type ORDER BY final_model_propensity DESC
       ), 6) AS gap_from_previous
FROM city_segment
ORDER BY city_type, rank_within_city;

-- name: income_segment_ranking
WITH income_banded AS (
    SELECT f.id,
           CASE WHEN f.annual_income_usd < 60000 THEN 'Under 60k'
                WHEN f.annual_income_usd < 90000 THEN '60k-90k'
                WHEN f.annual_income_usd < 120000 THEN '90k-120k'
                ELSE '120k+' END AS income_band,
           s.customer_segment, p.predicted_probability
    FROM ev_customer_features f
    JOIN ev_customer_segments s ON s.id = f.id
    JOIN ev_model_predictions p ON p.id = f.id
    WHERE f.source_set = 'train'
), summary AS (
    SELECT income_band, customer_segment, COUNT(*) AS customers,
           AVG(predicted_probability) AS average_propensity
    FROM income_banded
    GROUP BY income_band, customer_segment
)
SELECT income_band, customer_segment, customers,
       ROUND(average_propensity, 6) AS average_propensity,
       ROW_NUMBER() OVER (PARTITION BY income_band ORDER BY average_propensity DESC, customer_segment) AS propensity_rank
FROM summary
ORDER BY income_band, propensity_rank;
