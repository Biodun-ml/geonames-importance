import numpy as np
import pandas as pd

# Points for the place type. Codes not listed here fall back to CLASS_POINTS.
# Feature codes: https://www.geonames.org/export/codes.html
FEATURE_POINTS = {
    # countries and territories
    "PCLI": 70, "PCLD": 60, "PCLS": 60, "PCLF": 55, "PCLIX": 50, "TERR": 50,
    # populated places
    "PPLC": 70, "PPLG": 60, "PPLA": 55, "PPLA2": 40, "PPLA3": 30, "PPLA4": 22, "PPLA5": 18,
    "PPL": 15, "PPLS": 12, "PPLX": 8, "PPLF": 8, "PPLL": 6, "PPLR": 6,
    "PPLCH": 10, "PPLH": 2, "PPLQ": 0, "PPLW": 0,
    # administrative divisions, current and historical
    "ADM1": 45, "ADM2": 30, "ADM3": 20, "ADM4": 12, "ADM5": 8, "ADMD": 8,
    "PCLH": 2, "ADM1H": 2, "ADM2H": 2, "ADM3H": 2, "ADM4H": 2, "ADMDH": 2,
    # transport
    "AIRP": 40, "AIRF": 12, "PRT": 20, "RSTN": 10,
    # islands, parks, landmarks
    "ISL": 20, "ISLS": 18, "ATOL": 15, "PRK": 15, "RESN": 12, "VLC": 12,
    "LK": 10, "BCH": 10, "MT": 8, "MUS": 8, "CSTL": 8,
}  # fmt: skip

CLASS_POINTS = {"P": 15, "A": 10, "S": 3, "T": 3, "H": 3, "L": 3, "V": 1, "R": 1, "U": 0}

MAX_FEATURE_POINTS = 70
MAX_POPULATION_POINTS = 50
IATA_POINTS = 10
MAX_SCORE = MAX_FEATURE_POINTS + MAX_POPULATION_POINTS + IATA_POINTS

# A population of 10 million earns the full 50 points: 50 * log10(1 + pop) / 7.
POPULATION_FOR_MAX_POINTS_LOG10 = 7

# (minimum score, level), checked from the top.
IMPORTANCE_THRESHOLDS = [(100, 5), (75, 4), (50, 3), (25, 2)]

COUNTRY_CODES = {"PCLI", "PCLD", "PCLS", "PCLF", "PCLIX", "TERR"}
HISTORICAL_CODES = {
    "PPLH", "PPLQ", "PPLW", "PPLCH", "PCLH", "ADM1H", "ADM2H", "ADM3H", "ADM4H", "ADMDH",
}  # fmt: skip

FEATURE_ADMIN_TYPES = {
    "PPLC": "country_capital",
    "PPLG": "government_seat",
    "PPLA": "state_capital",
    "PPLX": "neighbourhood",
    "ADM1": "region",
    "ADM2": "district",
    "ADM3": "district",
    "ADM4": "district",
    "ADM5": "district",
    "ADMD": "district",
    "AIRP": "airport",
    "AIRF": "airport",
    "ISL": "island",
    "ISLS": "island",
    "ATOL": "island",
    **{code: "country" for code in COUNTRY_CODES},
    **{code: "historical" for code in HISTORICAL_CODES},
}

CLASS_ADMIN_TYPES = {
    "H": "natural",
    "T": "natural",
    "U": "natural",
    "V": "natural",
    "L": "area",
    "S": "facility",
    "R": "road",
}

CITY_MIN_POPULATION = 100_000
TOWN_MIN_POPULATION = 10_000


def feature_points(feature_class: pd.Series, feature_code: pd.Series) -> pd.Series:
    by_code = feature_code.map(FEATURE_POINTS)
    by_class = feature_class.map(CLASS_POINTS)
    return by_code.fillna(by_class).fillna(0).astype("float64")


def population_points(population: pd.Series) -> pd.Series:
    pop = population.clip(lower=0).astype("float64")
    points = MAX_POPULATION_POINTS * np.log10(1 + pop) / POPULATION_FOR_MAX_POINTS_LOG10
    return points.clip(upper=MAX_POPULATION_POINTS)


def score(df: pd.DataFrame) -> pd.Series:
    has_iata = df["iata_code"].fillna("").ne("").to_numpy(dtype=bool)
    total = (
        feature_points(df["feature_class"], df["feature_code"])
        + population_points(df["population"])
        + np.where(has_iata, IATA_POINTS, 0)
    )
    return total.round(2)


def importance_level(scores: pd.Series) -> pd.Series:
    level = pd.Series(1, index=scores.index, dtype="int8")
    # Assign from the lowest threshold up so higher levels overwrite lower ones.
    for minimum, value in reversed(IMPORTANCE_THRESHOLDS):
        level[scores >= minimum] = value
    return level


def admin_type(df: pd.DataFrame) -> pd.Series:
    by_code = df["feature_code"].map(FEATURE_ADMIN_TYPES)

    pop = df["population"]
    by_size = pd.Series(
        np.select(
            [pop >= CITY_MIN_POPULATION, pop >= TOWN_MIN_POPULATION],
            ["city", "town"],
            default="village",
        ),
        index=df.index,
    )
    is_place = df["feature_class"].eq("P")
    by_class = by_size.where(is_place, df["feature_class"].map(CLASS_ADMIN_TYPES))

    return by_code.fillna(by_class).fillna("other").astype("str")


def add_scores(df: pd.DataFrame, capitals: dict[str, str]) -> pd.DataFrame:
    df = df.copy()
    df["score"] = score(df)
    df["importance"] = importance_level(df["score"])
    df["admin_type"] = admin_type(df)
    df["country_capital"] = df["country_code"].map(capitals)
    return df
