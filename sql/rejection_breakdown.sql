-- Why records were quarantined, as a share of all extracted rows (latest successful run per month)
WITH extracted AS (
    SELECT sum(rows_extracted) AS total
    FROM (SELECT month, arg_max(rows_extracted, started_at) AS rows_extracted
          FROM etl_run_log WHERE status = 'success' GROUP BY month)
)
SELECT reason,
       count(*) AS rows_rejected,
       round(100.0 * count(*) / (SELECT total FROM extracted), 3) AS pct_of_extracted
FROM quarantine_trips
GROUP BY reason
ORDER BY rows_rejected DESC;
