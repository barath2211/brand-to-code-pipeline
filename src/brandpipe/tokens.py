"""Brand config -> design tokens (JSON + CSS custom properties)."""
from __future__ import annotations

from .color import best_text_on, darken_until, mix

GENERIC_FALLBACK = {
    "serif": "Georgia, 'Times New Roman', serif",
    "sans": "system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif",
    "mono": "ui-monospace, SFMono-Regular, Menlo, monospace",
}
SERIF_HINTS = ("serif", "garamond", "georgia", "times", "merriweather", "playfair", "lora")


def font_stack(name: str) -> str:
    lower = name.lower()
    if "," in name:
        return name  # already a stack
    kind = "serif" if any(h in lower for h in SERIF_HINTS) and "sans" not in lower else "sans"
    return f"'{name}', {GENERIC_FALLBACK[kind]}"


def build_tokens(cfg: dict) -> dict:
    c = cfg["colors"]
    t = cfg["typography"]
    base = t["base_size_px"]
    return {
        "color": {
            "primary": c["primary"],
            "primary-hover": mix(c["primary"], "#000000", 0.12),
            "on-primary": best_text_on(c["primary"]),
            # Brand primary is never altered; links get an accessible derived shade instead.
            "link": darken_until(c["primary"], c["surface"], 4.5),
            "secondary": c["secondary"],
            "on-secondary": best_text_on(c["secondary"]),
            "background": c["background"],
            "surface": c["surface"],
            "border": mix(c["surface"], c["text"], 0.15),
            "text": c["text"],
            "muted-text": c["muted_text"],
            "positive": c.get("positive", "#1a7f37"),
            "negative": c.get("negative", "#c62828"),
        },
        "font": {
            "heading": font_stack(t["heading_font"]),
            "body": font_stack(t["body_font"]),
            "size-base": f"{base}px",
            "size-sm": f"{round(base * 0.875)}px",
            "size-lg": f"{round(base * 1.25)}px",
            "size-xl": f"{round(base * 1.6)}px",
        },
        "space": {f"{i}": f"{cfg['spacing_unit_px'] * i}px" for i in (1, 2, 3, 4, 6)},
        "radius": {"base": f"{cfg['radius_px']}px"},
    }


def tokens_to_css(tokens: dict, scope: str) -> str:
    lines = [f"/* Generated from brand config. Do not edit by hand. */", f".{scope} {{"]
    for group, values in tokens.items():
        for key, val in values.items():
            lines.append(f"  --{group}-{key}: {val};")
    lines.append("}")
    return "\n".join(lines) + "\n"
