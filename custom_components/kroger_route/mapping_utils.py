"""Helpers for editing ignore/typo/product mappings in the UI."""
from __future__ import annotations

from typing import Iterable


def lines_to_list(text: str | None) -> list[str]:
    """Parse one-item-per-line text into a cleaned, lowercased list."""
    if not text:
        return []
    items: list[str] = []
    for raw in str(text).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        items.append(line.lower())
    return items


def list_to_lines(items: Iterable[str] | None) -> str:
    """Serialize a list into one-item-per-line text."""
    if not items:
        return ""
    return "\n".join(str(i).strip() for i in items if str(i).strip())


def lines_to_mapping(text: str | None) -> dict[str, str]:
    """Parse key/value lines into a dict.

    Accepted separators per line: '=', ':', '=>'
    Examples:
      yogrt = yogurt
      oj = orange juice
      maple syrup => 0001111050000
    """
    if not text:
        return {}

    mapping: dict[str, str] = {}
    for raw in str(text).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        key = ""
        value = ""
        for sep in ("=>", "=", ":"):
            if sep in line:
                left, right = line.split(sep, 1)
                key = left.strip()
                value = right.strip()
                break
        if not key or not value:
            continue
        mapping[key.lower()] = value
    return mapping


def mapping_to_lines(mapping: dict[str, str] | None) -> str:
    """Serialize a mapping dict into editable lines."""
    if not mapping:
        return ""
    return "\n".join(f"{key} = {value}" for key, value in sorted(mapping.items()))
