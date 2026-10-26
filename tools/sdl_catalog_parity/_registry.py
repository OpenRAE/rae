"""Merged reference-edge expectation registry."""

from __future__ import annotations

from tools.sdl_catalog_parity._expectations_1 import EXPECTATIONS_PART_1
from tools.sdl_catalog_parity._expectations_2 import EXPECTATIONS_PART_2
from tools.sdl_catalog_parity._expectations_3 import EXPECTATIONS_PART_3
from tools.sdl_catalog_parity._expectations_4 import EXPECTATIONS_PART_4

REFERENCE_EDGE_EXPECTATIONS: dict[str, tuple[str, str, str, str]] = {
    **EXPECTATIONS_PART_1,
    **EXPECTATIONS_PART_2,
    **EXPECTATIONS_PART_3,
    **EXPECTATIONS_PART_4,
}

_PART_TOTAL = len(EXPECTATIONS_PART_1) + len(EXPECTATIONS_PART_2) + len(EXPECTATIONS_PART_3) + len(EXPECTATIONS_PART_4)
if len(REFERENCE_EDGE_EXPECTATIONS) != _PART_TOTAL:
    raise AssertionError("reference-edge expectation parts overlap")
