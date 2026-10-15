"""Compatibility rules for historical protocols; new captures allocate no versions."""

from tools.evidence_bundle_index import revision_key
from tools.research_evidence import is_capture


def source_bound_revision(value: object) -> bool:
    return is_capture(value) or revision_key(value) >= (4, 0, 0)


def expected_corpus_revision(value: object) -> str:
    if is_capture(value):
        return "4.0.0"
    major, _, _ = revision_key(value)
    if major == 42 or major >= 45:
        return "4.0.0"
    return "3.0.0" if major >= 16 else "2.0.0"
