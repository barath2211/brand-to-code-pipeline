# Evals and Benchmarks

## What matters

The business outcome is lead time. The things that drive it are: how often the first build passes QA, how many issues need a human, and how accurate extraction from guideline text is.

| Metric | How it's measured | Target |
|---|---|---|
| First-pass QA rate | Share of brands passing with no fixes | Tracked, no target (depends on client input) |
| Pass rate after auto-fix | Share passing within 3 attempts | ≥ 90% |
| Protected-value escalations | Share needing a human decision on primary/secondary | Tracked |
| Extraction field accuracy | Extracted config vs hand-labelled config, per field | ≥ 95% on colours, 100% "no invented values" |
| Build time | `build_log.json` total | Seconds, excluding LLM calls |
| Accessibility regressions | QA failures reaching production | 0 |

## Current results (this repo, mock provider)

| Brand | Input | First pass | After auto-fix | Fixes applied | Build time |
|---|---|---|---|---|---|
| Aurora Minerals | JSON | PASS | n/a | none | ~10 ms |
| Helix Bio | JSON | FAIL (3) | PASS on attempt 2 | muted text `#b0b0b0` to `#727272` (2.17:1 to 4.81:1), logo http to https | ~3 ms |
| Nordlys Energy | Guideline text | PASS | n/a | none; 6/6 colours, fonts and radius extracted correctly | ~2 ms |
| Kestrel Logistics | PDF brand book | FAIL (2) | PASS on attempt 2 | muted text `#8a948f` to `#686f6b`; brand name, 6/6 colours, fonts and radius read from the PDF | ~60 ms |

Helix Bio's primary colour (`#7fd1c4`) only reaches 1.72:1 as link text. The pipeline left the brand colour alone and derived a link shade (`#4c7d76`, 4.51:1) instead.

Honest caveat: four brands is a demo, not an eval set. The mock extractor is regex written for the sample guideline, so its perfect score proves the plumbing, not model quality.

## Running extraction evals against a real model

1. Add guideline files to `data/brands/*_guidelines.md` and a matching hand-written expected config.
2. Run `LLM_PROVIDER=ollama python src/cli.py build <file>` for each.
3. Compare `dist/<client>/brand.resolved.json` to the expected config field by field.
4. Track two numbers separately: **accuracy** on stated values, and **invented values** (anything in the output not present in the text). The second must stay at zero.

## Baseline vs automated (original system)

| | Manual process | Automated pipeline |
|---|---|---|
| Contract to live | 3 to 6 weeks | 2 hours to 2 days |
| Review loops | Several per client | Usually none |
| Where time went | Waiting between production and QA | Collecting complete brand input from the client |

The remaining time in the automated flow is mostly waiting on the client for missing brand details, which is why the guideline extraction step and clear validation errors matter.
