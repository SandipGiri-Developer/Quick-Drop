from pathlib import Path

import pytest

from app.data.loader import load_dataset
from app.domain.errors import DataIntegrityError


def test_loader_real_data() -> None:
    d = load_dataset(Path("data"))
    assert len(d.riders) > 0
    assert len(d.trips) > 0
    assert len(d.payouts) > 0


def test_loader_bad_data(tmp_path: Path) -> None:
    # missing column in riders
    (tmp_path / "riders.csv").write_text("rider_id,name\nR001,John\n", encoding="utf-8")
    with pytest.raises(DataIntegrityError):
        load_dataset(tmp_path)
