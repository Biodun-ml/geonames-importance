import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from .overrides import append_overrides, parse_value
from .pipeline import DEFAULT_CHUNKSIZE, run
from .scoring import add_scores

TOP_COLUMNS = [
    "geonameid",
    "name",
    "country_code",
    "feature_code",
    "admin_type",
    "population",
    "iata_code",
    "score",
    "importance",
]
DERIVED = ["score", "importance", "admin_type", "country_capital"]


def cmd_score(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    rows = run(args.source, args.output, args.iata, args.overrides, args.chunksize)
    elapsed = time.perf_counter() - started
    print(f"wrote {rows:,} rows to {args.output} in {elapsed:.1f}s", file=sys.stderr)
    return 0


def top_places(
    parquet: Path, n: int, country: str | None = None, admin_type: str | None = None
) -> pd.DataFrame:
    # Keep a running top n per batch; loading the whole world file at once costs ~3.5 GB.
    best = pd.DataFrame()
    for batch in pq.ParquetFile(parquet).iter_batches(columns=TOP_COLUMNS):
        df = batch.to_pandas()
        if country:
            df = df[df["country_code"] == country]
        if admin_type:
            df = df[df["admin_type"] == admin_type]
        best = pd.concat([best, df]) if not best.empty else df
        best = best.nlargest(n, ["score", "population"])
    return best


def cmd_top(args: argparse.Namespace) -> int:
    top = top_places(args.parquet, args.n, args.country, args.admin_type)
    print(top.to_string(index=False, na_rep="-"))
    return 0


def _parse_assignments(pairs: list[str]) -> dict[str, str]:
    changes = {}
    for pair in pairs:
        field, sep, raw = pair.partition("=")
        if not sep:
            raise ValueError(f"expected FIELD=VALUE, got {pair!r}")
        parse_value(field, raw)
        changes[field] = raw
    return changes


def _capital_for(parquet: Path, country_code: str) -> dict[str, str]:
    table = pq.read_table(
        parquet, columns=["country_capital"], filters=[("country_code", "==", country_code)]
    )
    names = table.column("country_capital").drop_null()
    return {country_code: names[0].as_py()} if len(names) else {}


def cmd_edit(args: argparse.Namespace) -> int:
    changes = _parse_assignments(args.set)
    table = pq.read_table(args.parquet, filters=[("geonameid", "==", args.geonameid)])
    if table.num_rows == 0:
        print(f"geonameid {args.geonameid} not found in {args.parquet}", file=sys.stderr)
        return 1

    before = table.to_pandas()
    after = before.drop(columns=DERIVED)
    for field, raw in changes.items():
        after.loc[0, field] = parse_value(field, raw)
    after = add_scores(after, _capital_for(args.parquet, after.loc[0, "country_code"]))

    for field in [*changes, *DERIVED]:
        old, new = before.loc[0, field], after.loc[0, field]
        marker = "" if str(old) == str(new) else "  (changed)"
        print(f"{field:>16}: {old} -> {new}{marker}")

    append_overrides(args.overrides, args.geonameid, changes)
    print(
        f"saved to {args.overrides}; re-run `score --overrides {args.overrides}` "
        "to apply it to the Parquet file",
        file=sys.stderr,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="geonames-importance")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("score", help="score a GeoNames dump and write Parquet")
    p.add_argument("source", type=Path, help="allCountries.txt, NG.txt, NG.zip, ...")
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--iata", type=Path, help="alternateNamesV2 file (or its iata rows)")
    p.add_argument("--overrides", type=Path, help="CSV written by the edit command")
    p.add_argument("--chunksize", type=int, default=DEFAULT_CHUNKSIZE)
    p.set_defaults(func=cmd_score)

    p = sub.add_parser("top", help="print the highest scoring places")
    p.add_argument("parquet", type=Path)
    p.add_argument("-n", type=int, default=20)
    p.add_argument("--country", help="ISO country code, e.g. NG")
    p.add_argument("--admin-type", help="e.g. airport, state_capital")
    p.set_defaults(func=cmd_top)

    p = sub.add_parser("edit", help="override fields for one place and record the change")
    p.add_argument("parquet", type=Path, help="output of the score command")
    p.add_argument("geonameid", type=int)
    p.add_argument("--set", action="append", required=True, metavar="FIELD=VALUE")
    p.add_argument("--overrides", type=Path, default=Path("overrides.csv"))
    p.set_defaults(func=cmd_edit)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pd.set_option("display.width", 200)
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
