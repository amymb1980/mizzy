# Mizzy — task list

Ordered to de-risk the data pipeline before building on top of it. Tick as you go.

## Now

- [ ] **Price-list / invoice ingestion** (`mizzy/ingest`). Input: a supplier price list or invoice
      as PDF, CSV, or photo. Output: a list of line records `{raw_description, pack (from
      normalise), unit_price, pack_price, supplier, date, confidence}`. Start with CSV (easiest),
      then text-PDF, then image/scanned (OCR). One adapter per input shape; AI fallback for messy
      ones. Feed every description through `mizzy/normalise`. **Needs real files from Jase** —
      Bidfood/PFD/Provista/Moco price lists or invoices, even photos.
- [ ] **Grow the normalise corpus from real lines.** Every real invoice line goes into
      `tests/corpus.py` with its expected pack. Report the true hit rate vs the hand-written corpus.

## Next (needs a supplier login)

- [ ] **One scraper, end to end** (`mizzy/scrape`). Log into ONE portal (Bidfood or PFD) with
      Jase's own credentials from `.env`, pull the price list, handle search/pagination, output the
      same line records as ingestion. Document exactly what broke: MFA, bot detection, layout.
      This is the real go/no-go for the whole product.
- [ ] Second scraper, to see how much is reusable vs per-supplier.
- [ ] Per-supplier health check + "prices N days old" staleness surfacing.

## Then (the resolver — the actual product)

- [ ] **Product matching** (`mizzy/match`): exact / equivalent / substitute bands + fuzzy slider.
      Returns matches with confidence. Reuses normalise's base unit for comparability.
- [ ] **Cheapest-wins resolver** (`mizzy/resolve`): per line, lowest normalised price across
      connected suppliers; per-line override.
- [ ] **Delivery optimiser**: supplier run days, cut-offs, free-delivery minimums; trade lines
      between suppliers to clear minimums.
- [ ] Split-and-send: one basket → N supplier orders in each supplier's format.

## Later

- [ ] Invoice photo → receiving check → 3-way match (ordered vs received vs invoiced).
- [ ] Live ingredient cost from invoices; AI recipe search; component swap.
- [ ] Menu costing, price-move alerts, weekly budget with inflation adjustment, savings report.
- [ ] Backend API + web app (phone/tablet/desktop, one codebase).

## Housekeeping before first real work

- [ ] Confirm `pip install -e ".[dev]" && pytest` is green on Jase's machine.
- [ ] Create `.env.example` listing the vars (no values): supplier usernames, the model API key.
- [ ] Decide the AI provider + model for ingestion/matching/recipe search, and the per-venue
      budget (spec target: under ~$1/venue/week).
