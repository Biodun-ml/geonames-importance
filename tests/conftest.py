from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"


@pytest.fixture
def geonames_path() -> Path:
    return DATA / "geonames.tsv"


@pytest.fixture
def alternate_names_path() -> Path:
    return DATA / "alternate_names.tsv"
