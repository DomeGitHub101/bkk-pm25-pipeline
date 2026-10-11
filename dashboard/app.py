"""Read-only web dashboard for the mart layer: JSON API + one static page."""

import os
from pathlib import Path

import psycopg
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row

DSN = os.environ.get("PM25_DSN", "postgresql://pm25:pm25@localhost:5433/pm25")
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Bangkok PM2.5 dashboard")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def query(sql: str, params: tuple = ()) -> list[dict]:
    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        conn.read_only = True
        return conn.execute(sql, params).fetchall()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/latest")
def latest() -> list[dict]:
    """Latest hourly reading and 24h average for all 50 districts (worst hourly first)."""
    return query("""
        SELECT l.district_code, l.district_th, l.district_en, l.measured_at,
               l.pm25::float AS pm25, l.level, l.n_stations, l.stations, l.method,
               a.pm25_24h::float AS pm25_24h, a.level_24h, a.n_hours
        FROM mart.v_district_pm25_latest l
        JOIN mart.v_district_pm25_24h a USING (district_code)
    """)


@app.get("/api/district/{code}")
def district(code: int, hours: int = Query(24, ge=1, le=24 * 90)) -> list[dict]:
    """Hourly series for one district, with the trailing 24h average at each hour."""
    rows = query("""
        SELECT measured_at, pm25::float AS pm25, pm25_24h::float AS pm25_24h, n_hours_24h
        FROM mart.v_district_pm25_rolling24h
        WHERE district_code = %s AND measured_at >= now() - make_interval(hours => %s)
        ORDER BY measured_at
    """, (code, hours))
    if not rows and not query("SELECT 1 FROM core.dim_district WHERE district_code = %s", (code,)):
        raise HTTPException(404, "unknown district")
    return rows


@app.get("/api/bangkok")
def bangkok(hours: int = Query(24, ge=1, le=24 * 90)) -> list[dict]:
    """Bangkok-wide hourly average across districts."""
    return query("""
        SELECT measured_at, round(avg(pm25), 1)::float AS pm25
        FROM mart.v_district_pm25_hourly
        WHERE measured_at >= now() - make_interval(hours => %s)
        GROUP BY measured_at
        ORDER BY measured_at
    """, (hours,))
