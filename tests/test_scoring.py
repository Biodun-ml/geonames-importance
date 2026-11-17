import pandas as pd
import pytest

from geonames_importance.scoring import (
    MAX_SCORE,
    add_scores,
    admin_type,
    importance_level,
    population_points,
    score,
)


def places(*rows: tuple) -> pd.DataFrame:
    df = pd.DataFrame(
        rows, columns=["feature_class", "feature_code", "population", "iata_code", "country_code"]
    )
    df["iata_code"] = df["iata_code"].astype("string")
    return df


def test_population_points_are_log_scaled_and_capped():
    points = population_points(pd.Series([0, 9, 99_999, 10_000_000, 40_000_000]))
    assert points[0] == 0
    assert points[1] == pytest.approx(50 / 7)
    assert points[2] == pytest.approx(50 * 5 / 7)
    assert points[3] == pytest.approx(50, abs=1e-4)
    assert points[4] == 50


def test_capital_with_iata_scores_near_the_top():
    df = places(("P", "PPLC", 10_000_000, "XYZ", "AA"))
    assert score(df)[0] == pytest.approx(MAX_SCORE, abs=0.01)


def test_unknown_feature_code_falls_back_to_class_points():
    df = places(("P", "PPLZZ", 0, None, "AA"), ("S", "XYZ", 0, None, "AA"))
    assert score(df).tolist() == [15, 3]


def test_iata_code_adds_bonus():
    df = places(("S", "AIRP", 0, None, "AA"), ("S", "AIRP", 0, "LOS", "AA"))
    assert score(df).tolist() == [40, 50]


def test_abandoned_place_scores_zero_without_population():
    df = places(("P", "PPLQ", 0, None, "AA"))
    assert score(df)[0] == 0


@pytest.mark.parametrize(
    ("value", "level"),
    [(0, 1), (24.99, 1), (25, 2), (50, 3), (74.99, 3), (75, 4), (99.99, 4), (100, 5), (130, 5)],
)
def test_importance_thresholds(value, level):
    assert importance_level(pd.Series([value]))[0] == level


def test_admin_type_labels():
    df = places(
        ("P", "PPLC", 3_000_000, None, "NG"),
        ("P", "PPLA", 300_000, None, "NG"),
        ("P", "PPL", 250_000, None, "NG"),
        ("P", "PPLA2", 20_000, None, "NG"),
        ("P", "PPL", 0, None, "NG"),
        ("P", "PPLQ", 0, None, "NG"),
        ("A", "ADM1", 0, None, "NG"),
        ("A", "ADM3", 0, None, "NG"),
        ("S", "AIRP", 0, None, "NG"),
        ("T", "ISL", 0, None, "NG"),
        ("H", "STM", 0, None, "NG"),
        ("S", "HTL", 0, None, "NG"),
    )
    assert admin_type(df).tolist() == [
        "country_capital",
        "state_capital",
        "city",
        "town",
        "village",
        "historical",
        "region",
        "district",
        "airport",
        "island",
        "natural",
        "facility",
    ]


def test_add_scores_attaches_country_capital():
    df = places(("P", "PPL", 100, None, "NG"), ("P", "PPL", 100, None, "ZZ"))
    out = add_scores(df, {"NG": "Abuja"})
    assert out["country_capital"].tolist()[0] == "Abuja"
    assert pd.isna(out["country_capital"].tolist()[1])
