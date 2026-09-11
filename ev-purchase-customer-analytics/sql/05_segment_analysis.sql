-- name: segment_analysis
WITH segment_kpi AS (
    SELECT s.customer_segment,
           COUNT(*) AS customers,
           AVG(s.segmentation_score) AS business_model_propensity,
           AVG(f.will_buy_ev = 'Yes') AS observed_purchase_rate,
           AVG(f.annual_income_usd) AS average_income,
           AVG(f.home_charging_possible = 'Yes') AS home_charging_share,
           AVG(f.subsidy_available = 'Yes') AS subsidy_share
    FROM ev_customer_segments s
    JOIN ev_customer_features f ON f.id = s.id
    WHERE f.source_set = 'train'
    GROUP BY s.customer_segment
)
SELECT customer_segment, customers,
       ROUND(customers / SUM(customers) OVER (), 6) AS customer_share,
       ROUND(business_model_propensity, 6) AS business_model_propensity,
       ROUND(observed_purchase_rate, 6) AS observed_purchase_rate,
       ROUND(average_income, 2) AS average_income,
       ROUND(home_charging_share, 6) AS home_charging_share,
       ROUND(subsidy_share, 6) AS subsidy_share,
       DENSE_RANK() OVER (ORDER BY business_model_propensity DESC) AS propensity_rank
FROM segment_kpi
ORDER BY propensity_rank;
