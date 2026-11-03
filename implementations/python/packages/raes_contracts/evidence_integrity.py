"""Integrity modes provable by the current scientific evidence response contract."""

from types import MappingProxyType

# None means the artifact contract's own checksum algorithm; a named algorithm
# adds an exact algorithm constraint. New guarantees need a response verifier,
# not only another string in a backend capability declaration.
_CHECKSUM_ALGORITHMS = MappingProxyType({"none": None, "checksum": None, "sha256-digest": "sha256"})


def evidence_integrity_modes() -> frozenset[str]:
    """Return the modes with an implemented emitted-content proof path."""

    return frozenset(_CHECKSUM_ALGORITHMS)


def validate_evidence_integrity_mode(mode: str, checksum_algorithm: str) -> None:
    """Refuse unsupported guarantees or an incompatible artifact checksum."""

    if mode not in _CHECKSUM_ALGORITHMS:
        raise ValueError(f"emitted evidence cannot prove integrity requirement {mode!r}")
    required_algorithm = _CHECKSUM_ALGORITHMS[mode]
    if required_algorithm is not None and checksum_algorithm != required_algorithm:
        raise ValueError("emitted evidence does not satisfy the required sha256 integrity mode")


__all__ = ["evidence_integrity_modes", "validate_evidence_integrity_mode"]
