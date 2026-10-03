"""Small shared validators; no silent numeric coercion at service boundaries."""
from __future__ import annotations
import math
from datetime import datetime

MAX_INTEGER = 2**53 - 1

def integer(value, label: str, minimum: int = 0, maximum: int = MAX_INTEGER) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer between {minimum} and {maximum}")
    return value

def text(value, label: str, maximum: int = 512, empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise ValueError(f"{label} must be {'a' if empty else 'a nonempty'} string of at most {maximum} characters")
    return value

def rate(value, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{label} must be a finite number between 0 and 1")
    return value

def timestamp(value: str) -> str:
    text(value, 'timestamp', 64)
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamp must include time and timezone, e.g. 2026-09-28T00:00:00Z; a date alone is insufficient')
    from datetime import timezone
    return parsed.astimezone(timezone.utc).isoformat()

def schema(value, spec, label='arguments'):
    """Validate the intentionally small JSON Schema subset used by our tools."""
    kind = spec.get('type')
    if kind == 'object':
        if not isinstance(value, dict):
            raise ValueError(f'{label} must be an object')
        properties = spec.get('properties', {})
        missing = set(spec.get('required', [])) - value.keys()
        unknown = value.keys() - properties.keys()
        if missing or (unknown and spec.get('additionalProperties') is False):
            raise ValueError(f'{label}: missing {sorted(missing)}, unknown {sorted(unknown)}')
        for key, child in value.items():
            if key in properties:
                schema(child, properties[key], key)
    elif kind == 'integer':
        integer(value, label, spec.get('minimum', 0), spec.get('maximum', MAX_INTEGER))
    elif kind == 'number':
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f'{label} must be finite')
        if value < spec.get('minimum', -math.inf) or value > spec.get('maximum', math.inf):
            raise ValueError(f'{label} is outside the allowed range')
    elif kind == 'string':
        text(value, label, spec.get('maxLength', 512), empty=True)
        if spec.get('format') == 'date-time': timestamp(value)
    if 'enum' in spec and value not in spec['enum']:
        raise ValueError(f'{label} must be one of {spec["enum"]}')
