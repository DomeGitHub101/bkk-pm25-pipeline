import json
from pathlib import Path

import pytest

from pm25.transform import (
    extract_district,
    parse_bangkok_stations,
    parse_measured_at,
    to_number,
    validate_rows,
)

FIXTURE = Path(__file__).parent / "fixtures" / "air4thai_sample.json"


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("area", "expected"),
    [
        ("แขวงหิรัญรูจี เขตธนบุรี, กรุงเทพฯ", "ธนบุรี"),
        ("แขวงคลองจั่น, เขตบางกะปิ,กรุงเทพฯ", "บางกะปิ"),
        ("ริมถนนวิภาวดีรังสิต, เขตดินแดง, กรุงเทพฯ", "ดินแดง"),
        ("เขตคลองสามวา, กรุงเทพฯ", "คลองสามวา"),
        ("ต.ช้างเผือก อ.เมือง, เชียงใหม่", None),
        (None, None),
    ],
)
def test_extract_district(area, expected):
    assert extract_district(area) == expected


@pytest.mark.parametrize(("raw", "expected"), [("11.1", 11.1), ("0", 0.0), ("-1", None), ("", None), (None, None)])
def test_to_number(raw, expected):
    assert to_number(raw) == expected


def test_parse_measured_at_handles_midnight_as_24():
    assert parse_measured_at("2026-10-11", "24:00") == "2026-10-12T00:00:00+07:00"
    assert parse_measured_at("2026-10-11", "20:00") == "2026-10-11T20:00:00+07:00"
    assert parse_measured_at(None, "20:00") is None


def test_parse_keeps_only_bangkok(payload):
    rows = parse_bangkok_stations(payload)
    assert [r["station_id"] for r in rows] == ["02t", "o10"]

    first = rows[0]
    assert first["district_th"] == "ธนบุรี"
    assert first["pm25"] == 11.1
    assert first["aqi"] == 19
    assert first["lat"] == pytest.approx(13.732846)

    missing = rows[1]
    assert missing["pm25"] is None
    assert missing["aqi"] is None


def test_validate_flags_too_few_stations(payload):
    rows = parse_bangkok_stations(payload)
    errors, warnings = validate_rows(rows, min_stations=30)
    assert any("at least 30" in e for e in errors)
    assert any("o10: no PM2.5" in w for w in warnings)


def test_validate_flags_out_of_range_and_duplicates(payload):
    rows = parse_bangkok_stations(payload)
    rows[0]["pm25"] = 5000
    rows.append(dict(rows[0]))
    errors, _ = validate_rows(rows, min_stations=1)
    assert any("out of range" in e for e in errors)
    assert any("duplicate" in e for e in errors)


def test_validate_passes_clean_data(payload):
    rows = parse_bangkok_stations(payload)
    errors, _ = validate_rows(rows, min_stations=2)
    assert errors == []
