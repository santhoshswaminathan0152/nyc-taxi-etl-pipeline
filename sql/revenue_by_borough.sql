-- Trips, revenue and average fare by pickup borough
SELECT z.borough,
       count(*)                     AS trips,
       round(sum(f.total_amount))   AS revenue_usd,
       round(avg(f.fare_amount), 2) AS avg_fare_usd,
       round(avg(f.trip_distance), 2) AS avg_distance_mi
FROM fact_trips f
JOIN dim_zone z ON f.pu_zone_id = z.zone_id
GROUP BY z.borough
ORDER BY revenue_usd DESC;
