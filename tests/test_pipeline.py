import zipfile
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from geonames_importance.cli import top_places
from geonames_importance.columns import OUTPUT_SCHEMA
from geonames_importance.pipeline import find_capitals, load_iata_codes, run


def write_rows(path: Path, rows: list[list[str]]) -> Path:
    path.write_text("".join("\t".join(r) + "\n" for r in rows), encoding="utf-8")
    return path


def geoname_row(geonameid: int, name: str, code: str, country: str, population: int) -> list[str]:
    return [
        str(geonameid),
        name,
        name,
        "",
        "1.0",
        "2.0",
        "P",
        code,
        country,
        "",
        "01",
        "",
        "",
        "",
        str(population),
        "",
        "10",
        "UTC",
        "2024-01-01",
    ]


@pytest.fixture
def scored(tmp_path, geonames_path, alternate_names_path) -> pd.DataFrame:
    out = tmp_path / "out.parquet"
    run(geonames_path, out, iata_path=alternate_names_path)
    return pd.read_parquet(out).set_index("geonameid")


def test_chunk_size_does_not_change_output(tmp_path, geonames_path, alternate_names_path):
    small, large = tmp_path / "small.parquet", tmp_path / "large.parquet"
    run(geonames_path, small, iata_path=alternate_names_path, chunksize=5)
    run(geonames_path, large, iata_path=alternate_names_path, chunksize=1000)

    small_table, large_table = pq.read_table(small), pq.read_table(large)
    assert small_table.num_rows == 30
    assert pq.ParquetFile(small).metadata.num_row_groups == 6
    assert small_table.equals(large_table)


def test_output_schema(tmp_path, geonames_path):
    out = tmp_path / "out.parquet"
    run(geonames_path, out)
    assert pq.read_schema(out).names == OUTPUT_SCHEMA.names


def test_known_places(scored):
    abuja, lagos, ikeja, village = (scored.loc[i] for i in (2352778, 2332459, 2338313, 2338312))
    assert abuja["admin_type"] == "country_capital"
    assert abuja["iata_code"] == "ABV"
    assert abuja["importance"] == 5
    assert lagos["admin_type"] == "city"
    assert lagos["importance"] == 5
    assert ikeja["admin_type"] == "state_capital"
    assert village["admin_type"] == "village"
    assert village["importance"] == 1
    assert scored.loc[2332458, "admin_type"] == "airport"
    assert scored.loc[2332455, "admin_type"] == "island"


def test_ranking(scored):
    assert scored["score"].idxmax() == 2352778
    # The three Ikejas: state capital, local government area, and an unrelated village.
    assert (
        scored.loc[2338313, "score"] > scored.loc[7910350, "score"] > scored.loc[2338312, "score"]
    )


def test_country_capital_column(scored):
    assert (scored.loc[scored["country_code"] == "NG", "country_capital"] == "Abuja").all()
    assert scored.loc[2950159, "country_capital"] == "Berlin"
    assert scored.loc[3352136, "country_capital"] == "Windhoek"


def test_namibia_country_code_is_not_read_as_missing(scored):
    assert scored.loc[3352136, "country_code"] == "NA"


def test_missing_elevation_is_null_not_zero(scored):
    assert pd.isna(scored.loc[2352778, "elevation"])
    assert scored.loc[2332458, "elevation"] == 41


def test_find_capitals_prefers_most_populous_pplc(tmp_path):
    path = write_rows(
        tmp_path / "xx.txt",
        [
            geoname_row(1, "Sucre", "PPLC", "BO", 224_838),
            geoname_row(2, "La Paz", "PPLC", "BO", 812_799),
            geoname_row(3, "Somewhere", "PPL", "BO", 9_000_000),
        ],
    )
    assert find_capitals(path, chunksize=1) == {"BO": "La Paz"}


def test_load_iata_codes_skips_historic_and_other_languages(alternate_names_path):
    codes = load_iata_codes(alternate_names_path)
    assert codes[2332458] == "LOS"
    assert codes[2352778] == "ABV"
    assert 2339351 not in codes
    assert len(codes) == 6


def test_reads_country_zip_with_readme(tmp_path, geonames_path, alternate_names_path):
    archive = tmp_path / "NG.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "not data\n")
        zf.write(geonames_path, "NG.txt")
    from_zip, from_txt = tmp_path / "zip.parquet", tmp_path / "txt.parquet"
    run(archive, from_zip)
    run(geonames_path, from_txt)
    assert pq.read_table(from_zip).equals(pq.read_table(from_txt))


def test_names_with_bare_quotes_are_kept(tmp_path):
    path = write_rows(tmp_path / "q.txt", [geoname_row(1, 'Fort "Old" Town', "PPL", "NG", 10)])
    out = tmp_path / "q.parquet"
    run(path, out)
    assert pd.read_parquet(out)["name"][0] == 'Fort "Old" Town'


def test_top_places_matches_a_full_sort(tmp_path, geonames_path, alternate_names_path):
    out = tmp_path / "out.parquet"
    run(geonames_path, out, iata_path=alternate_names_path, chunksize=4)
    full = pd.read_parquet(out).sort_values(["score", "population"], ascending=False)

    top = top_places(out, 10)
    assert top["geonameid"].tolist() == full["geonameid"].head(10).tolist()

    airports = top_places(out, 5, country="NG", admin_type="airport")
    assert set(airports["geonameid"]) == {2332458, 2335202, 2339351}
