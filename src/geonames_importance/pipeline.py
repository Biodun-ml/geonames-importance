import csv
import io
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .columns import (
    ALTERNATE_NAME_COLUMNS,
    GEONAME_COLUMNS,
    OUTPUT_SCHEMA,
    SOURCE_COLUMNS,
    SOURCE_DTYPES,
)
from .overrides import apply_overrides, load_overrides
from .scoring import add_scores

DEFAULT_CHUNKSIZE = 200_000


@contextmanager
def open_dump(path: Path) -> Iterator[io.TextIOBase]:
    """Open a GeoNames .txt file, or the .txt inside a GeoNames .zip.

    The country zips also contain readme.txt, so the data member is picked by name.
    """
    if path.suffix.lower() != ".zip":
        with open(path, encoding="utf-8", newline="") as f:
            yield f
        return
    with zipfile.ZipFile(path) as zf:
        member = f"{path.stem}.txt"
        if member not in zf.namelist():
            members = [n for n in zf.namelist() if n.endswith(".txt") and n != "readme.txt"]
            if len(members) != 1:
                raise ValueError(f"cannot tell which file in {path} holds the data: {members}")
            member = members[0]
        with zf.open(member) as raw:
            yield io.TextIOWrapper(raw, encoding="utf-8", newline="")


def _read_tsv(f: io.TextIOBase, names: list[str], **kwargs) -> pd.io.parsers.TextFileReader:
    # QUOTE_NONE because names can contain a bare '"'. keep_default_na=False because
    # "NA" is Namibia's country code and "None" and "Null" are real place names.
    return pd.read_csv(
        f,
        sep="\t",
        header=None,
        names=names,
        quoting=csv.QUOTE_NONE,
        keep_default_na=False,
        na_values={"elevation": [""]},
        **kwargs,
    )


def read_geonames(f: io.TextIOBase, chunksize: int, usecols: list[str] | None = None):
    usecols = usecols or SOURCE_COLUMNS
    return _read_tsv(
        f,
        GEONAME_COLUMNS,
        usecols=usecols,
        dtype={c: SOURCE_DTYPES[c] for c in usecols},
        chunksize=chunksize,
    )


def load_iata_codes(path: Path, chunksize: int = DEFAULT_CHUNKSIZE) -> dict[int, str]:
    """Read IATA codes from alternateNamesV2 or any file in that format.

    Accepts the full dump, a per-country file, or rows pre-filtered with
    `grep -P '\\tiata\\t'`. Historic codes are skipped. If a place has more than
    one current code, the preferred one wins, then the lowest alternate_name_id.
    """
    frames = []
    with open_dump(path) as f:
        reader = _read_tsv(f, ALTERNATE_NAME_COLUMNS, dtype="str", chunksize=chunksize)
        for chunk in reader:
            chunk = chunk[(chunk["isolanguage"] == "iata") & (chunk["is_historic"] != "1")]
            frames.append(
                chunk[["alternate_name_id", "geonameid", "alternate_name", "is_preferred_name"]]
            )
    if not frames:
        return {}
    codes = pd.concat(frames, ignore_index=True)
    codes["alternate_name_id"] = codes["alternate_name_id"].astype("int64")
    codes["geonameid"] = codes["geonameid"].astype("int64")
    codes = codes.sort_values(
        ["geonameid", "is_preferred_name", "alternate_name_id"], ascending=[True, False, True]
    ).drop_duplicates("geonameid")
    return dict(zip(codes["geonameid"], codes["alternate_name"], strict=True))


def find_capitals(
    path: Path, chunksize: int, overrides: pd.DataFrame | None = None
) -> dict[str, str]:
    """Map country_code to the name of its PPLC place.

    Needs a full pass before scoring because the capital can sit anywhere in the
    file. A few countries have more than one PPLC; the most populous is used.
    """
    cols = ["geonameid", "name", "feature_code", "country_code", "population"]
    frames = []
    with open_dump(path) as f:
        for chunk in read_geonames(f, chunksize, usecols=cols):
            if overrides is not None:
                chunk = apply_overrides(chunk, overrides)
            frames.append(chunk[chunk["feature_code"] == "PPLC"])
    capitals = pd.concat(frames, ignore_index=True)
    if capitals.empty:
        return {}
    capitals = capitals.sort_values(
        ["country_code", "population", "geonameid"], ascending=[True, False, True]
    ).drop_duplicates("country_code")
    return dict(zip(capitals["country_code"], capitals["name"], strict=True))


def score_chunk(
    chunk: pd.DataFrame,
    capitals: dict[str, str],
    iata_codes: dict[int, str],
    overrides: pd.DataFrame | None = None,
) -> pd.DataFrame:
    chunk = chunk.copy()
    chunk["iata_code"] = chunk["geonameid"].map(iata_codes).astype("string")
    if overrides is not None:
        chunk = apply_overrides(chunk, overrides)
    return add_scores(chunk, capitals)


def run(
    source: Path,
    output: Path,
    iata_path: Path | None = None,
    overrides_path: Path | None = None,
    chunksize: int = DEFAULT_CHUNKSIZE,
) -> int:
    overrides = load_overrides(overrides_path) if overrides_path else None
    iata_codes = load_iata_codes(iata_path) if iata_path else {}
    capitals = find_capitals(source, chunksize, overrides)

    rows = 0
    with open_dump(source) as f, pq.ParquetWriter(output, OUTPUT_SCHEMA) as writer:
        for chunk in read_geonames(f, chunksize):
            scored = score_chunk(chunk, capitals, iata_codes, overrides)
            table = pa.Table.from_pandas(
                scored[OUTPUT_SCHEMA.names], schema=OUTPUT_SCHEMA, preserve_index=False
            )
            writer.write_table(table)
            rows += len(scored)
    return rows
