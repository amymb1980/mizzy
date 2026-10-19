import math

import pytest

from mizzy.normalise import Confidence, normalise

from .corpus import CORPUS


@pytest.mark.parametrize("raw,unit,qty,note", CORPUS, ids=[c[0] for c in CORPUS])
def test_corpus(raw, unit, qty, note):
    p = normalise(raw)
    if unit is None:
        assert p.base_qty is None, f"{raw!r}: expected no pack, got {p.describe()} ({p.base_unit} {p.base_qty})"
        assert p.confidence == Confidence.NONE
        return
    assert p.base_unit == unit, f"{raw!r}: unit {p.base_unit} != {unit}  [{p.describe()}] notes={p.notes}"
    assert p.base_qty is not None, f"{raw!r}: no base_qty  notes={p.notes}"
    tol = 0.05 if "A10" in raw.upper() or "tin" in (note or "") else 0.01
    assert math.isclose(p.base_qty, qty, rel_tol=tol), (
        f"{raw!r}: qty {p.base_qty} != {qty}  [{p.describe()}] notes={p.notes}"
    )


def test_unit_price():
    p = normalise("TOMATOES CHOPPED 6X2.5KG")
    assert p.unit_price(61.50) == 4.1


def test_a10_vs_pouch_comparable():
    pouch = normalise("Tomatoes Chopped 2.5kg Pouch Ctn 6")
    tins = normalise("TOM CHOP A10 CTN6")
    # Pouches: $61.50 for 15 kg = $4.10/kg.  Tins: $66.90 for ~18 kg = $3.72/kg.
    # The dearer carton is the cheaper product. This is the whole point of the normaliser.
    assert pouch.base_qty == 15.0 and abs(tins.base_qty - 18.0) < 0.5
    assert tins.unit_price(66.90) < pouch.unit_price(61.50)


def test_confidence_grey_rule():
    assert normalise("TOMATOES CHOPPED 6X2.5KG").confidence == Confidence.HIGH
    assert normalise("BEANS BAKED A10").confidence == Confidence.MEDIUM
    assert normalise("Limes each").confidence == Confidence.LOW
    assert normalise("Delivery Fee").confidence == Confidence.NONE


def test_name_strips_pack_tokens():
    assert normalise("TOMATOES CHOPPED 6X2.5KG").name == "tomatoes chopped"
    assert normalise("Tomatoes Chopped 2.5kg Pouch Ctn 6").name == "tomatoes chopped"
    assert normalise("TOM CHOP A10 CTN6").name == "tom chop"
