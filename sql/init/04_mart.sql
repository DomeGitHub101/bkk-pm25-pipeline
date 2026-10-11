\connect pm25 pm25

-- Great-circle distance in km.
CREATE FUNCTION mart.distance_km(lat1 float8, lon1 float8, lat2 float8, lon2 float8)
RETURNS float8 LANGUAGE sql IMMUTABLE AS $$
    SELECT 6371 * 2 * asin(sqrt(
        power(sin(radians(lat2 - lat1) / 2), 2)
        + cos(radians(lat1)) * cos(radians(lat2)) * power(sin(radians(lon2 - lon1) / 2), 2)
    ))
$$;

-- Thai PCD PM2.5 bands (24h µg/m³, 2023 standard).
CREATE FUNCTION mart.pm25_level(v numeric)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN v IS NULL  THEN NULL
        WHEN v <= 15    THEN 'ดีมาก'
        WHEN v <= 25    THEN 'ดี'
        WHEN v <= 37.5  THEN 'ปานกลาง'
        WHEN v <= 75    THEN 'เริ่มมีผลกระทบต่อสุขภาพ'
        ELSE                 'มีผลกระทบต่อสุขภาพ'
    END
$$;

-- Which station(s) represent each district: its own stations, or the nearest one if it has none.
CREATE VIEW mart.v_district_station_map AS
SELECT d.district_code, d.name_th, d.name_en, s.station_id, 'in_district' AS method
FROM core.dim_district d
JOIN core.dim_station s ON s.district_th = d.name_th
UNION ALL
SELECT d.district_code, d.name_th, d.name_en, n.station_id, 'nearest_station' AS method
FROM core.dim_district d
CROSS JOIN LATERAL (
    SELECT s.station_id
    FROM core.dim_station s
    WHERE s.lat IS NOT NULL
    ORDER BY mart.distance_km(d.lat, d.lon, s.lat, s.lon)
    LIMIT 1
) n
WHERE NOT EXISTS (SELECT 1 FROM core.dim_station s WHERE s.district_th = d.name_th);

CREATE VIEW mart.v_district_pm25_hourly AS
SELECT
    m.district_code,
    m.name_th AS district_th,
    m.name_en AS district_en,
    f.measured_at,
    round(avg(f.pm25), 1)                    AS pm25,
    mart.pm25_level(round(avg(f.pm25), 1))   AS level,
    count(*)                                 AS n_stations,
    string_agg(f.station_id, ',' ORDER BY f.station_id) AS stations,
    m.method
FROM mart.v_district_station_map m
JOIN core.fact_pm25_hourly f USING (station_id)
GROUP BY m.district_code, m.name_th, m.name_en, f.measured_at, m.method;

-- Latest reading (within 6h) for all 50 districts, worst first.
CREATE VIEW mart.v_district_pm25_latest AS
SELECT
    d.district_code,
    d.name_th AS district_th,
    d.name_en AS district_en,
    l.measured_at,
    l.pm25,
    l.level,
    l.n_stations,
    l.stations,
    l.method
FROM core.dim_district d
LEFT JOIN LATERAL (
    SELECT h.*
    FROM mart.v_district_pm25_hourly h
    WHERE h.district_code = d.district_code
      AND h.measured_at >= now() - interval '6 hours'
    ORDER BY h.measured_at DESC
    LIMIT 1
) l ON true
ORDER BY l.pm25 DESC NULLS LAST;

-- SELECT * FROM mart.pm25_by_district('บางนา');          -- last 24h
-- SELECT * FROM mart.pm25_by_district('Bang Na', 72);    -- last 72h, English name works too
CREATE FUNCTION mart.pm25_by_district(p_district text, p_hours int DEFAULT 24)
RETURNS TABLE (district_th text, district_en text, measured_at timestamptz, pm25 numeric, level text, stations text)
LANGUAGE sql STABLE AS $$
    SELECT h.district_th, h.district_en, h.measured_at, h.pm25, h.level, h.stations
    FROM mart.v_district_pm25_hourly h
    WHERE (h.district_th = p_district OR h.district_en ILIKE p_district)
      AND h.measured_at >= now() - make_interval(hours => p_hours)
    ORDER BY h.measured_at DESC
$$;
