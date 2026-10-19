# Mizzy

Chef-side buying layer and live costing. See the project overview and feature spec in the Food Costing App project.

## Packages

- `mizzy/normalise` — the unit normalisation engine. Turns a supplier product string such as
  `TOMATOES CHOPPED 6X2.5KG` or `Tom Chop A10 Ctn 6` into a pack structure, a base unit
  (`kg`, `L`, `each`) and a base quantity, so prices from different suppliers compare per kg / per L / per each.

## Run the tests

```
pip install -e ".[dev]"
pytest -q
```

`tests/corpus.py` holds the test lines. Add real supplier strings there as they turn up; the expected values
are what a chef would say the pack contains.
