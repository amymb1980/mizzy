"""Parse Australian foodservice product strings into a Pack.

Design notes
------------
Supplier strings are abbreviations piled on abbreviations: "TOM CHOP A10 CTN 6", "6X2.5KG",
"12PK 400G", "CTN 10KG", "2.5KG PCH X 4", "BUNCH", "EA", "KG" (catch weight), "4/5KG".
We do NOT try to understand the product; only the pack. The product name is whatever is
left after the pack tokens are pulled out, which the matcher uses later.

Pipeline:
  1. clean text  (lowercase, unify × / x / *, strip punctuation noise)
  2. strip descriptors that look like sizes but aren't  (grades "21/25", "U10"; portion
     ranges "150-180g"; dimensions "10in", "45cm x 600m"; carton grades "700g" on eggs)
  3. resolve known pack codes  (A10, A9, #10 → ~3 kg)
  4. find all (count) and (size unit) tokens
  5. assemble outer × inner × size, falling back to sensible defaults
  6. compute base_unit / base_qty and a confidence

Everything the parser is unsure about is recorded in `notes` and lowers confidence,
so the app can show it grey and ask the chef.
"""

from __future__ import annotations

import re
from typing import Optional

from .model import Confidence, Pack

# ----------------------------------------------------------------------------- units

MASS = {
    "mg": 0.000001,
    "g": 0.001, "gm": 0.001, "gr": 0.001, "gram": 0.001, "grams": 0.001,
    "kg": 1.0, "kgs": 1.0, "kilo": 1.0, "kilos": 1.0, "kilogram": 1.0, "kilograms": 1.0,
    "lb": 0.45359237, "lbs": 0.45359237, "oz": 0.0283495,
}
VOLUME = {
    "ml": 0.001, "mls": 0.001, "millilitre": 0.001, "millilitres": 0.001,
    "l": 1.0, "lt": 1.0, "ltr": 1.0, "ltrs": 1.0, "litre": 1.0, "litres": 1.0, "liter": 1.0, "liters": 1.0,
    "gal": 3.78541, "qt": 0.946353, "floz": 0.0295735,
}
UNIT_WORDS = sorted(list(MASS) + list(VOLUME), key=len, reverse=True)
UNIT_RE = "|".join(re.escape(u) for u in UNIT_WORDS)
NUM = r"(?:\d+(?:\.\d+)?)"

# Known tin codes → (size kg, note). AU foodservice lives on these.
PACK_CODES: dict[str, tuple[float, str]] = {
    "a10": (3.0, "A10 tin ≈ 3 kg (2.9–3.1 kg by product)"),
    "#10": (3.0, "#10 tin ≈ 3 kg"),
    "a9": (2.65, "A9 tin ≈ 2.65 kg"),
    "a6": (1.8, "A6 tin ≈ 1.8 kg"),
    "a2.5": (0.82, "A2.5 tin ≈ 820 g"),
    "a2": (0.60, "A2 tin ≈ 600 g"),
    "a1": (0.30, "A1 tin ≈ 300 g"),
}
COUNT_WORDS = {"half dozen": 6, "1/2 dozen": 6, "half doz": 6, "1/2 doz": 6, "dozen": 12, "doz": 12, "dz": 12, "pair": 2}

EACH_WORDS = {"ea", "each", "pc", "pce", "pcs", "piece", "pieces", "unit", "units",
              "bunch", "bch", "bun", "head", "hd", "punnet", "pnt", "pun", "tray", "sleeve", "slv",
              "roll", "rl", "loaf", "stick", "stk", "whole", "pkt", "pk", "pack", "packet", "ct"}
CONTAINER_WORDS = {"ctn", "carton", "cs", "case", "box", "bx", "bag", "bg", "pch", "pouch",
                   "tin", "can", "cn", "btl", "bottle", "jar", "tub", "pail", "bkt", "bucket",
                   "drum", "sachet", "sch", "tray", "tr", "bulk", "frozen", "frz", "fresh", "iqf",
                   "chilled", "ch", "tetra", "squeeze", "block", "wheel", "sliced", "approx", "avg"}
