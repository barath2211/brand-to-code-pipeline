# PRD: Brand-to-Code Onboarding Pipeline

| | |
|---|---|
| Author | Barath Kumar (with a colleague, original internal version) |
| Status | Reference implementation (public). Original shipped internally. |
| Last updated | September 2026 |

## 1. Summary

New clients need a set of embeddable web components styled to their brand. Today that's manual styling followed by manual review, with errors bouncing back and forth. This product turns brand input into a validated config, generates the components from it, and checks the result automatically, so the first build is usually the final one.

## 2. Problem

- **Long lead time.** 3 to 6 weeks from signed contract to live components.
- **Rework loop.** Production applies brand rules by hand; onboarding QA finds mistakes; work goes back. Most delay was waiting in this loop, not doing the work.
- **Predictable errors.** Mistyped hex codes, grey text that fails accessibility, fonts without fallbacks, logos on http that browsers block.
- **Doesn't scale.** Every new client added the same manual effort.

## 3. Personas

| Persona | Pain today | What changes |
|---|---|---|
| Production designer/developer | Re-types brand values, redoes work after review | Edits one config; components regenerate |
| Onboarding specialist | Reviews by eye, writes long correction emails | Reads a QA report with exact ratios and fixes |
| Account manager | Can't give clients a reliable go-live date | Same-day preview for most clients |
| Client brand team | Unsure their brand was applied correctly | Preview page plus a report listing every check |

## 4. Goals and non-goals

**Goals**
1. Generate a complete, branded component set from one config file.
2. Catch every accessibility and consistency issue that the manual review used to catch, automatically.
3. Fix safe issues automatically and explain every change.
4. Accept brand guidelines as free text and extract a config from them.

**Non-goals**
- Designing new components. The component library is fixed; only styling is per client.
- Changing a client's core brand colours without a human decision.
- Scanned (image-only) brand books. Text-based PDFs are supported; scans need OCR or a vision model (v2).

## 5. User stories and acceptance criteria

| # | Story | Acceptance criteria |
|---|---|---|
| US-1 | As a production developer, I want to go from a brand config to all components in one command. | One CLI command produces tokens, components, preview and report in `dist/<client>`. |
| US-2 | As an onboarding specialist, I want accessibility checked automatically. | Six text/background pairs checked against WCAG AA 4.5:1. Each failure shows the actual ratio. |
| US-3 | As an onboarding specialist, I want safe problems fixed for me. | With `--auto-fix`, muted text and logo protocol are fixed; QA re-runs; report lists every change with before and after. |
| US-4 | As a brand owner, I want our primary colours untouched. | Primary and secondary are never auto-changed. Where they fail for links, a derived accessible shade is used and noted in the report. |
| US-5 | As a production developer, I want to start from the client's guideline text. | A `.md` guideline produces a valid config. Values not stated in the text are left out rather than invented. |
| US-6 | As an engineer, I want components that can't drift from the brand. | Templates contain no literal colours; a QA check fails the build if any appear. |
| US-7 | As an account manager, I want bad input to fail fast. | Invalid configs are blocked before rendering with a list of every problem. |

## 6. Key product decisions

1. **Config as the single source of truth.** Every output is generated from it. Fixing the config fixes everything.
2. **LLM only at the edges.** The model reads unstructured guidelines and optionally reviews the result. Colour maths, rendering and QA are deterministic, testable code.
3. **Fix what's safe, flag what's not.** Automating the obvious fixes removes most of the loop. Anything touching brand identity stays a human decision.
4. **Explain every result.** A failing check always comes with the measured value and a suggested fix, so no one has to guess.

## 7. Trade-offs

| Decision | Alternative | Why this way |
|---|---|---|
| Jinja templates + CSS variables | Per-client hand-written CSS | One template set, unlimited brands; no drift |
| Deterministic QA | LLM visual review of screenshots | Repeatable, explainable, instant; LLM review kept as an optional second opinion |
| Local models by default | Hosted API only | Client brand material is often pre-launch and confidential |
| Derived link shade | Auto-darken the primary colour | Keeps the brand intact and still passes accessibility |

## 8. Edge cases

| Case | Behaviour |
|---|---|
| Guideline text misses a required colour | Extraction leaves it out; validation blocks with a clear message listing what's missing |
| Short hex (`#abc`) | Normalised to six digits |
| Brand primary too light for text | `on-primary` switches to dark text automatically |
| Brand primary too light for links | Derived `link` token; primary unchanged; noted in report |
| Logo on http | Fails QA; auto-fix proposes https |
| No logo | Warning; header uses the brand name as text |
| Fix can't reach target | Loop stops after 3 attempts and reports the remaining failures |
| Unknown component requested | Blocked at validation |

## 9. Success metrics

| Metric | Baseline | Target |
|---|---|---|
| Contract-to-live lead time | 3 to 6 weeks | Under 2 days (original system: 2 hours to 2 days) |
| Review round-trips per client | Several | 0 to 1 |
| Builds passing QA first time (after auto-fix) | n/a | ≥ 90% |
| Accessibility issues reaching production | Occasional | 0 |

## 10. Rollout

| Phase | Scope | Exit criteria |
|---|---|---|
| 1. Pilot | 3 new clients, run alongside manual process | Generated output matches or beats manual result in side-by-side review |
| 2. Default for new clients | All new onboarding, manual review still signs off | Review round-trips ≤ 1 for 4 weeks |
| 3. Migrate existing clients | Regenerate existing client configs | No visual regressions reported by clients |

## 11. Open questions

- Should clients be able to edit their config through a self-serve form, with QA running live?
- Should the LLM review step become mandatory once its false-positive rate is known?
