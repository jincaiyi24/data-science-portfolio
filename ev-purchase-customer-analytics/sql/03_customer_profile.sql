-- name: customer_profile
WITH profiled AS (
    SELECT f.*,
           CASE WHEN age < 35 THEN 'Under 35'
                WHEN age < 45 THEN '35-44'
                WHEN age < 55 THEN '45-54'
                ELSE '55+' END AS age_band,
           CASE WHEN annual_income_usd < 60000 THEN 'Under 60k'
                WHEN annual_income_usd < 90000 THEN '60k-90k'
                WHEN annual_income_usd < 120000 THEN '90k-120k'
                ELSE '120k+' END AS income_band
    FROM ev_customer_features f
    WHERE source_set = 'train'
)
SELECT age_band, income_band, city_type,
       COUNT(*) AS customers,
       ROUND(AVG(will_buy_ev = 'Yes'), 6) AS observed_purchase_rate,
       ROUND(AVG(annual_income_usd), 2) AS average_income,
       ROUND(AVG(daily_commute_km), 2) AS average_commute_km
FROM profiled
GROUP BY age_band, income_band, city_type
ORDER BY customers DESC, age_band, income_band, city_type;