# Non-food lines compared per each: their "size" (650ml container, 2ply) is a descriptor
PACKAGING_WORDS = {"container", "containers", "lid", "lids", "napkin", "napkins",
                   "glove", "gloves", "wrap", "foil", "liner", "liners", "towel",
                   "towels", "straw", "straws", "cutlery", "forks", "spoons", "knives",
                   "plates", "bowls", "cups", "takeaway", "disposable", "bin", "cling",
                   "film", "serviette", "serviettes", "tissue", "paper"}
# Products whose "Ng" is a carton grade, not a weight
GRADE_G_WORDS = {"egg", "eggs"}

CATCH_RE = re.compile(r"\b(rw|r/w|r w|random weight|catch weight|c/w|c w|per kg|p/kg|\$/kg|kg price|avg|approx)\b")


def _clean(s: str) -> str:
    s = s.lower().strip()
    s = s.replace("×", "x").replace("*", "x").replace("@", " x ")
    s = re.sub(r"[()\[\]{}'\"]", " ", s)
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)         # 1,000 → 1000
    s = re.sub(r"(?<=\d),(?=\d)", ".", s)             # 2,5 → 2.5
    s = re.sub(r"(?<=[a-z])/(?=[a-z])", " ", s)       # r/w, c/w handled as words with space
    s = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", s)
    s = re.sub(r"\s+", " ", s)
    return f" {s} "


def _strip_descriptors(t: str, notes: list[str]) -> tuple[str, bool]:
    """Remove tokens that look like sizes/counts but describe the product, not the pack.
    Returns (text, is_packaging)."""
    # seafood / produce grades: 21/25, 16/20, u10, u/10, 5/6
    t = re.sub(r"(?<![\w.])\d{1,2}/\d{1,2}(?![\w.])(?!\s*(?:doz|dozen|dz))", " ", t)
    t = re.sub(r"(?<![\w.])u/?\d{1,2}(?![\w.])", " ", t)
    # portion / piece ranges: 150-180g, 150/180g, 4-5kg → we keep the UNIT WORD as a catch-weight hint
    m = re.search(rf"(?<![\w.])({NUM})\s*[-–]\s*({NUM})\s*({UNIT_RE})(?![a-z])", t)
    if m:
        unit = m.group(3)
        notes.append(f"range {m.group(1)}–{m.group(2)} {unit} is a portion/piece size, not the pack")
        t = t[: m.start()] + f" <range {unit}> " + t[m.end():]
    # dimensions: 10in, 4in, 45cm, 600m, 44cm x 150m
    t = re.sub(r"(?<![\w.])\d+(?:\.\d+)?\s*(?:in|inch|inches|cm|mm|m|metre|metres|meter)(?![a-z])", " ", t)
    # ply, mm cut sizes already gone above; strip "2ply"
    t = re.sub(r"(?<![\w.])\d+\s*ply(?![a-z])", " ", t)
    words = set(re.findall(r"[a-z]+", t))
    is_packaging = bool(words & PACKAGING_WORDS)
    if words & GRADE_G_WORDS:
        # eggs: "700g" is the carton grade
        t2 = re.sub(r"(?<![\w.])\d{2,3}\s*g(?![a-z])", " ", t)
        if t2 != t:
            notes.append("egg carton grade (g) ignored; eggs compared per each")
            t = t2
    return t, is_packaging


