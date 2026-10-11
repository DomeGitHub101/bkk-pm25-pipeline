\connect pm25 pm25

-- raw  : API responses exactly as received (bronze)
-- core : cleaned dimensions + facts (silver)
-- mart : query-friendly views per district (gold)
CREATE SCHEMA raw;
CREATE SCHEMA core;
CREATE SCHEMA mart;

CREATE TABLE raw.air4thai_snapshot (
    snapshot_id bigserial PRIMARY KEY,
    fetched_at  timestamptz NOT NULL DEFAULT now(),
    payload     jsonb       NOT NULL
);

CREATE TABLE core.dim_district (
    district_code smallint PRIMARY KEY,
    name_th       text UNIQUE NOT NULL,
    name_en       text UNIQUE NOT NULL,
    lat           double precision NOT NULL,  -- approximate centroid
    lon           double precision NOT NULL
);

CREATE TABLE core.dim_station (
    station_id    text PRIMARY KEY,
    name_th       text,
    name_en       text,
    area_th       text,
    district_th   text,  -- parsed from area_th; not a FK so new/odd stations never break the load
    lat           double precision,
    lon           double precision,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE core.fact_pm25_hourly (
    station_id  text         NOT NULL REFERENCES core.dim_station,
    measured_at timestamptz  NOT NULL,
    pm25        numeric(6,1) NOT NULL,
    aqi         smallint,
    color_id    smallint,
    snapshot_id bigint REFERENCES raw.air4thai_snapshot,
    loaded_at   timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (station_id, measured_at)
);

CREATE INDEX ON core.fact_pm25_hourly (measured_at);
