"""Automated brand QA.

Replaces the manual "onboarding team eyeballs the build and sends it back" loop
with checks that run in seconds and explain exactly what to change.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Optional

from .color import contrast_ratio, darken_until
from .llm import LLMClient

AA_NORMAL = 4.5


@dataclass
class Check:
    id: str
    title: str
    status: str  # pass | fail | warn
    detail: str
    fix: Optional[dict] = None


def _contrast(check_id: str, title: str, fg_key: str, fg: str, bg: str, target: float = AA_NORMAL) -> Check:
    ratio = contrast_ratio(fg, bg)
    if ratio >= target:
        return Check(check_id, title, "pass", f"{fg} on {bg} = {ratio}:1 (needs {target})")
    suggested = darken_until(fg, bg, target)
    return Check(
        check_id, title, "fail",
        f"{fg} on {bg} = {ratio}:1, below WCAG AA {target}:1",
        fix={"path": fg_key, "from": fg, "to": suggested, "new_ratio": contrast_ratio(suggested, bg)},
    )


def run_checks(cfg: dict, tokens: dict, rendered: dict[str, str]) -> list[Check]:
    col = tokens["color"]
    checks = [
        _contrast("C1", "Body text on background", "colors.text", col["text"], col["background"]),
        _contrast("C2", "Muted text on background", "colors.muted_text", col["muted-text"], col["background"]),
        _contrast("C3", "Muted text on panels", "colors.muted_text", col["muted-text"], col["surface"]),
        _contrast("C4", "Button/header text on primary", "tokens.on-primary", col["on-primary"], col["primary"]),
        _contrast("C5", "Tag text on secondary", "tokens.on-secondary", col["on-secondary"], col["secondary"]),
        _contrast("C6", "Links on panels", "tokens.link", col["link"], col["surface"]),
    ]
    if col["link"] != col["primary"]:
        checks[-1].detail += f" (derived from primary {col['primary']}, which alone is {contrast_ratio(col['primary'], col['surface'])}:1)"

    # Components must only reference tokens, never literal colours.
    literal = {name: re.findall(r"#[0-9a-fA-F]{3,6}\b", html) for name, html in rendered.items()}
    offenders = {k: v for k, v in literal.items() if v}
    checks.append(Check("T1", "No hard-coded colours in components", "fail" if offenders else "pass",
                        f"found {offenders}" if offenders else "all colours come from tokens"))

    missing = [c for c in cfg["components"] if c not in rendered]
    checks.append(Check("T2", "All requested components rendered", "fail" if missing else "pass",
                        f"missing {missing}" if missing else f"{len(rendered)} components"))

    fonts_ok = all("," in tokens["font"][k] for k in ("heading", "body"))
    checks.append(Check("F1", "Font stacks include fallbacks", "pass" if fonts_ok else "fail",
                        f"heading: {tokens['font']['heading']}"))

    logo = cfg.get("logo_url", "")
    if not logo:
        checks.append(Check("L1", "Logo provided", "warn", "no logo_url; header falls back to text wordmark"))
    elif not logo.startswith("https://"):
        checks.append(Check("L1", "Logo served over https", "fail", f"{logo} will be blocked as mixed content",
                            fix={"path": "logo_url", "from": logo, "to": "https://" + logo.split("://", 1)[-1]}))
    else:
        checks.append(Check("L1", "Logo served over https", "pass", logo))

    alt_ok = all('alt=""' not in h for h in rendered.values())
    checks.append(Check("A1", "Images have alt text", "pass" if alt_ok else "fail", "checked rendered HTML"))
    return checks


REVIEW_SYSTEM = """You are a brand QA reviewer. Compare the brand guideline text with the
generated design tokens. List every mismatch as a bullet: what the guideline says,
what the tokens say. If there are none, reply exactly: No mismatches found."""


def llm_brand_review(client: LLMClient, guideline_text: Optional[str], cfg: dict) -> Optional[dict]:
    if not guideline_text:
        return None

    def mock() -> str:
        stated = {h.lower() for h in re.findall(r"#[0-9a-fA-F]{6}\b", guideline_text)}
        used = {v.lower() for v in cfg["colors"].values()}
        missing = sorted(stated - used)
        if not missing:
            return "No mismatches found."
        return "\n".join(f"- Guideline colour {m} is not used in the config" for m in missing)

    resp = client.chat("writer", REVIEW_SYSTEM, f"Guidelines:\n{guideline_text}\n\nConfig colours: {cfg['colors']}\nFonts: {cfg['typography']}", mock=mock)
    return {"model": resp.model, "latency_ms": resp.latency_ms, "review": resp.text}


def summarise(checks: list[Check]) -> dict:
    fails = [c for c in checks if c.status == "fail"]
    return {
        "status": "fail" if fails else "pass",
        "passed": sum(c.status == "pass" for c in checks),
        "failed": len(fails),
        "warnings": sum(c.status == "warn" for c in checks),
        "checks": [asdict(c) for c in checks],
    }
