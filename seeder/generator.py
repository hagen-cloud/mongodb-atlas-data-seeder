"""Document generation from a declarative JSON schema.

A schema is a mapping of ``field_name -> spec`` where ``spec`` has a ``type``
and type-specific options. Supported types: ``objectId``, ``int``, ``double``,
``bool``, ``enum``, ``string``, ``uuid``, ``date``, ``faker``, ``object`` and
``array``. ``faker`` delegates to any method of a seeded ``Faker`` instance.
"""

from __future__ import annotations

import datetime as dt
import random
import string
from typing import Any

from bson import ObjectId

_ALPHABET = string.ascii_letters + string.digits
_CHARSETS = {
    "alnum": _ALPHABET,
    "alpha": string.ascii_letters,
    "digits": string.digits,
    "hex": "0123456789abcdef",
    "lower": string.ascii_lowercase,
    "upper": string.ascii_uppercase,
}


def _rand_string(rng: random.Random, length: int, charset: str = "alnum") -> str:
    alphabet = _CHARSETS.get(charset, _ALPHABET)
    return "".join(rng.choice(alphabet) for _ in range(length))


def _parse_date(value: Any) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime(value.year, value.month, value.day, tzinfo=dt.UTC)
    return dt.datetime.fromisoformat(str(value))


def generate_value(spec: dict[str, Any], rng: random.Random, faker: Any) -> Any:  # pylint: disable=too-many-return-statements
    """Generate a single value from a field spec, using the seeded RNG/Faker."""
    field_type = spec.get("type")

    if field_type == "objectId":
        return ObjectId()
    if field_type == "int":
        return rng.randint(int(spec.get("min", 0)), int(spec.get("max", 1_000_000)))
    if field_type == "double":
        low = float(spec.get("min", 0.0))
        high = float(spec.get("max", 1.0))
        return round(rng.uniform(low, high), int(spec.get("decimals", 2)))
    if field_type == "bool":
        return rng.random() < float(spec.get("p_true", 0.5))
    if field_type == "enum":
        return rng.choice(spec["values"])
    if field_type == "string":
        if spec.get("values"):
            return rng.choice(spec["values"])
        return _rand_string(rng, int(spec.get("length", 16)), spec.get("charset", "alnum"))
    if field_type == "uuid":
        return faker.uuid4()
    if field_type == "date":
        start = _parse_date(spec.get("min", "2020-01-01"))
        end = _parse_date(spec.get("max", dt.datetime.now(tz=dt.UTC).isoformat()))
        span = (end - start).total_seconds()
        return start + dt.timedelta(seconds=rng.random() * span)
    if field_type == "faker":
        method = getattr(faker, spec["method"])
        return method(**spec.get("args", {}))
    if field_type == "object":
        return {key: generate_value(value, rng, faker) for key, value in spec.get("fields", {}).items()}
    if field_type == "array":
        count = rng.randint(int(spec.get("minItems", 0)), int(spec.get("maxItems", 5)))
        return [generate_value(spec["of"], rng, faker) for _ in range(count)]

    raise ValueError(f"Unknown field type: {field_type!r}")


def generate_document(schema: dict[str, Any], rng: random.Random, faker: Any) -> dict[str, Any]:
    """Generate one document by resolving every field in the schema."""
    return {name: generate_value(spec, rng, faker) for name, spec in schema.items()}
