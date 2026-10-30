-- Busiest pickup -> dropoff zone pairs
SELECT pu.zone AS pickup_zone,
       dz.zone AS dropoff_zone,
       count(*) AS trips,
       round(median(f.duration_min), 1) AS median_minutes
FROM fact_trips f
JOIN dim_zone pu ON f.pu_zone_id = pu.zone_id
JOIN dim_zone dz ON f.do_zone_id = dz.zone_id
GROUP BY ALL
ORDER BY trips DESC
LIMIT 10;
