-- name: business_case_analysis
WITH candidates AS (
    SELECT f.city_type, f.subsidy_available, f.home_charging_possible,
           s.customer_segment, p.prediction_decile, p.predicted_probability,
           f.will_buy_ev
    FROM ev_customer_features f
    JOIN ev_model_predictions p ON p.id = f.id
    JOIN ev_customer_segments s ON s.id = f.id
    WHERE f.source_set = 'train'
)
SELECT city_type, subsidy_available, home_charging_possible, customer_segment,
       COUNT(*) AS customers,
       ROUND(AVG(predicted_probability), 6) AS average_propensity,
       ROUND(AVG(will_buy_ev = 'Yes'), 6) AS observed_purchase_rate,
       ROUND(AVG(prediction_decile <= 2), 6) AS top_two_decile_share
FROM candidates
GROUP BY city_type, subsidy_available, home_charging_possible, customer_segment
HAVING COUNT(*) >= 100
ORDER BY average_propensity DESC, customers DESC;
