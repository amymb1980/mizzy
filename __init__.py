"""Mizzy unit normalisation.

    >>> from mizzy.normalise import normalise
    >>> p = normalise("TOMATOES CHOPPED 6X2.5KG")
    >>> p.base_unit, p.base_qty
    ('kg', 15.0)
    >>> p.unit_price(61.50)
    4.1
"""

from .model import Pack, Confidence
from .parser import normalise

__all__ = ["normalise", "Pack", "Confidence"]
