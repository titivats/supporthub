from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict


def to_iso(ts: datetime | None) -> str | None:
    return ts.isoformat() if ts else None


def safe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except Exception:
            return None
    return None


def extract_numeric(obj: Any, prefix: str = "", out: Dict[str, float] | None = None) -> Dict[str, float]:
    if out is None:
        out = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            child_key = f"{prefix}.{key}" if prefix else str(key)
            extract_numeric(value, child_key, out)
        return out
    if isinstance(obj, list):
        for index, value in enumerate(obj):
            child_key = f"{prefix}[{index}]" if prefix else f"[{index}]"
            extract_numeric(value, child_key, out)
        return out
    numeric = safe_float(obj)
    if numeric is not None:
        out[prefix or "value"] = numeric
    return out


def normalize_metric_key(value: str) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


_METRIC_ALIASES = {
    "voltage": ("voltage", "volt", "volts", "v"),
    "current": ("current", "ampere", "amperes", "amps", "amp", "a"),
    "power": ("power", "watt", "watts", "w"),
    "power_factor": ("powerfactor", "power_factor", "pf"),
    "energy": ("energy", "kwh", "wh"),
    "frequency": ("frequency", "freq", "hz", "f"),
}


def canonical_metric_name(value: str) -> str | None:
    normalized = normalize_metric_key(value)
    if not normalized:
        return None

    exact_alias_map = {}
    for canonical, aliases in _METRIC_ALIASES.items():
        normalized_aliases = {normalize_metric_key(alias) for alias in aliases if alias}
        for alias in normalized_aliases:
            exact_alias_map[alias] = canonical

    exact_match = exact_alias_map.get(normalized)
    if exact_match:
        return exact_match

    for canonical, aliases in _METRIC_ALIASES.items():
        normalized_aliases = {normalize_metric_key(alias) for alias in aliases if alias}
        for alias in sorted(normalized_aliases, key=len, reverse=True):
            if normalized.endswith(alias) or normalized.startswith(alias):
                return canonical
    return None


def canonicalize_numeric_key(raw_key: str) -> str:
    key = (raw_key or "").strip()
    if not key:
        return key

    if "." in key:
        prefix, suffix = key.rsplit(".", 1)
    else:
        prefix, suffix = "", key

    canonical_suffix = canonical_metric_name(suffix) or canonical_metric_name(key)
    if not canonical_suffix:
        return key
    return f"{prefix}.{canonical_suffix}" if prefix else canonical_suffix


def canonicalize_numeric_map(numeric_map: Dict[str, float]) -> Dict[str, float]:
    if not numeric_map:
        return {}

    out: Dict[str, float] = {}
    for key, value in numeric_map.items():
        canonical_key = canonicalize_numeric_key(key)
        current_value = out.get(canonical_key)
        numeric_value = float(value)

        if current_value is None:
            out[canonical_key] = numeric_value
            continue

        if float(current_value) == 0.0 and numeric_value != 0.0:
            out[canonical_key] = numeric_value
    return out


def pick_metric_value(numeric_map: Dict[str, float], aliases: tuple[str, ...]) -> float | None:
    if not numeric_map:
        return None

    alias_keys = {normalize_metric_key(alias) for alias in aliases if alias}
    if not alias_keys:
        return None

    for key, value in numeric_map.items():
        if normalize_metric_key(key) in alias_keys:
            return float(value)

    for key, value in numeric_map.items():
        normalized_key = normalize_metric_key(key)
        for alias in alias_keys:
            if normalized_key.endswith(alias):
                return float(value)
    return None


def parse_payload_numeric_map(payload: str) -> Dict[str, float]:
    numeric_map: Dict[str, float] = {}
    if not payload:
        return numeric_map

    try:
        if payload.startswith("{") or payload.startswith("["):
            numeric_map = extract_numeric(json.loads(payload))
        else:
            numeric = safe_float(payload)
            if numeric is not None:
                numeric_map = {"value": numeric}
    except Exception:
        numeric_map = {}

    return canonicalize_numeric_map(numeric_map)
