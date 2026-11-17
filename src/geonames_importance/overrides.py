import csv
from pathlib import Path

import pandas as pd

from .columns import SOURCE_COLUMNS, SOURCE_DTYPES

OVERRIDE_HEADER = ["geonameid", "field", "value"]

EDITABLE_DTYPES = {c: SOURCE_DTYPES[c] for c in SOURCE_COLUMNS if c != "geonameid"}
EDITABLE_DTYPES["iata_code"] = "str"


def parse_value(field: str, raw: str):
    if field not in EDITABLE_DTYPES:
        raise ValueError(
            f"{field!r} cannot be overridden; editable fields: {', '.join(EDITABLE_DTYPES)}"
        )
    dtype = EDITABLE_DTYPES[field]
    if dtype == "str":
        # An empty iata_code means "remove the code"; other text fields keep "".
        return None if field == "iata_code" and raw == "" else raw
    if raw == "" and dtype == "Int32":
        return pd.NA
    if dtype == "float64":
        return float(raw)
    return int(raw)


def load_overrides(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=OVERRIDE_HEADER)
    overrides = pd.read_csv(path, dtype="str", keep_default_na=False)
    if list(overrides.columns) != OVERRIDE_HEADER:
        raise ValueError(f"{path}: expected header {','.join(OVERRIDE_HEADER)}")
    overrides["geonameid"] = overrides["geonameid"].astype("int64")
    for field, raw in zip(overrides["field"], overrides["value"], strict=True):
        parse_value(field, raw)
    return overrides


def apply_overrides(chunk: pd.DataFrame, overrides: pd.DataFrame) -> pd.DataFrame:
    hits = overrides[overrides["geonameid"].isin(chunk["geonameid"])]
    hits = hits[hits["field"].isin(chunk.columns)]
    if hits.empty:
        return chunk
    chunk = chunk.copy()
    row_of = pd.Series(chunk.index, index=chunk["geonameid"])
    # Rows are applied in file order, so a later edit to the same field wins.
    for geonameid, field, raw in hits.itertuples(index=False):
        chunk.loc[row_of[geonameid], field] = parse_value(field, raw)
    return chunk


def append_overrides(path: Path, geonameid: int, changes: dict[str, str]) -> None:
    new_file = not path.exists() or path.stat().st_size == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(OVERRIDE_HEADER)
        for field, raw in changes.items():
            writer.writerow([geonameid, field, raw])
