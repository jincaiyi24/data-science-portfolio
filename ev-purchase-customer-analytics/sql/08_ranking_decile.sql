-- name: prediction_deciles
SELECT p.source_set, p.prediction_decile,
       COUNT(*) AS customers,
       ROUND(MIN(p.predicted_probability), 8) AS minimum_probability,
       ROUND(AVG(p.predicted_probability), 8) AS average_probability,
       ROUND(MAX(p.predicted_probability), 8) AS maximum_probability,
       ROUND(AVG(f.will_buy_ev = 'Yes'), 8) AS observed_purchase_rate
FROM ev_model_predictions p
JOIN ev_customer_features f ON f.id = p.id
GROUP BY p.source_set, p.prediction_decile
ORDER BY p.source_set, p.prediction_decile;

-- name: top_decile_profile
SELECT f.source_set, f.city_type, f.current_car_type, f.subsidy_available,
       COUNT(*) AS customers,
       ROUND(AVG(p.predicted_probability), 8) AS average_probability,
       ROUND(AVG(f.will_buy_ev = 'Yes'), 8) AS observed_purchase_rate,
       ROUND(AVG(f.annual_income_usd), 2) AS average_income
FROM ev_model_predictions p
JOIN ev_customer_features f ON f.id = p.id
WHERE p.prediction_decile = 1
GROUP BY f.source_set, f.city_type, f.current_car_type, f.subsidy_available
ORDER BY f.source_set, customers DESC;
