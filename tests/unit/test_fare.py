from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.fare import compute_trip_fare
from app.domain.money import round_half_up


@pytest.mark.parametrize(
    "dist_km, surge, expected",
    [
        ("0.8", "1.0", 25),  # <= 2km
        ("2.0", "1.0", 25),  # exactly 2km
        ("3.0", "1.0", 31),  # 25 + 6 = 31
        ("7.4", "1.0", 57),  # 25 + 5.4*6 = 25 + 32.4 = 57.4 -> 57
        ("7.5", "1.0", 58),  # 25 + 5.5*6 = 25 + 33 = 58
        ("6.0", "1.5", 74),  # (25 + 4*6) * 1.5 = 49 * 1.5 = 73.5 -> 74 (round up)
        ("9.0", "1.5", 101),  # (25 + 7*6) * 1.5 = 67 * 1.5 = 100.5 -> 101
        ("10.0", "1.2", 88),  # (25 + 8*6) * 1.2 = 73 * 1.2 = 87.6 -> 88
        ("13.0", "1.5", 137),  # (25 + 11*6) * 1.5 = 91 * 1.5 = 136.5 -> 137
    ],
)
def test_compute_trip_fare_cases(dist_km: str, surge: str, expected: int) -> None:
    assert compute_trip_fare(Decimal(dist_km), Decimal(surge)) == expected


def test_bankers_rounding_difference() -> None:
    # 2.5 banker rounds to 2, round_half_up rounds to 3.
    # We want round_half_up.
    val = Decimal("2.5")
    assert round_half_up(val) == 3


@given(
    st.decimals(min_value=0, max_value=20, places=1),
    st.decimals(min_value=1.0, max_value=2.0, places=1),
)
def test_fare_properties(dist: Decimal, surge: Decimal) -> None:
    fare = compute_trip_fare(dist, surge)
    assert isinstance(fare, int)
    if dist > 0:
        assert fare >= 25


@given(st.decimals(min_value=0, max_value=10000, places=2))
def test_round_half_up_matches_floor_plus_half(val: Decimal) -> None:
    import math

    assert round_half_up(val) == math.floor(float(val) + 0.5)
