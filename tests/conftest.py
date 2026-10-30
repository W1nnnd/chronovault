import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

AS_OF = dt.date(2026, 10, 30)


@pytest.fixture(scope="session")
def sample_nas(tmp_path_factory):
    from samples.generate_samples import generate

    return generate(tmp_path_factory.mktemp("nas") / "nas")


@pytest.fixture()
def sources(sample_nas):
    return [sample_nas / "Documents", sample_nas / "Photos"]
