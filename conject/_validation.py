from typing import Any, Type

import pydantic


class ValidationError(Exception):
    def __init__(self, value: Any, expected_type: Type):
        self.value = value
        self.expected_type = expected_type


def make_validator(val_type: Any, debug_name: str) -> Any:
    if val_type is Any:
        return _empty_validator

    class Config(pydantic.BaseConfig):
        arbitrary_types_allowed = True

    model = pydantic.create_model(
        debug_name,
        __config__=Config,
        value=(val_type, ...),
    )

    def validate(value: Any) -> Any:
        try:
            result = model(value=value)
        except pydantic.ValidationError as e:
            raise ValidationError(value, val_type) from e

        # noinspection PyUnresolvedReferences
        return result.value  # type: ignore

    return validate


def _empty_validator(value: Any) -> Any:
    return value
