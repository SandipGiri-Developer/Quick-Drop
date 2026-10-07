from decimal import Decimal

from .money import Rupees, round_half_up

BASE_FARE = Decimal(25)
PER_KM_RATE = Decimal(6)
FREE_KM = Decimal(2)
INCENTIVE_AMOUNT = Rupees(150)
INCENTIVE_MIN_TRIPS = 12
CANCEL_PENALTY = Rupees(10)
DISPUTE_WINDOW_DAYS = 7
METRES_THRESHOLD = Decimal(100)


def compute_trip_fare(distance_km: Decimal, surge: Decimal) -> Rupees:
    if distance_km <= FREE_KM:
        fare = BASE_FARE
    else:
        fare = BASE_FARE + (distance_km - FREE_KM) * PER_KM_RATE

    total = fare * surge
    return round_half_up(total)
