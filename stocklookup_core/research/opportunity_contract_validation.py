"""Structural-only guard for prohibited opportunity/scenario capabilities."""
from __future__ import annotations
from typing import Any, Mapping

_FORBIDDEN = ("recommendation", "targetprice", "probability", "portfoliopositionsize", "positionsize", "portfoliosize")


def _normalized_key(value: Any) -> str:
    return "".join(character.lower() for character in str(value) if character.isalnum())


def find_prohibited_fields(value: Any, path: str = "$") -> list[str]:
    """Return key paths only; never inspect limitation/warning text values."""
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = _normalized_key(key)
            child_path = f"{path}.{key}"
            if any(token in normalized for token in _FORBIDDEN):
                found.append(child_path)
            found.extend(find_prohibited_fields(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_prohibited_fields(child, f"{path}[{index}]"))
    return found


def validate_no_prohibited_capabilities(value: Any) -> None:
    forbidden = find_prohibited_fields(value)
    if forbidden:
        raise ValueError("prohibited_opportunity_capability_fields:" + ",".join(forbidden))
