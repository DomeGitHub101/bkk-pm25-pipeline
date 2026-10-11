-- Connect: docker compose exec postgres psql -U pm25 -d pm25

-- 1) Current PM2.5 for all 50 districts, worst first
SELECT district_th, district_en, measured_at, pm25, level, method
FROM mart.v_district_pm25_latest;

-- 2) One district, last 24 hours (Thai or English name)
SELECT * FROM mart.pm25_by_district('บางนา');
SELECT * FROM mart.pm25_by_district('Chatuchak', 72);

-- 2b) 24h average for all districts right now (this is what the 37.5 standard applies to)
SELECT district_th, pm25_24h, level_24h, n_hours FROM mart.v_district_pm25_24h;

-- 2c) Daily summary per district
SELECT * FROM mart.v_district_pm25_daily ORDER BY day DESC, pm25_avg DESC;

-- 3) Daily average per district (compare with the 37.5 µg/m³ 24h standard)
SELECT district_th,
       date_trunc('day', measured_at) AS day,
       round(avg(pm25), 1)            AS pm25_daily_avg,
       mart.pm25_level(round(avg(pm25), 1)) AS level
FROM mart.v_district_pm25_hourly
GROUP BY district_th, day
ORDER BY day DESC, pm25_daily_avg DESC;

-- 4) Hours above the standard per district over the last 7 days
SELECT district_th, count(*) AS hours_over_standard
FROM mart.v_district_pm25_hourly
WHERE measured_at >= now() - interval '7 days' AND pm25 > 37.5
GROUP BY district_th
ORDER BY hours_over_standard DESC;

-- 5) Which hour of the day is dirtiest across Bangkok?
SELECT extract(hour FROM measured_at) AS hour_of_day, round(avg(pm25), 1) AS avg_pm25
FROM core.fact_pm25_hourly
GROUP BY hour_of_day
ORDER BY hour_of_day;

-- 6) Stations that stopped reporting (no reading in the last 3 hours)
SELECT s.station_id, s.district_th, max(f.measured_at) AS last_reading
FROM core.dim_station s
LEFT JOIN core.fact_pm25_hourly f USING (station_id)
GROUP BY s.station_id, s.district_th
HAVING max(f.measured_at) IS NULL OR max(f.measured_at) < now() - interval '3 hours'
ORDER BY last_reading NULLS FIRST;
