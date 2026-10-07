from .errors import InvalidRiderIdError


def normalize_rider_id(raw: str) -> str:
    if not raw:
        raise InvalidRiderIdError("Rider ID cannot be empty")

    cleaned = raw.strip()
    if not cleaned:
        raise InvalidRiderIdError("Rider ID cannot be empty")

    if cleaned.upper().startswith("R"):
        num_part = cleaned[1:]
        if num_part.isdigit():
            return f"R{int(num_part):03d}"

    raise InvalidRiderIdError(f"Invalid rider ID format: {raw}")
