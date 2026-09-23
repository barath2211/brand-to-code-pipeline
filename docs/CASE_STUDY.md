# Case study: client onboarding from 3 to 6 weeks down to hours

**My role:** I found the problem, designed the pipeline, built it hands-on with a colleague, then pitched it and ran the rollout.
**Setting:** Client onboarding at an enterprise SaaS company that delivers branded, embeddable web components.
**Result:** Delivery went from **3 to 6 weeks down to between 2 hours and 2 days**. 10 to 30 clients have gone through it so far.

---

## The situation

Every new client got a set of web components (share price, news, calendar and so on) styled to match their brand. The process was manual:

1. Production read the client's brand guidelines and hand-applied colours, fonts and logo to each component.
2. The onboarding team reviewed the result by eye.
3. Anything wrong went back to production, and the loop repeated.

The actual styling work wasn't the slow part. Waiting was: work sat in the queue between production and review, and every error meant another trip. The errors were predictable: a mistyped hex code, grey text too light to read, a logo on http that browsers block, a font with no fallback.

## What I noticed

Almost every correction the review team sent back was something a machine could check. Contrast ratios, hex formats, missing fields, http links. If those were checked automatically, the human review could focus on the few things that need taste.

## Key decisions

**One config file as the source of truth.** Each client's brand becomes a single structured config. Every component is generated from it. Fixing the config fixes everything, and no component can drift from the brand.

**AI only where the input is messy.** Brand guidelines come as PDFs and free text, so a model reads them and proposes a config. Everything after that (colour maths, rendering, QA) is plain code that behaves the same every time and can be tested.

**Automated QA that explains itself.** Every build runs accessibility contrast checks and consistency checks. A failure shows the measured value and the exact fix, instead of a vague "text looks too light".

**Fix what's safe, flag what isn't.** Safe fixes (darkening a grey, switching http to https) are applied automatically and QA re-runs. A client's core brand colours are never changed automatically. If a brand colour is too light for text, the system derives an accessible shade for that use and flags it for a person.

## Rollout

1. Piloted on a few new clients alongside the manual process and compared the results side by side.
2. Presented the comparison to management, the product manager and the VP for approval.
3. Made it the default for new clients, with the review team still signing off.

## Outcome

- **Lead time:** 3 to 6 weeks down to 2 hours to 2 days. The 2-hour cases are clients with a complete brand kit and a standard component set. The longer ones involve chasing missing brand details or a bigger component scope.
- **Review loops:** the production-to-review back-and-forth mostly disappeared, because the predictable errors are caught before anyone looks.
- **Scale:** 10 to 30 clients onboarded through it so far.

## What I'd do differently

- **Start with PDF input.** Most brand guides arrive as PDFs. This repo reads text-based PDFs; scanned ones would need OCR or a vision model.
- **Add visual regression.** Contrast checks catch readability problems, but not layout breakage. Screenshot comparison between builds is the next step.
- **Let clients see QA results directly.** A self-serve preview with live QA would cut the remaining back-and-forth on missing brand details.

## In this repo

All brands, content and code are fictional or rewritten. Try `python src/cli.py build-all --auto-fix --provider mock`: Helix Bio fails QA on purpose and is repaired, and Kestrel Logistics is built straight from a PDF brand book.
