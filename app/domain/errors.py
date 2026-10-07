class DomainError(Exception):
    pass


class DataIntegrityError(DomainError):
    pass


class UnknownRiderError(DomainError):
    pass


class InvalidRiderIdError(DomainError):
    pass


class TripNotFoundError(DomainError):
    pass
