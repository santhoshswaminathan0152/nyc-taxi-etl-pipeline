-- Daily trip volume
SELECT d.date, d.day_name, d.is_weekend, count(*) AS trips
FROM fact_trips f
JOIN dim_date d ON f.pickup_date_key = d.date_key
GROUP BY ALL
ORDER BY d.date;
