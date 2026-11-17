import pandas as pd
import pytest

from geonames_importance.cli import main
from geonames_importance.overrides import append_overrides, apply_overrides, load_overrides
from geonames_importance.pipeline import run

IKEJA_VILLAGE = 2338312


def test_round_trip_and_later_edit_wins(tmp_path):
    path = tmp_path / "overrides.csv"
    append_overrides(path, 1, {"population": "500"})
    append_overrides(path, 1, {"population": "700", "name": "New"})

    overrides = load_overrides(path)
    chunk = pd.DataFrame({"geonameid": [1, 2], "name": ["Old", "Other"], "population": [0, 5]})
    out = apply_overrides(chunk, overrides)

    assert out["population"].tolist() == [700, 5]
    assert out["name"].tolist() == ["New", "Other"]
    assert chunk["population"].tolist() == [0, 5]


def test_unknown_field_is_rejected(tmp_path):
    path = tmp_path / "overrides.csv"
    path.write_text("geonameid,field,value\n1,score,100\n")
    with pytest.raises(ValueError, match="cannot be overridden"):
        load_overrides(path)


def test_missing_file_means_no_overrides(tmp_path):
    assert load_overrides(tmp_path / "nope.csv").empty


def test_edit_records_override_and_score_applies_it(tmp_path, geonames_path, capsys):
    parquet, overrides = tmp_path / "ng.parquet", tmp_path / "overrides.csv"
    run(geonames_path, parquet)
    before = pd.read_parquet(parquet).set_index("geonameid").loc[IKEJA_VILLAGE]

    code = main(
        [
            "edit",
            str(parquet),
            str(IKEJA_VILLAGE),
            "--set",
            "population=250000",
            "--overrides",
            str(overrides),
        ]
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert "population: 0 -> 250000  (changed)" in printed
    assert "admin_type: village -> city  (changed)" in printed
    assert overrides.read_text().splitlines() == [
        "geonameid,field,value",
        f"{IKEJA_VILLAGE},population,250000",
    ]

    run(geonames_path, parquet, overrides_path=overrides)
    after = pd.read_parquet(parquet).set_index("geonameid").loc[IKEJA_VILLAGE]
    assert after["population"] == 250000
    assert after["admin_type"] == "city"
    assert after["score"] > before["score"]


def test_edit_rejects_bad_value_without_writing(tmp_path, geonames_path):
    parquet, overrides = tmp_path / "ng.parquet", tmp_path / "overrides.csv"
    run(geonames_path, parquet)
    code = main(
        [
            "edit",
            str(parquet),
            str(IKEJA_VILLAGE),
            "--set",
            "population=lots",
            "--overrides",
            str(overrides),
        ]
    )
    assert code == 2
    assert not overrides.exists()


def test_override_can_change_the_capital(tmp_path, geonames_path):
    overrides = tmp_path / "overrides.csv"
    append_overrides(overrides, 2352778, {"feature_code": "PPLA"})
    append_overrides(overrides, 2332459, {"feature_code": "PPLC"})
    parquet = tmp_path / "ng.parquet"
    run(geonames_path, parquet, overrides_path=overrides)
    df = pd.read_parquet(parquet).set_index("geonameid")
    assert df.loc[2338313, "country_capital"] == "Lagos"
    assert df.loc[2332459, "admin_type"] == "country_capital"


def test_iata_code_can_be_removed(tmp_path, geonames_path, alternate_names_path):
    overrides = tmp_path / "overrides.csv"
    append_overrides(overrides, 2332459, {"iata_code": ""})
    parquet = tmp_path / "ng.parquet"
    run(geonames_path, parquet, iata_path=alternate_names_path, overrides_path=overrides)
    df = pd.read_parquet(parquet).set_index("geonameid")
    assert pd.isna(df.loc[2332459, "iata_code"])
    assert df.loc[2332458, "iata_code"] == "LOS"
