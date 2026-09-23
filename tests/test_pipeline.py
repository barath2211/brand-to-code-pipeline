import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brandpipe.color import contrast_ratio, darken_until  # noqa: E402
from brandpipe.pipeline import BrandPipeline, BuildError  # noqa: E402
from brandpipe.schema import validate  # noqa: E402

BRANDS = ROOT / "data" / "brands"


@pytest.fixture()
def pipe(tmp_path):
    return BrandPipeline("mock", out_dir=tmp_path)


def test_contrast_known_values():
    assert contrast_ratio("#000000", "#ffffff") == 21.0
    assert contrast_ratio("#ffffff", "#ffffff") == 1.0


def test_darken_until_meets_target():
    fixed = darken_until("#b0b0b0", "#ffffff", 4.5)
    assert contrast_ratio(fixed, "#ffffff") >= 4.5


def test_valid_brand_passes_qa(pipe):
    res = pipe.build(BRANDS / "aurora-minerals.json")
    assert res["report"]["status"] == "pass"


def test_bad_brand_fails_without_autofix(pipe):
    res = pipe.build(BRANDS / "helix-bio.json")
    failed = {c["id"] for c in res["report"]["checks"] if c["status"] == "fail"}
    assert {"C2", "C3", "L1"} <= failed


def test_autofix_repairs_but_never_touches_brand_primary(pipe):
    original = json.loads((BRANDS / "helix-bio.json").read_text())
    res = pipe.build(BRANDS / "helix-bio.json", auto_fix=True)
    assert res["report"]["status"] == "pass"
    assert res["config"]["colors"]["primary"] == original["colors"]["primary"]
    assert res["config"]["logo_url"].startswith("https://")


def test_components_use_tokens_only(pipe, tmp_path):
    pipe.build(BRANDS / "aurora-minerals.json")
    for f in (tmp_path / "aurora-minerals" / "components").glob("*.html"):
        assert "#" not in f.read_text().replace('href="#"', "")


def test_guideline_extraction(pipe):
    res = pipe.build(BRANDS / "nordlys-energy_guidelines.md")
    cfg = res["config"]
    assert cfg["colors"] == {
        "primary": "#12355b", "secondary": "#2bb673", "background": "#ffffff",
        "surface": "#f4f6f8", "text": "#222831", "muted_text": "#5f6b7a",
    }
    assert cfg["typography"]["heading_font"] == "Source Serif Pro"
    assert cfg["radius_px"] == 6


def test_invalid_config_is_blocked(pipe, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"client_id": "Bad Name", "display_name": "x", "colors": {"primary": "blue"}, "typography": {}}))
    with pytest.raises(BuildError):
        pipe.build(bad)


def test_schema_normalises_short_hex():
    cfg = {"client_id": "a1", "display_name": "A", "typography": {"heading_font": "X", "body_font": "Y", "base_size_px": 16},
           "colors": {k: "#abc" for k in ["primary", "secondary", "background", "surface", "text", "muted_text"]}}
    merged, errors = validate(cfg)
    assert not errors and merged["colors"]["primary"] == "#aabbcc"
