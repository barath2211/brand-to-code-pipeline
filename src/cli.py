"""Brand-to-code CLI.

  python src/cli.py build data/brands/aurora-minerals.json
  python src/cli.py build data/brands/helix-bio.json --auto-fix
  python src/cli.py build data/brands/nordlys-energy_guidelines.md --provider mock
  python src/cli.py build-all --auto-fix
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brandpipe.pipeline import ROOT, BrandPipeline, BuildError  # noqa: E402


def show(result: dict) -> None:
    log, rep = result["log"], result["report"]
    print(f"\n=== {log['client_id']} | provider={log['provider']} | QA {rep['status'].upper()} | {log['timings']['total_ms']} ms ===")
    for a in log["attempts"]:
        extra = f"  fixes: {a['fixes_applied']}" if a.get("fixes_applied") else ""
        print(f"  attempt {a['attempt']}: {a['status']} ({a['failed']} failed){extra}")
    for c in rep["checks"]:
        if c["status"] != "pass":
            print(f"  [{c['status'].upper()}] {c['id']} {c['title']}: {c['detail']}")
    if result["review"]:
        print("  Guideline review:", result["review"]["review"].replace("\n", " | "))
    print(f"  Output: {log['output_dir']}/index.html")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("source", type=Path)
    sub.add_parser("build-all")
    for p in (b, sub.choices["build-all"]):
        p.add_argument("--auto-fix", action="store_true")
        p.add_argument("--provider", choices=["mock", "ollama", "ollama-small", "openai", "gemini", "anthropic"])
    args = ap.parse_args()

    pipe = BrandPipeline(args.provider)
    sources = [args.source] if args.cmd == "build" else sorted((ROOT / "data" / "brands").glob("*"))
    code = 0
    for src in sources:
        try:
            res = pipe.build(src, auto_fix=args.auto_fix)
            show(res)
            code |= res["report"]["status"] == "fail"
        except BuildError as exc:
            print(f"\n=== {src.name} | BLOCKED ===\n{exc}")
            code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
