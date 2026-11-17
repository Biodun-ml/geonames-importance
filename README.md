# geonames-importance

Scores every place in a [GeoNames](https://www.geonames.org/) dump by how important it is,
from 0 to 130, and buckets the score into levels 1 to 5. The score comes from the feature code
(capital, state capital, airport, ...), a log-scaled population, and whether the place has an
IATA code. It reads the dump in chunks and writes Parquet as it goes, so the full 13.5 million
row `allCountries` file runs in under 700 MB of memory.

I use this kind of ranking to decide which places to show first in search and autocomplete,
and to drop the long tail of unnamed hills and streams when only real destinations matter.

## Install

```
pip install -e .            # pandas, pyarrow
pip install -e '.[dev]'     # plus pytest and ruff
```

Python 3.10+.

## Data

Download a country file or the whole world from <https://download.geonames.org/export/dump/>.
Zip files can be passed directly.

```
curl -O https://download.geonames.org/export/dump/NG.zip
curl -o alt-NG.zip https://download.geonames.org/export/dump/alternatenames/NG.zip  # optional, IATA codes
```

`--iata` accepts `alternateNamesV2.zip`, a per-country file from `alternatenames/`, or just the
IATA rows if you have already extracted them:

```
unzip -p alternateNamesV2.zip alternateNamesV2.txt | grep -P '\tiata\t' > iata.tsv
```

## Usage

```
$ geonames-importance score NG.zip -o ng.parquet --iata alt-NG.zip
wrote 76,332 rows to ng.parquet in 0.5s

$ geonames-importance top ng.parquet -n 8
 geonameid                        name country_code feature_code      admin_type  population iata_code  score  importance
   2352778                       Abuja           NG         PPLC country_capital     2690000       ABV 125.93           5
   2328926 Federal Republic of Nigeria           NG         PCLI         country   237527782         - 120.00           5
   2335204                        Kano           NG         PPLA   state_capital     4910000       KAN 112.79           5
   2339354                      Ibadan           NG         PPLA   state_capital     3649000       IBA 111.87           5
   2324774               Port Harcourt           NG         PPLA   state_capital     2120000       PHC 110.19           5
   2335727                      Kaduna           NG         PPLA   state_capital     1850000       KAD 109.77           5
   2347283                  Benin City           NG         PPLA   state_capital     1782000       BNI 109.65           5
   2331447                   Maiduguri           NG         PPLA   state_capital     1110000       MIU 108.18           5

$ geonames-importance top ng.parquet -n 3 --admin-type airport
 geonameid                                name country_code feature_code admin_type  population iata_code  score  importance
   2322910                              Sokoto           NG         AIRP    airport           0       SKO   50.0           3
   2324773 Port Harcourt International Airport           NG         AIRP    airport           0       PHC   50.0           3
   2331139                     Makurdi Airport           NG         AIRP    airport           0       MDI   50.0           3
```

`top` also takes `--country NG`, which is useful on the world file.

### Fixing a place by hand

GeoNames has errors, and hand edits made directly to an output file get lost the next time it
is regenerated. `edit` shows what a change does to the score, then appends it to an overrides
CSV. `score --overrides` applies that file on every run, so the fix is scored by the same rules
as everything else.

Ajah is a Lagos suburb that GeoNames codes as `PPLX` (section of a populated place):

```
$ geonames-importance edit ng.parquet 2351521 --set feature_code=PPL
    feature_code: PPLX -> PPL  (changed)
           score: 8.0 -> 15.0  (changed)
      importance: 1 -> 1
      admin_type: neighbourhood -> village  (changed)
 country_capital: Abuja -> Abuja
saved to overrides.csv; re-run `score --overrides overrides.csv` to apply it to the Parquet file

$ cat overrides.csv
geonameid,field,value
2351521,feature_code,PPL

$ geonames-importance score NG.zip -o ng.parquet --iata alt-NG.zip --overrides overrides.csv
```

Any source column except `geonameid` and `alternatenames` can be overridden, plus `iata_code`
(an empty value removes the code). Later rows for the same field win. Overrides are applied
before the capital lookup, so changing which place is `PPLC` changes `country_capital` too.

## Output

All source columns except `alternatenames`, plus:

| column            | meaning                                                         |
|-------------------|-----------------------------------------------------------------|
| `iata_code`       | from alternateNamesV2, or null                                  |
| `score`           | 0 to 130                                                        |
| `importance`      | 1 to 5                                                          |
| `admin_type`      | normalised label, see below                                     |
| `country_capital` | name of the country's `PPLC` place, the same on every row of a country |

## How scoring works

`score = feature points + population points + IATA points`

**Feature points (max 70).** The full table is `FEATURE_POINTS` in
[`scoring.py`](src/geonames_importance/scoring.py). The main ones:

| code                  | points | code              | points |
|-----------------------|-------:|-------------------|-------:|
| PCLI (country)        | 70     | ADM1              | 45     |
| PPLC (capital)        | 70     | ADM2              | 30     |
| PPLG (seat of govt.)  | 60     | ADM3              | 20     |
| PPLA                  | 55     | ADM4              | 12     |
| PPLA2                 | 40     | AIRP              | 40     |
| PPLA3                 | 30     | ISL, PRT          | 20     |
| PPLA4                 | 22     | PRK, ATOL         | 15     |
| PPL                   | 15     | AIRF, RESN, VLC   | 12     |
| PPLX                  | 8      | LK, BCH, RSTN     | 10     |
| PPLH, PPLQ, PPLW      | 0 to 2 | MT, MUS, CSTL     | 8      |

Codes not in the table get points by feature class: P 15, A 10, S/T/H/L 3, V/R 1, U 0.

**Population points (max 50).** `50 * log10(1 + population) / 7`, capped at 50. A place of
10 million gets the full 50, 100,000 gets about 36, 1,000 about 21. The log keeps a megacity
from drowning out the feature code.

**IATA points.** 10 if the place has a current (non-historic) IATA code.

**Importance level.**

| level | score    |
|------:|----------|
| 5     | 100 +    |
| 4     | 75 to 99 |
| 3     | 50 to 74 |
| 2     | 25 to 49 |
| 1     | below 25 |

So a state capital of 300,000 people is level 4, or 5 if it has an airport code. A national
capital is 5, an airport with a code is 3, and a village with no population figure is 1.

**admin_type.** `PPLC` country_capital, `PPLG` government_seat, `PPLA` state_capital,
`ADM1` region, `ADM2` to `ADM5` district, `AIRP`/`AIRF` airport, `ISL`/`ISLS`/`ATOL` island,
`PCLI` and similar country, `PPLX` neighbourhood, historical and abandoned codes historical.
Other populated places are city (100,000+), town (10,000+) or village. Everything else falls back
to its feature class: natural (H, T, U, V), area (L), facility (S), road (R).

## Performance

Measured on a 2-core Intel Xeon VM at 2.10 GHz with 7 GB RAM, Python 3.13, pandas 3.1.1,
pyarrow 26. Wall time and peak RSS come from [`scripts/measure.py`](scripts/measure.py)
(`getrusage` of the child process). Input is read straight from the zip, with IATA codes.

| input                                   | rows       | chunksize | wall   | peak RSS | Parquet |
|-----------------------------------------|-----------:|----------:|-------:|---------:|--------:|
| NG.zip                                  | 76,332     | 200,000   | 1.0 s  | 256 MB   | 3.5 MB  |
| DE.zip                                  | 222,330    | 200,000   | 2.7 s  | 366 MB   | 10 MB   |
| allCountries.zip (1.79 GB unzipped)     | 13,484,091 | 200,000   | 241 s  | 695 MB   | 588 MB  |
| allCountries.zip                        | 13,484,091 | 50,000    | 235 s  | 498 MB   | 617 MB  |

`top -n 10` on the world file: 3.4 s, 539 MB peak.

Once the input is bigger than one chunk, memory depends on the chunk size rather than the input
size; about 250 MB of the baseline is the Python, pandas and pyarrow imports. The file is read twice: once with five columns to find each country's
`PPLC`, then again to score. Smaller chunks mean smaller Parquet row groups, hence the slightly
bigger file at 50,000.

## Limitations

- The feature code dominates. GeoNames codes Lagos (population 15.4 million) as `PPLA2`, because
  the Lagos State capital is Ikeja, so Lagos scores 100 and ranks 26th in Nigeria, behind the
  country itself, Abuja and 23 state capitals. That is what the overrides file is for, but the rules will not notice it for you.
- Most small places have population 0 in GeoNames, so tens of thousands of villages tie at 15.
- GeoNames attaches IATA codes to cities as well as airports (`LOS` is on both Lagos and its
  airport), and some are metropolitan codes such as `LON`. Both get the bonus.
- A few countries have no `PPLC` row in GeoNames (for example AQ, EH, IL, PS), so
  `country_capital` is null for them. Where a country has more than one `PPLC`, the most populous
  is used.
- `edit` does not rewrite the Parquet file; the change lands on the next `score` run.
- Single process. Parsing the TSV is the bottleneck.

## Tests

```
pytest
ruff check
```

The fixture in `tests/data/` is 30 rows taken from the GeoNames NG, DE and NA files with the
`alternatenames` column emptied, plus a few IATA rows and one made-up historic code.

## License

MIT for the code. GeoNames data is [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/);
credit GeoNames if you publish anything built from it.
