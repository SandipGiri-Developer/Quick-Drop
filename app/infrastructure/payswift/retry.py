import time
from collections.abc import Callable


def with_retry[T](
    max_attempts: int,
    base_delay: float,
    action: Callable[[], T],
    is_retryable: Callable[[Exception], bool],
    sleep_func: Callable[[float], None] = time.sleep,
) -> T:
    """
    Executes an action with exponential backoff.
    """
    attempts = 0
    while True:
        attempts += 1
        try:
            return action()
        except Exception as e:
            if attempts >= max_attempts or not is_retryable(e):
                raise

            # Wait, if we can read Retry-After from the exception, we should use it.
            # We'll handle Retry-After inside the exception itself by adding a property `retry_after`.
            delay = getattr(e, "retry_after", None)
            if delay is None:
                delay = base_delay * (2 ** (attempts - 1))

            sleep_func(delay)
