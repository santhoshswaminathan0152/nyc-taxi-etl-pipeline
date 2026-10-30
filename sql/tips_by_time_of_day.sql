-- Median tip % for credit-card trips (cash tips are not recorded in the data)
SELECT f.time_of_day,
       count(*) AS trips,
       round(median(f.tip_pct), 1) AS median_tip_pct
FROM fact_trips f
JOIN dim_payment_type p ON f.payment_type_id = p.payment_type_id
WHERE p.description = 'Credit card'
GROUP BY f.time_of_day
ORDER BY median_tip_pct DESC;
