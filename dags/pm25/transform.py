"""Pure transform/validation logic for Air4Thai payloads.

Kept free of Airflow imports so it can be unit-tested in isolation.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

BKK_TZ = timezone(timedelta(hours=7))
DISTRICT_RE = re.compile(r"เขต\s*([^\s,]+)")
PM25_MAX = 1000.0


def extract_district(area_th: str | None) -> str | None:
    """'แขวงคลองจั่น, เขตบางกะปิ,กรุงเทพฯ' -> 'บางกะปิ'."""
    matches = DISTRICT_RE.findall(area_th or "")
    return matches[-1] if matches else None


def to_number(value: Any) -> float | None:
    """Air4Thai uses '-1' (or blanks) for missing readings."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def parse_measured_at(date_str: str | None, time_str: str | None) -> str | None:
    """Combine Air4Thai date + time (local Bangkok time) into an ISO timestamp.

    Handles '24:00', which some stations report for midnight.
    """
    if not date_str or not time_str:
        return None
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d")
        hour, minute = (int(part) for part in time_str.split(":")[:2])
    except ValueError:
        return None
    return (day + timedelta(hours=hour, minutes=minute)).replace(tzinfo=BKK_TZ).isoformat()


def parse_bangkok_stations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the Air4Thai payload into one row per Bangkok station."""
    rows = []
    for station in payload.get("stations", []):
        area_th = station.get("areaTH") or ""
        if "กรุงเทพ" not in area_th:
            continue

        last = station.get("AQILast") or {}
        pm25 = last.get("PM25") or {}
        aqi = to_number(pm25.get("aqi"))
        color_id = to_number(pm25.get("color_id"))

        rows.append(
            {
                "station_id": station.get("stationID"),
                "name_th": station.get("nameTH"),
                "name_en": station.get("nameEN"),
                "area_th": area_th,
                "district_th": extract_district(area_th),
                "lat": to_number(station.get("lat")),
                "lon": to_number(station.get("long")),
                "measured_at": parse_measured_at(last.get("date"), last.get("time")),
                "pm25": to_number(pm25.get("value")),
                "aqi": int(aqi) if aqi is not None else None,
                "color_id": int(color_id) if color_id is not None else None,
            }
        )
    return rows


def validate_rows(rows: list[dict[str, Any]], min_stations: int) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors should fail the pipeline."""
    errors: list[str] = []
    warnings: list[str] = []

    if len(rows) < min_stations:
        errors.append(f"expected at least {min_stations} Bangkok stations, got {len(rows)}")

    ids = [row["station_id"] for row in rows]
    if None in ids:
        errors.append("station without stationID")
    duplicates = {sid for sid in ids if ids.count(sid) > 1}
    if duplicates:
        errors.append(f"duplicate station ids: {sorted(duplicates)}")

    for row in rows:
        sid = row["station_id"]
        if row["pm25"] is not None and not 0 <= row["pm25"] <= PM25_MAX:
            errors.append(f"{sid}: pm25 out of range ({row['pm25']})")
        if row["pm25"] is not None and row["measured_at"] is None:
            errors.append(f"{sid}: pm25 present but measured_at missing")
        if row["district_th"] is None:
            warnings.append(f"{sid}: could not parse district from {row['area_th']!r}")
        if row["pm25"] is None:
            warnings.append(f"{sid}: no PM2.5 reading")

    return errors, warnings
