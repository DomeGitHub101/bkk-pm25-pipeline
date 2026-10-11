\connect pm25 pm25

-- The Thai PM2.5 standard (37.5 µg/m³) is a 24-hour average, so hourly readings
-- alone can't say whether a district is "over the standard". These views add
-- 24h averages. n_hours shows how many hours the average is based on: a value
-- built from a few hours is less reliable than one built from a full day.

-- Trailing 24h average at every hour, per district (for trend charts).
CREATE VIEW mart.v_district_pm25_rolling24h AS
SELECT
    h.district_code,
    h.district_th,
    h.district_en,
    h.measured_at,
    h.pm25,
    round(avg(h.pm25) OVER w, 1) AS pm25_24h,
    count(*)          OVER w     AS n_hours_24h
FROM mart.v_district_pm25_hourly h
WINDOW w AS (
    PARTITION BY h.district_code
    ORDER BY h.measured_at
    RANGE BETWEEN interval '23 hours' PRECEDING AND CURRENT ROW
);

-- 24h average for all 50 districts right now, worst first.
CREATE VIEW mart.v_district_pm25_24h AS
SELECT
    d.district_code,
    d.name_th AS district_th,
    d.name_en AS district_en,
    a.pm25_24h,
    mart.pm25_level(a.pm25_24h) AS level_24h,
    a.max_1h,
    coalesce(a.n_hours, 0)      AS n_hours
FROM core.dim_district d
LEFT JOIN (
    SELECT district_code,
           round(avg(pm25), 1) AS pm25_24h,
           max(pm25)           AS max_1h,
           count(*)            AS n_hours
    FROM mart.v_district_pm25_hourly
    WHERE measured_at > now() - interval '24 hours'
    GROUP BY district_code
) a USING (district_code)
ORDER BY a.pm25_24h DESC NULLS LAST;

-- Daily summary per district (calendar day in Bangkok time).
CREATE VIEW mart.v_district_pm25_daily AS
SELECT
    district_code,
    district_th,
    district_en,
    (measured_at AT TIME ZONE 'Asia/Bangkok')::date AS day,
    round(avg(pm25), 1)                             AS pm25_avg,
    mart.pm25_level(round(avg(pm25), 1))            AS level,
    max(pm25)                                       AS pm25_max,
    count(*)                                        AS n_hours,
    count(*) FILTER (WHERE pm25 > 37.5)             AS hours_over_37_5
FROM mart.v_district_pm25_hourly
GROUP BY district_code, district_th, district_en, day;
