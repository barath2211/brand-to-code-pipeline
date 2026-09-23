"""Orchestration: (guidelines ->) config -> validate -> tokens -> components -> QA -> (auto-fix) -> dist."""
from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from . import qa
from .extract import extract_config
from .llm import LLMClient
from .schema import validate
from .tokens import build_tokens, tokens_to_css

PKG = Path(__file__).resolve().parent
ROOT = PKG.parents[1]
TEMPLATES = PKG / "templates"
SAMPLE_CONTENT = ROOT / "data" / "sample_content.json"


# Brand identity colours are flagged, never auto-fixed.
PROTECTED = {"colors.primary", "colors.secondary"}


class BuildError(Exception):
    pass


def _apply_fixes(cfg: dict, checks: list[dict]) -> list[str]:
    applied: dict[str, str] = {}
    for c in checks:
        fix = c.get("fix")
        if c["status"] != "fail" or not fix:
            continue
        path = fix["path"]
        if path in PROTECTED:
            continue  # core brand identity: needs a human decision, never auto-changed
        if path.startswith("colors."):
            cfg["colors"][path.split(".", 1)[1]] = fix["to"]
        elif path == "logo_url":
            cfg["logo_url"] = fix["to"]
        else:
            continue  # token-level fixes are derived; nothing to change in config
        applied[path] = f"{path}: {fix['from']} -> {fix['to']}"  # later, stricter fix wins
    return list(applied.values())


class BrandPipeline:
    def __init__(self, provider: Optional[str] = None, out_dir: Path = ROOT / "dist"):
        self.client = LLMClient(provider)
        self.out_dir = out_dir
        self.env = Environment(loader=FileSystemLoader(TEMPLATES), undefined=StrictUndefined, autoescape=True)
        self.content = json.loads(SAMPLE_CONTENT.read_text(encoding="utf-8"))

    def load(self, source: Path) -> tuple[dict, Optional[str], dict]:
        timings = {}
        if source.suffix == ".md":
            t = time.perf_counter()
            text = source.read_text(encoding="utf-8")
            client_id = source.stem.replace("_guidelines", "")
            cfg = extract_config(self.client, text, client_id)
            timings["extract_ms"] = round((time.perf_counter() - t) * 1000, 1)
            return cfg, text, timings
        return json.loads(source.read_text(encoding="utf-8")), None, timings

    def render(self, cfg: dict) -> tuple[dict, dict[str, str]]:
        tokens = build_tokens(cfg)
        rendered = {}
        for name in cfg["components"]:
            tpl = self.env.get_template(f"{name}.html.j2")
            rendered[name] = tpl.render(brand=cfg, content=self.content)
        return tokens, rendered

    def build(self, source: Path, auto_fix: bool = False) -> dict:
        t0 = time.perf_counter()
        raw, guideline_text, timings = self.load(source)
        cfg, errors = validate(copy.deepcopy(raw))
        if errors:
            raise BuildError("Config failed validation:\n  - " + "\n  - ".join(errors))

        history = []
        for attempt in range(1, 4):
            t = time.perf_counter()
            tokens, rendered = self.render(cfg)
            report = qa.summarise(qa.run_checks(cfg, tokens, rendered))
            timings[f"render_and_qa_attempt_{attempt}_ms"] = round((time.perf_counter() - t) * 1000, 1)
            history.append({"attempt": attempt, "status": report["status"], "failed": report["failed"]})
            if report["status"] == "pass" or not auto_fix:
                break
            applied = _apply_fixes(cfg, report["checks"])
            history[-1]["fixes_applied"] = applied
            if not applied:
                break

        review = qa.llm_brand_review(self.client, guideline_text, cfg)
        out = self._write(cfg, tokens, rendered, report, review, history)
        timings["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        log = {"client_id": cfg["client_id"], "provider": self.client.provider, "timings": timings,
               "qa_status": report["status"], "attempts": history, "output_dir": str(out)}
        (out / "build_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
        return {"log": log, "report": report, "review": review, "config": cfg}

    def _write(self, cfg, tokens, rendered, report, review, history) -> Path:
        out = self.out_dir / cfg["client_id"]
        (out / "components").mkdir(parents=True, exist_ok=True)
        scope = f"brand-{cfg['client_id']}"
        (out / "tokens.json").write_text(json.dumps(tokens, indent=2), encoding="utf-8")
        (out / "tokens.css").write_text(tokens_to_css(tokens, scope), encoding="utf-8")
        (out / "components.css").write_text((TEMPLATES / "base.css").read_text(encoding="utf-8"), encoding="utf-8")
        for name, html in rendered.items():
            (out / "components" / f"{name}.html").write_text(html, encoding="utf-8")
        preview = self.env.get_template("preview.html.j2").render(brand=cfg, components=[_Markup(h) for h in rendered.values()])
        (out / "index.html").write_text(preview, encoding="utf-8")
        clean_cfg = {k: v for k, v in cfg.items() if not k.startswith("_")}
        (out / "brand.resolved.json").write_text(json.dumps(clean_cfg, indent=2), encoding="utf-8")
        (out / "qa_report.json").write_text(json.dumps({"report": report, "llm_review": review, "attempts": history}, indent=2), encoding="utf-8")
        (out / "qa_report.md").write_text(report_markdown(cfg, report, review, history), encoding="utf-8")
        return out


def _Markup(s: str):
    from markupsafe import Markup
    return Markup(s)


def report_markdown(cfg: dict, report: dict, review: Optional[dict], history: list) -> str:
    icon = {"pass": "PASS", "fail": "FAIL", "warn": "WARN"}
    lines = [f"# QA report: {cfg['display_name']}", "", f"**Overall:** {report['status'].upper()}  "
             f"({report['passed']} passed, {report['failed']} failed, {report['warnings']} warnings)", ""]
    if len(history) > 1:
        lines += ["**Auto-fix attempts:**", ""] + [f"- Attempt {h['attempt']}: {h['status']}" + (f", applied {h['fixes_applied']}" if h.get("fixes_applied") else "") for h in history] + [""]
    lines += ["| Check | Result | Detail | Suggested fix |", "|---|---|---|---|"]
    for c in report["checks"]:
        fix = f"`{c['fix']['path']}` -> `{c['fix']['to']}`" if c.get("fix") and c["status"] == "fail" else ""
        lines.append(f"| {c['id']} {c['title']} | {icon[c['status']]} | {c['detail']} | {fix} |")
    if review:
        lines += ["", f"## Guideline review ({review['model']})", "", review["review"]]
    return "\n".join(lines) + "\n"
