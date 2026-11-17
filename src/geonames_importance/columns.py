import pyarrow as pa

# The 19 tab-separated columns of the GeoNames "geoname" table, in file order.
# See https://download.geonames.org/export/dump/readme.txt
GEONAME_COLUMNS = [
    "geonameid",
    "name",
    "asciiname",
    "alternatenames",
    "latitude",
    "longitude",
    "feature_class",
    "feature_code",
    "country_code",
    "cc2",
    "admin1_code",
    "admin2_code",
    "admin3_code",
    "admin4_code",
    "population",
    "elevation",
    "dem",
    "timezone",
    "modification_date",
]

# alternatenames is often the widest column in the file and nothing here uses it.
SOURCE_COLUMNS = [c for c in GEONAME_COLUMNS if c != "alternatenames"]

SOURCE_DTYPES = {
    "geonameid": "int64",
    "name": "str",
    "asciiname": "str",
    "latitude": "float64",
    "longitude": "float64",
    "feature_class": "str",
    "feature_code": "str",
    "country_code": "str",
    "cc2": "str",
    "admin1_code": "str",
    "admin2_code": "str",
    "admin3_code": "str",
    "admin4_code": "str",
    "population": "int64",
    "elevation": "Int32",
    "dem": "int32",
    "timezone": "str",
    "modification_date": "str",
}

ALTERNATE_NAME_COLUMNS = [
    "alternate_name_id",
    "geonameid",
    "isolanguage",
    "alternate_name",
    "is_preferred_name",
    "is_short_name",
    "is_colloquial",
    "is_historic",
    "from",
    "to",
]

DERIVED_COLUMNS = ["iata_code", "score", "importance", "admin_type", "country_capital"]

_ARROW_TYPES = {
    "int64": pa.int64(),
    "int32": pa.int32(),
    "Int32": pa.int32(),
    "float64": pa.float64(),
    "str": pa.string(),
}

OUTPUT_SCHEMA = pa.schema(
    [pa.field(c, _ARROW_TYPES[SOURCE_DTYPES[c]]) for c in SOURCE_COLUMNS]
    + [
        pa.field("iata_code", pa.string()),
        pa.field("score", pa.float64()),
        pa.field("importance", pa.int8()),
        pa.field("admin_type", pa.string()),
        pa.field("country_capital", pa.string()),
    ]
)
