-- name: purchase_propensity
WITH scored AS (
    SELECT f.id, f.source_set, f.city_type, f.subsidy_available,
           f.home_charging_possible, f.range_anxiety_level,
           f.charging_stations_near_home + f.charging_stations_near_work AS nearby_stations,
           p.predicted_probability
    FROM ev_customer_features f
    JOIN ev_model_predictions p ON p.id = f.id
)
SELECT source_set, city_type, subsidy_available, home_charging_possible, range_anxiety_level,
       COUNT(*) AS customers,
       ROUND(AVG(predicted_probability), 6) AS average_propensity,
       ROUND(AVG(nearby_stations), 2) AS average_nearby_stations
FROM scored
GROUP BY source_set, city_type, subsidy_available, home_charging_possible, range_anxiety_level
ORDER BY source_set, average_propensity DESC;