def normalise(raw: str) -> Pack:
    pack = Pack(raw=raw)
    s = _clean(raw)
    if not s.strip():
        return pack
    notes = pack.notes
    text = s

    if CATCH_RE.search(text):
        pack.catch_weight = True
        notes.append("catch weight: priced per kg, delivered weight varies")

    text, is_packaging = _strip_descriptors(text, notes)

    # ---- known tin codes, optionally with count on either side: 6xa10 | a10 x 6 | a10 ctn6 | a10 ctn 6
    code_size: Optional[float] = None
    for code, (size, note) in PACK_CODES.items():
        pat = re.escape(code)
        m = re.search(rf"(?<![\w.])(?:(\d+)\s*x\s*)?{pat}(?:\s*x\s*(\d+))?(?![\w.])", text)
        if m:
            code_size = size
            notes.append(note)
            n = m.group(1) or m.group(2)
            text = text[: m.start()] + (f" <code> x {n} " if n else " <code> ") + text[m.end():]
            break

    # ---- explicit sizes
    sizes: list[tuple[float, str, Optional[int]]] = []
    consumed: list[tuple[int, int]] = []

    def free(m):
        return not any(a <= m.start() < b for a, b in consumed)

    # 6x2.5kg | 6 x 2.5 kg | 12/400g | 24/400ml
    for m in re.finditer(rf"(?<![\w.])(\d+)\s*(?:x|/)\s*({NUM})\s*({UNIT_RE})(?![a-z])", text):
        sizes.append((float(m.group(2)), m.group(3), int(m.group(1)))); consumed.append(m.span())
    # 2.5kg x 6 | 400ml 24ct | 400ml ctn 24 | 2.5kg pch x4 | 1 litre x 12
    for m in re.finditer(
        rf"(?<![\w.])({NUM})\s*({UNIT_RE})\s*(?:(?:{'|'.join(CONTAINER_WORDS)})\s*)?(?:x\s*|/\s*)?(\d+)\s*(?:ct|pk|s)?(?![\w.])",
        text,
    ):
        if free(m):
            sizes.append((float(m.group(1)), m.group(2), int(m.group(3)))); consumed.append(m.span())
    # bare size
    for m in re.finditer(rf"(?<![\w.])({NUM})\s*({UNIT_RE})(?![a-z])", text):
        if free(m):
            sizes.append((float(m.group(1)), m.group(2), None)); consumed.append(m.span())

    for a, b in sorted(consumed, reverse=True):
        text = text[:a] + " " * (b - a) + text[b:]

    # ---- count words first (dozen, half dozen) so their digits aren't re-read as counts
    counts: list[int] = []
    for w, mult in COUNT_WORDS.items():
        m = re.search(rf"(?<![a-z\d/])(\d+)?\s*{re.escape(w)}(?![a-z])", text)
        if m:
            if m.group(1):
                counts.append(int(m.group(1)))
            counts.append(mult); notes.append(f"{w} = {mult}")
            text = text[: m.start()] + " " * (m.end() - m.start()) + text[m.end():]
            break
    # ---- leftover counts: ctn 6 | ctn6 | x 6 | 12pk | 48pk | 2000s | 24ct | 6pk x 8 | 10 x 100
    for m in re.finditer(r"(?:(?<![\w.])|(?<=ctn)|(?<=cs))(\d+)\s*(?:x|pk|pack|pkt|ct|s|'s)?(?![\w.])", text):
        n = int(m.group(1))
        if 1 <= n <= 5000:
            counts.append(n)

    tokens = set(re.findall(r"[a-z#.]+", text))
    is_each = bool(tokens & EACH_WORDS)

    # ---- packaging: always per each, counts multiply, sizes are descriptors
    if is_packaging:
        pk_counts: list[int] = []
        rest = s
        for m in re.finditer(r"(?<![\w.])(\d+)\s*x\s*(\d+)(?![\w.])", s):
            pk_counts += [int(m.group(1)), int(m.group(2))]
            rest = rest.replace(m.group(0), " ")
        pk_counts += [int(m.group(1)) for m in re.finditer(r"(?<![\w.])(\d+)\s*(?:pk|pack|pkt|ct|s|'s)(?![\w.])", rest)]
        pk_counts = pk_counts or [c for c in counts]
        n = 1
        for c in pk_counts:
            n *= c
        pack.inner = n
        pack.base_unit, pack.base_qty = "each", float(n)
        pack.confidence = Confidence.MEDIUM if counts else Confidence.LOW
        notes.append("packaging/non-food: compared per each; stated ml/cm are the item's size")
        pack.name = _name(s)
        return pack

    # ---- assemble
    if code_size is not None and not sizes:
        inner = counts[0] if counts else 1
        if not counts:
            notes.append("tin count not stated; assumed 1")
        pack.inner, pack.size, pack.size_unit = inner, code_size, "kg"
        pack.confidence = Confidence.MEDIUM
    elif sizes and not (pack.catch_weight and all(c is None for _, _, c in sizes)):
        sizes.sort(key=lambda t: (t[2] is None, -_to_base(t[0], t[1])[1]))
        size, unit, attached = sizes[0]
        inner = attached or (counts[0] if counts else 1)
        if attached and counts and counts[0] != attached:
            pack.outer = counts[0]
            notes.append(f"outer count {counts[0]} from a second number; check")
        pack.inner, pack.size, pack.size_unit = inner, size, unit
        pack.confidence = Confidence.HIGH if (attached or not counts or inner == 1) else Confidence.MEDIUM
        if len(sizes) > 1:
            others = [f"{a:g}{u}" for a, u, _ in sizes[1:]]
            notes.append(f"other sizes ignored: {', '.join(others)}")
            # a bracketed total like "(5kg)" after "2 x 2.5kg" is fine; anything else lowers confidence
            if not (len(sizes) == 2 and abs(_to_base(*sizes[1][:2])[1] - pack.inner * _to_base(size, unit)[1]) < 1e-6):
                pack.confidence = Confidence.MEDIUM
    elif pack.catch_weight:
        pack.base_unit, pack.base_qty = "kg", 1.0
        pack.confidence = Confidence.MEDIUM
        if sizes:
            notes.append("stated weight treated as approximate; priced per kg")
    elif is_each or counts:
        n = 1
        for c in counts:
            n *= c
        pack.inner = n
        pack.base_unit, pack.base_qty = "each", float(n)
        pack.confidence = Confidence.MEDIUM if counts else Confidence.LOW
        notes.append("no weight or volume stated; compared per each")
    else:
        bare = [u for u in ("kg", "l", "ltr", "lt") if re.search(rf"(?<![\w.]){u}(?![\w.])", text)]
        if bare:
            pack.base_unit = "kg" if bare[0] == "kg" else "L"
            pack.base_qty = 1.0
            pack.catch_weight = pack.base_unit == "kg"
            pack.confidence = Confidence.MEDIUM
            notes.append(f"sold per {pack.base_unit}")
        else:
            pack.confidence = Confidence.NONE
            notes.append("could not find a pack size")

    if pack.size is not None and pack.size_unit:
        base_unit, per = _to_base(pack.size, pack.size_unit)
        pack.base_unit = base_unit
        pack.base_qty = round(pack.outer * pack.inner * per, 6)

    pack.name = _name(s)
    return pack


