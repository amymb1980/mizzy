from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Confidence(str, Enum):
    """How sure the parser is. Mirrors the app's grey/black rule:
    anything below HIGH is shown grey and needs a chef to confirm."""

    HIGH = "high"        # explicit size and unit found, arithmetic is unambiguous
    MEDIUM = "medium"    # resolved via a known pack code (A10, bunch, ...) or a default
    LOW = "low"          # guessed; e.g. "each" with no weight, or a count with no size
    NONE = "none"        # could not parse; base_qty is None


@dataclass
class Pack:
    """The structure of one purchasable line, as a chef would describe it.

    outer × inner × size unit   e.g. 1 × 6 × 2.5 kg  (a carton of six 2.5 kg pouches)
    """

    raw: str
    outer: int = 1                  # cartons / cases in the sellable unit (almost always 1)
    inner: int = 1                  # pieces inside: cans, pouches, bottles, each
    size: Optional[float] = None    # size of one piece, in `size_unit`
    size_unit: Optional[str] = None # g, kg, ml, L, each
    base_unit: Optional[str] = None # kg, L, each  — the comparable unit
    base_qty: Optional[float] = None
    confidence: Confidence = Confidence.NONE
    notes: list[str] = field(default_factory=list)
    catch_weight: bool = False      # priced per kg, delivered at variable weight
    name: str = ""                  # the product string with pack tokens stripped

    def unit_price(self, line_price: float) -> Optional[float]:
        """Price per base unit, from the price of one sellable line (one carton, one bag...)."""
        if not self.base_qty:
            return None
        return round(line_price / self.base_qty, 4)

    def describe(self) -> str:
        parts = []
        if self.outer > 1:
            parts.append(f"{self.outer} ×")
        if self.inner > 1:
            parts.append(f"{self.inner} ×")
        if self.size is not None and self.size_unit:
            parts.append(f"{self.size:g} {self.size_unit}")
        elif self.base_unit == "each":
            parts.append("each")
        return " ".join(parts) or "?"
