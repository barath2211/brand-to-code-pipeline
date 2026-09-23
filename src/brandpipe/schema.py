"""Brand config schema and validation.

A brand config is the single source of truth for a client's look. Everything
downstream (tokens, components, QA) is generated from it, so validation here is
where most manual-rework loops get killed.
"""
from __future__ import annotations

import re

HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")

REQUIRED = {
    "client_id": str,
    "display_name": str,
    "colors": dict,
    "typography": dict,
}
REQUIRED_COLORS = ["primary", "secondary", "background", "surface", "text", "muted_text"]
REQUIRED_TYPO = ["heading_font", "body_font", "base_size_px"]
ALLOWED_COMPONENTS = ["header", "share_price_ticker", "news_list", "events_calendar", "contact_card"]

DEFAULTS = {
    "radius_px": 6,
    "spacing_unit_px": 8,
    "logo_url": "",
    "locale": "en-GB",
    "components": ALLOWED_COMPONENTS,
    "button_style": "filled",
}


def normalise_hex(value: str) -> str:
    value = value.strip()
    if len(value) == 4:  # #abc -> #aabbcc
        value = "#" + "".join(c * 2 for c in value[1:])
    return value.lower()


def validate(config: dict) -> tuple[dict, list[str]]:
    """Return (config with defaults, list of blocking errors)."""
    errors: list[str] = []
    for key, typ in REQUIRED.items():
        if key not in config:
            errors.append(f"missing required field '{key}'")
        elif not isinstance(config[key], typ):
            errors.append(f"'{key}' must be {typ.__name__}")
    if errors:
        return config, errors

    if not re.fullmatch(r"[a-z0-9-]{2,40}", config["client_id"]):
        errors.append("client_id must be lowercase letters, digits or dashes")

    colors = config["colors"]
    for name in REQUIRED_COLORS:
        val = colors.get(name)
        if val is None:
            errors.append(f"colors.{name} is required")
        elif not isinstance(val, str) or not HEX.match(val):
            errors.append(f"colors.{name} '{val}' is not a hex colour")
        else:
            colors[name] = normalise_hex(val)

    typo = config["typography"]
    for name in REQUIRED_TYPO:
        if name not in typo:
            errors.append(f"typography.{name} is required")
    if isinstance(typo.get("base_size_px"), (int, float)) and not 12 <= typo["base_size_px"] <= 22:
        errors.append("typography.base_size_px should be between 12 and 22")

    merged = {**DEFAULTS, **config}
    unknown = [c for c in merged["components"] if c not in ALLOWED_COMPONENTS]
    if unknown:
        errors.append(f"unknown components: {unknown}")
    return merged, errors
