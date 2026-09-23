"""Free-text brand guidelines -> structured brand config (LLM step).

This is the step that used to be a person reading a PDF and typing hex codes
into a form. The model does the reading; the schema validator decides whether
the result is usable.
"""
from __future__ import annotations

import json
import re

from .llm import LLMClient, parse_json_loose

SYSTEM = """You convert brand guideline text into a JSON brand config.
Return ONLY JSON with this shape:
{"display_name": str,
 "colors": {"primary","secondary","background","surface","text","muted_text"} as hex strings,
 "typography": {"heading_font": str, "body_font": str, "base_size_px": int},
 "radius_px": int}
Only use values stated in the text. If a value is not stated, omit it. Never invent colours."""

ROLE_HINTS = {
    "primary": ["primary"],
    "secondary": ["secondary", "accent"],
    "background": ["background"],
    "surface": ["panel", "surface", "card"],
    "text": ["body text", "text is"],
    "muted_text": ["supporting text", "muted", "secondary text", "caption"],
}


def _mock_extract(text: str) -> dict:
    colors: dict[str, str] = {}
    for line in text.splitlines():
        hexes = re.findall(r"#[0-9a-fA-F]{6}\b", line)
        low = line.lower()
        if not hexes:
            continue
        # A line can hold two roles, e.g. "background is #fff with panels in #f4f6f8"
        roles = [r for r, hints in ROLE_HINTS.items() if any(h in low for h in hints)]
        if "text" in roles and "muted_text" in roles and len(hexes) >= 2:
            colors.setdefault("text", hexes[0]); colors.setdefault("muted_text", hexes[1]); continue
        if "background" in roles and "surface" in roles and len(hexes) >= 2:
            colors.setdefault("background", hexes[0]); colors.setdefault("surface", hexes[1]); continue
        for role, hx in zip(roles, hexes):
            colors.setdefault(role, hx)
    fonts = re.findall(r'"([^"]+)"', text)
    size = re.search(r"(\d{2})px", text)
    radius = re.search(r"rounded[^\d]*(\d+)px", text.lower())
    title = re.search(r"^#\s*(.+?) brand", text, flags=re.MULTILINE)
    cfg = {
        "display_name": title.group(1).strip() if title else "Unnamed brand",
        "colors": {k: v.lower() for k, v in colors.items()},
        "typography": {},
    }
    if fonts:
        cfg["typography"]["heading_font"] = fonts[0]
        cfg["typography"]["body_font"] = fonts[1] if len(fonts) > 1 else fonts[0]
    if size:
        cfg["typography"]["base_size_px"] = int(size.group(1))
    if radius:
        cfg["radius_px"] = int(radius.group(1))
    return cfg


def extract_config(client: LLMClient, guideline_text: str, client_id: str) -> dict:
    resp = client.chat(
        role="writer",
        system=SYSTEM,
        user=f"<guidelines>\n{guideline_text}\n</guidelines>",
        json_mode=True,
        mock=lambda: json.dumps(_mock_extract(guideline_text)),
    )
    cfg = parse_json_loose(resp.text)
    cfg["client_id"] = client_id
    cfg.setdefault("colors", {})
    cfg.setdefault("typography", {})
    cfg["_extraction"] = {"model": resp.model, "provider": resp.provider, "latency_ms": resp.latency_ms}
    return cfg
