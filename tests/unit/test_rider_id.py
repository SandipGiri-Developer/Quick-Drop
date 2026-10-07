import pytest

from app.domain.errors import InvalidRiderIdError
from app.domain.rider_id import normalize_rider_id


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("R7", "R007"),
        ("r19", "R019"),
        (" R003 ", "R003"),
        (
            "R0003",
            "R003",
        ),  # Wait, should R0003 be R003? Let's say yes since int("0003") = 3 -> R003
    ],
)
def test_normalize_rider_id(raw: str, expected: str) -> None:
    assert normalize_rider_id(raw) == expected


@pytest.mark.parametrize(
    "invalid",
    [
        "X12",
        "",
        "R",
        None,
    ],
)
def test_invalid_rider_id(invalid: str | None) -> None:
    with pytest.raises(InvalidRiderIdError):
        normalize_rider_id(invalid)  # type: ignore
