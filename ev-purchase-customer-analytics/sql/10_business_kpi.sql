-- name: business_kpi
SELECT COUNT(*) AS all_customers,
       SUM(f.source_set = 'train') AS labelled_customers,
       SUM(f.source_set = 'test') AS scoring_customers,
       ROUND(AVG(CASE WHEN f.source_set = 'train' THEN f.will_buy_ev = 'Yes' END), 6) AS observed_purchase_rate,
       ROUND(AVG(p.predicted_probability), 6) AS final_model_average_propensity,
       ROUND(AVG(s.high_potential_flag), 6) AS high_potential_share,
       ROUND(AVG(f.home_charging_possible = 'Yes'), 6) AS home_charging_share,
       ROUND(AVG(f.subsidy_available = 'Yes'), 6) AS subsidy_available_share,
       ROUND(AVG(f.charging_stations_near_home + f.charging_stations_near_work), 2) AS average_nearby_stations
FROM ev_customer_features f
JOIN ev_model_predictions p ON p.id = f.id
JOIN ev_customer_segments s ON s.id = f.id;
