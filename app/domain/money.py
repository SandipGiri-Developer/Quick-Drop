from decimal import ROUND_HALF_UP, Decimal

Rupees = int


def round_half_up(value: Decimal) -> Rupees:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))
