# Mizzy — working brief for Claude Code

Read this first, every session. It is the standing context for the repo.

## What Mizzy is

A chef-side **buying layer and live costing tool** for hospitality kitchens. The chef orders
*products*, not from suppliers. Mizzy scrapes every connected supplier's prices (overnight and
on demand), picks the cheapest per **normalised unit** for each line, splits the order by supplier,
clears free-delivery minimums where it can, and emails each supplier in its own format. Invoices
photographed afterwards feed live recipe and menu costing — **with no stocktake**.

- Not a catalogue host (Ordermentum, Fresho let you order within one supplier at a time).
- Not an inventory suite (MarketMan, Cooking the Books need stocktakes and onboarding teams).
- **Rule of thumb: if a feature needs a stocktake, it's out.**

Domain mizzy.com.au. Name is lower-case "mizzy" in logo/URL, "Mizzy" in prose. Founder: Jase,
a chef (ex–head chef, Beechmont Hotel), on Tamborine Mountain QLD. Built for small-to-mid venues,
food trucks, caterers, aged care, childcare, canteens — the kitchens big systems ignore.

## The full spec lives outside this repo

The feature spec, design system, UI mockups, pricing, market and growth analysis are in the
owner's **Food Costing App** project on claude.ai, as artifacts and a project overview doc.
This repo is the implementation. When a decision here needs the spec, ask Jase to paste the
relevant section rather than guessing — don't reinvent scope.

## Core design principles (these shape the code, not just the UI)

1. **Normalised unit is the foundation.** Every price compares per kg / per L / per each.
   The `mizzy/normalise` package already does this; everything downstream depends on it.
2. **Grey means guessed.** Any value the system inferred (a product match, a parsed pack, a
   recipe quantity) carries a confidence. Low confidence surfaces to the chef to confirm; it is
   never silently treated as fact. The `Confidence` enum in `mizzy/normalise/model.py` is the
   pattern — reuse it in matching, invoice parsing and costing.
3. **The ranking is sacred.** Cheapest-wins is never influenced by supplier payment. Any future
   sponsored placement is a separate, fenced slot.
4. **Suggest, never silently change.** Swaps, out-of-stock replacements, matched products — all
   proposed for a one-tap confirm, never applied behind the chef's back.
5. **No stocktake, anywhere.** Costing is purchase-price based.

## Repo layout (grows as we build)

```
mizzy/
  normalise/        # DONE v0.1 — pack string → base unit + quantity + confidence
  ingest/           # NEXT — price lists & invoices (PDF/CSV/image) → normalised line records
  match/            # product matching + fuzzy slider (exact / equivalent / substitute)
  resolve/          # cheapest-wins resolver, delivery optimiser
  scrape/           # per-supplier price scrapers (credentials stay out of the repo)
  cost/             # recipe & menu costing, budget
  api/              # backend
  web/              # the app (phone/tablet/desktop from one codebase)
tests/
```

## Conventions

- Python 3.10+. Standard library first; add a dependency only when it earns its place
  (document why in the commit). `pip install -e ".[dev]" && pytest`.
- **Every parser/matcher returns a confidence, never a bare value.** Mirror `normalise`.
- **Test corpus is sacred.** `tests/corpus.py` holds real and realistic supplier strings with
  expected results. Add real invoice lines as they arrive. A wrong expectation is a bug too.
- Keep units metric. Prices in AUD. Currency and unit always travel with a number.
- **Secrets never enter the repo or git history.** Supplier logins and API keys go in a local
  `.env` (gitignored) or the OS keychain. If a task needs a credential, stop and ask Jase to
  place it in `.env`; do not hardcode, echo, or commit it.
- Scrapers must be polite: rate-limited, off-peak, and behind a per-supplier health check so a
  broken scraper shows as "prices N days old" rather than silently wrong.

## Current status

- `mizzy/normalise` v0.1 — 131 corpus lines passing. Handles NxSIZE, A10-class tins, catch
  weight, dozens, produce each/bunch, packaging-per-each, egg/seafood grades, portion ranges,
  dimension descriptors.
- Everything else is unbuilt. See `TASKS.md`.

## The open risk that governs sequencing

Can we actually get clean, current prices out of Bidfood / PFD / Provista portals? Until that's
proven, the resolver is theoretical. So the near-term work is ordered to de-risk data first:
prove ingestion on real price lists/invoices, then prove one scraper, before building the resolver
on top. Don't build far ahead of proven data.
