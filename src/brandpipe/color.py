"""Colour maths: WCAG contrast, shade derivation, accessible text colour picking."""
from __future__ import annotations


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def relative_luminance(h: str) -> float:
    def channel(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = hex_to_rgb(h)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return round((hi + 0.05) / (lo + 0.05), 2)


def mix(a: str, b: str, weight: float) -> str:
    """Blend colour a toward b by weight (0..1)."""
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    return rgb_to_hex(tuple(x + (y - x) * weight for x, y in zip(ra, rb)))


def best_text_on(bg: str, light: str = "#ffffff", dark: str = "#111111") -> str:
    return light if contrast_ratio(bg, light) >= contrast_ratio(bg, dark) else dark


def darken_until(fg: str, bg: str, target: float = 4.5, step: float = 0.05) -> str:
    """Nudge fg toward black (or white on dark bgs) until it meets the target ratio."""
    toward = "#000000" if relative_luminance(bg) > 0.5 else "#ffffff"
    candidate, w = fg, 0.0
    while contrast_ratio(candidate, bg) < target and w < 1:
        w += step
        candidate = mix(fg, toward, w)
    return candidate
