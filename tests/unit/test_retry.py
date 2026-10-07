from typing import Any

import pytest

from app.infrastructure.payswift.retry import with_retry


def test_retry_success() -> None:
    count = 0

    def action() -> Any:
        nonlocal count
        count += 1
        if count < 3:
            raise ValueError("fail")
        return "success"

    def is_retryable(e: Exception) -> bool:
        return isinstance(e, ValueError)

    res = with_retry(
        max_attempts=3,
        base_delay=0.01,
        action=action,
        is_retryable=is_retryable,
        sleep_func=lambda x: None,
    )
    assert res == "success"
    assert count == 3


def test_retry_max_attempts() -> None:
    count = 0

    def action() -> Any:
        nonlocal count
        count += 1
        raise ValueError("fail")

    def is_retryable(e: Exception) -> bool:
        return isinstance(e, ValueError)

    with pytest.raises(ValueError):
        with_retry(
            max_attempts=2,
            base_delay=0.01,
            action=action,
            is_retryable=is_retryable,
            sleep_func=lambda x: None,
        )
    assert count == 2


def test_retry_not_retryable() -> None:
    def action() -> Any:
        raise TypeError("stop")

    def is_retryable(e: Exception) -> bool:
        return isinstance(e, ValueError)

    with pytest.raises(TypeError):
        with_retry(
            max_attempts=3,
            base_delay=0.01,
            action=action,
            is_retryable=is_retryable,
            sleep_func=lambda x: None,
        )


def test_retry_after_property() -> None:
    class CustomError(Exception):
        retry_after = 0.5

    count = 0

    def action() -> Any:
        nonlocal count
        count += 1
        if count < 2:
            raise CustomError("wait")
        return "done"

    def is_retryable(e: Exception) -> bool:
        return True

    slept: float = 0.0

    def sleep_func(x: float) -> None:
        nonlocal slept
        slept = x

    res = with_retry(
        max_attempts=2,
        base_delay=0.01,
        action=action,
        is_retryable=is_retryable,
        sleep_func=sleep_func,
    )
    assert res == "done"
    assert slept == 0.5