def _to_base(size: float, unit: str) -> tuple[str, float]:
    if unit in MASS:
        return "kg", size * MASS[unit]
    if unit in VOLUME:
        return "L", size * VOLUME[unit]
    return "each", size


def _name(s: str) -> str:
    t = s
    t = re.sub(rf"(?<![\w.])\d+\s*(?:x|/)\s*{NUM}\s*(?:{UNIT_RE})(?![a-z])", " ", t)
    t = re.sub(rf"(?<![\w.]){NUM}\s*(?:{UNIT_RE})\s*(?:x|/)?\s*\d*\s*(?:ct|pk|s)?(?![\w.])", " ", t)
    t = re.sub(rf"(?<![\w.]){NUM}\s*[-–/]\s*{NUM}\s*(?:{UNIT_RE})(?![a-z])", " ", t)
    t = re.sub(r"(?<![\w.])\d{1,2}/\d{1,2}(?![\w.])", " ", t)
    t = re.sub(r"(?<![\w.])u/?\d{1,2}(?![\w.])", " ", t)
    t = re.sub(r"(?<![\w.])\d+(?:\.\d+)?\s*(?:in|inch|cm|mm|m|ply)(?![a-z])", " ", t)
    for code in PACK_CODES:
        t = re.sub(rf"(?<![\w.]){re.escape(code)}(?![\w.])", " ", t)
    t = re.sub(r"(?<![\w.])\d+\s*(?:x|pk|pack|pkt|ct|s|'s)?(?![\w.])", " ", t)
    t = re.sub(r"(?<![\w.])(?:ctn|cs)\d*(?![\w.])", " ", t)
    words = [w for w in t.split()
             if w not in CONTAINER_WORDS and w not in EACH_WORDS and w not in COUNT_WORDS
             and w not in {"x", "rw", "r", "w", "per", "kg", "l", "lt", "ltr"}]
    return " ".join(words).strip()
