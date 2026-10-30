# Interview Q&A: NYC Taxi ETL Pipeline

Likely questions about this project, with answers grounded in the code and the real run (Jan–Mar 2024: 9,554,778 rows extracted, 9,202,250 loaded, 352,528 quarantined, 26.2 s).

---

### 1. Walk me through the project in 60 seconds.
It's a batch ETL pipeline for NYC Yellow Taxi trip data. **Extract** downloads monthly parquet files and the zone lookup with retries and caching. **Transform** casts types, applies 12 validation rules and derives features like duration, speed and tip %. A **quality gate** checks row counts, rejection rate, nulls and reconciliation. **Load** writes a DuckDB star schema (`fact_trips` + three dimensions) one month at a time inside a transaction, re-checking referential integrity before commit. Bad rows go to a quarantine table with a reason, and every run is logged. Three months (9.5M rows) process in about 26 seconds.

### 2. ETL vs ELT: which is this, and why?
ETL: the data is cleaned in Python *before* it reaches the warehouse. That fits here because the validation rules are row-level, easy to unit-test in pandas, and the warehouse should only hold trusted data. In a cloud warehouse (Snowflake/BigQuery) I'd likely switch to **ELT**: land the raw parquet first, then transform with SQL/dbt, so raw history is preserved and transformations scale with the warehouse.

### 3. What does "idempotent" mean in your pipeline and how did you achieve it?
Running the same month twice gives the same result. Each load does `DELETE FROM fact_trips WHERE source_month = ?` then `INSERT` in **one transaction**, and dimensions use `INSERT OR REPLACE`. `trip_id` is deterministic (`yyyymm × 10⁸ + row index`). I verified it on real data: re-running 2024-01 left the fact table at exactly 9,202,250 rows, and a test (`test_rerunning_a_month_is_idempotent`) asserts it.

### 4. How do incremental loads work?
The unit of work is one month (the source publishes monthly files). The CLI takes `--months`, and only those months are extracted and replaced. That makes **backfills** and **reprocessing after a rule change** trivial: just re-run the affected months.

### 5. Why a star schema?
Analytics questions are "measure by dimension": revenue by borough, trips by hour or day of week. A central fact table at **trip grain** with small dimensions (`dim_zone` 265 rows, `dim_date` 91, `dim_payment_type` 7) keeps queries simple and fast: revenue by borough over 9.2M rows ran in 22 ms in DuckDB. It also avoids repeating zone names on 9M rows.

### 6. What is the grain of your fact table?
One row per valid taxi trip. Choosing the grain first prevents double counting; every measure (fare, tip, distance, duration) is additive or averageable at that level.

### 7. What data quality problems did you find in the real data?
3.69% of rows were invalid. The biggest issues were zero/negative distance (213,243 rows) and zero/negative fare (127,732). Smaller ones: trips over 6 hours (5,434), speeds above 80 mph (2,966), drop-off before pick-up (2,801), and 56 trips whose timestamps fell outside the file's month (some from 2002). Optional fields were null for 6.8% of loaded trips. There was also a subtle one: the zone CSV uses the string `"N/A"` as a borough, which pandas converts to NaN by default, so I read it with `keep_default_na=False`.

### 8. Why quarantine bad rows instead of dropping them?
Dropping hides problems. A quarantine table with a `reason` column lets analysts audit what was removed, lets the source team fix upstream issues, and allows reprocessing if a rule was too strict. It also makes the numbers reconcile: `loaded + rejected = extracted` is itself a quality check.

### 9. If a row breaks several rules, what reason does it get?
The first rule in priority order (`np.select` over an ordered list). For example, a row missing a required field is tagged `missing_required_field` even if its fare is also negative. This keeps exactly one reason per row, so counts add up.

### 10. What quality checks fail the run?
Batch level (before writing): minimum row count, rejection rate ≤ 15%, null % in required columns ≤ 1%, all durations/distances/fares positive, and row reconciliation. Load level (inside the transaction): no orphan foreign keys to `dim_zone`, `dim_date` or `dim_payment_type`. Thresholds live in `config.yaml`.

### 11. What happens if a check fails halfway through the load?
The load runs inside `BEGIN TRANSACTION`. If the referential-integrity check fails, it executes `ROLLBACK`, so the warehouse is exactly as it was before, never half-loaded. The failure is still written to `etl_run_log` with the reason. `test_referential_integrity_failure_rolls_back` covers this.

### 12. How do you make extraction reliable?
Retries with exponential backoff, a 60 s timeout, and an **atomic cache**: the file downloads to `*.part` and is renamed only when complete, so a crash never leaves a corrupt file that would be treated as cached on the next run.

### 13. How do you monitor the pipeline?
Two ways: structured **JSON logs** (one event per month with run id, counts, duration and status), which a log platform can parse, and the **`etl_run_log` table**, which can be queried for history, e.g. "rejection rate by month", or used to alert when it jumps.

### 14. How did you test the pipeline?
10 pytest tests on small synthetic DataFrames: each validation rule, derived features, deterministic IDs, quality-check pass/fail, idempotency, and rollback on integrity failure. Extraction is monkeypatched, so tests take under a second and run in **GitHub Actions** without downloading data.

### 15. Why DuckDB?
It's an embedded columnar OLAP database: no server, fast on analytical scans, and it reads pandas DataFrames directly. That makes it ideal for a laptop-scale warehouse. The same star schema and SQL would port to Postgres, Snowflake or BigQuery.

### 16. How would you scale this to 10× or 100× the data?
- Transform with **Spark or Polars** instead of pandas (pandas holds a month in memory).
- Store raw and clean data as **partitioned parquet** (by year/month) in S3/GCS.
- Load into a cloud warehouse with tables partitioned by `source_month` so the delete+insert becomes a cheap **partition overwrite**.
- Run months in parallel since they're independent.

### 17. How would you schedule it in production?
An **Airflow** (or Prefect) DAG with one task per month, retries, SLAs and alerting. The TLC publishes with a delay, so I'd schedule monthly and use a sensor to wait for the file. Because loads are idempotent, Airflow retries and backfills are safe.

### 18. How would you handle schema changes in the source?
`standardise()` selects and renames an explicit column list, so a new source column is ignored and a missing one fails loudly instead of silently loading garbage. I'd add a schema check on extract (expected columns and types) and version the mapping whenever TLC changes the file format.

### 19. What are slowly changing dimensions, and do you need them here?
SCDs track how dimension attributes change over time (Type 1 overwrites, Type 2 keeps history rows with valid-from/to dates). Here `dim_zone` is effectively static, so Type 1 (`INSERT OR REPLACE`) is enough. If TLC redrew zone boundaries, I'd move to Type 2 so old trips keep their original zone attributes.

### 20. What business insights did you get from the warehouse?
Manhattan accounts for 89.9% of trips and 75.6% of the $253.0M revenue. Queens has the highest average fare ($52.81), because 87.0% of Queens pickups are at JFK or LaGuardia. Weekday demand peaks at 18:00, and weekends stay busy past midnight. Card-paid trips tip a median of 25–27.5%.

### 21. What would you improve next?
Orchestration (Airflow), Great Expectations or dbt tests instead of hand-written checks, dbt models for marts, a Spark/Polars transform for scale, and adding the green-taxi and FHV datasets as new fact sources.

### 22. What was the hardest bug?
The first full run marked all three months as failed even though the data had loaded. The quality results contained numpy booleans, which `json.dumps` can't serialise, so building the log message raised *after* the commit. I cast the results to Python types, and the lesson was to keep anything that can fail out of the post-commit path. The other subtle one was the `"N/A"` borough being silently read as NaN.
