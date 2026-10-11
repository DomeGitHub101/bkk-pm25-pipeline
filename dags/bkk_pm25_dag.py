"""Hourly Bangkok PM2.5 pipeline: Air4Thai API -> raw -> core -> mart (Postgres)."""
from __future__ import annotations

import json
import logging
import tempfile
from contextlib import closing
from datetime import timedelta
from pathlib import Path

import certifi
import pendulum
import requests
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import dag, task

from pm25.transform import parse_bangkok_stations, validate_rows

API_URL = "https://air4thai.pcd.go.th/services/getNewAQI_JSON.php"
CONN_ID = "pm25_db"
MIN_STATIONS = 30
INTERMEDIATES = Path(__file__).parent / "pm25" / "certs" / "air4thai_intermediates.pem"

log = logging.getLogger(__name__)


def _ca_bundle() -> str:
    """certifi + the intermediates Air4Thai forgets to send (keeps TLS verification on)."""
    bundle = Path(tempfile.gettempdir()) / "air4thai-ca-bundle.pem"
    bundle.write_text(Path(certifi.where()).read_text() + INTERMEDIATES.read_text())
    return str(bundle)


def _connect():
    return closing(PostgresHook(postgres_conn_id=CONN_ID).get_conn())


@dag(
    dag_id="bkk_pm25_pipeline",
    description="Fetch Bangkok PM2.5 from Air4Thai every hour and load it into Postgres",
    schedule="15 * * * *",  # stations publish around the top of the hour
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Bangkok"),
    catchup=False,  # the API only exposes the latest reading, so backfill is meaningless
    max_active_runs=1,
    default_args={"retries": 3, "retry_delay": timedelta(minutes=5)},
    tags=["pm25", "bangkok", "air4thai"],
)
def bkk_pm25_pipeline():
    @task
    def extract() -> int:
        """Store the untouched API response in raw.air4thai_snapshot (bronze layer)."""
        resp = requests.get(API_URL, timeout=30, verify=_ca_bundle())
        resp.raise_for_status()
        payload = resp.json()

        with _connect() as conn, conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO raw.air4thai_snapshot (payload) VALUES (%s::jsonb) RETURNING snapshot_id",
                (json.dumps(payload, ensure_ascii=False),),
            )
            snapshot_id = cur.fetchone()[0]

        log.info("Saved snapshot %s with %s stations", snapshot_id, len(payload.get("stations", [])))
        return snapshot_id

    @task
    def transform(snapshot_id: int) -> list[dict]:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT payload FROM raw.air4thai_snapshot WHERE snapshot_id = %s", (snapshot_id,))
            payload = cur.fetchone()[0]

        rows = parse_bangkok_stations(payload)
        for row in rows:
            row["snapshot_id"] = snapshot_id
        log.info("Parsed %s Bangkok stations", len(rows))
        return rows

    @task
    def validate(rows: list[dict]) -> list[dict]:
        errors, warnings = validate_rows(rows, min_stations=MIN_STATIONS)
        for warning in warnings:
            log.warning(warning)
        if errors:
            raise ValueError("Data quality check failed:\n" + "\n".join(errors))
        return rows

    @task
    def load(rows: list[dict]) -> None:
        readings = [row for row in rows if row["pm25"] is not None and row["measured_at"] is not None]

        with _connect() as conn, conn, conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO core.dim_station (station_id, name_th, name_en, area_th, district_th, lat, lon)
                VALUES (%(station_id)s, %(name_th)s, %(name_en)s, %(area_th)s, %(district_th)s, %(lat)s, %(lon)s)
                ON CONFLICT (station_id) DO UPDATE SET
                    name_th = EXCLUDED.name_th,
                    name_en = EXCLUDED.name_en,
                    area_th = EXCLUDED.area_th,
                    district_th = EXCLUDED.district_th,
                    lat = EXCLUDED.lat,
                    lon = EXCLUDED.lon,
                    last_seen_at = now()
                """,
                rows,
            )
            cur.executemany(
                """
                INSERT INTO core.fact_pm25_hourly (station_id, measured_at, pm25, aqi, color_id, snapshot_id)
                VALUES (%(station_id)s, %(measured_at)s, %(pm25)s, %(aqi)s, %(color_id)s, %(snapshot_id)s)
                ON CONFLICT (station_id, measured_at) DO UPDATE SET
                    pm25 = EXCLUDED.pm25,
                    aqi = EXCLUDED.aqi,
                    color_id = EXCLUDED.color_id,
                    snapshot_id = EXCLUDED.snapshot_id,
                    loaded_at = now()
                """,
                readings,
            )

        log.info("Upserted %s stations and %s readings", len(rows), len(readings))

    load(validate(transform(extract())))


bkk_pm25_pipeline()
