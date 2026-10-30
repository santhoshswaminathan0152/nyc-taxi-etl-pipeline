-- Average trips per pickup hour, weekdays vs weekends
SELECT f.pickup_hour,
       d.is_weekend,
       count(*) / count(DISTINCT d.date_key) AS avg_trips
FROM fact_trips f
JOIN dim_date d ON f.pickup_date_key = d.date_key
GROUP BY ALL
ORDER BY d.is_weekend, f.pickup_hour;
