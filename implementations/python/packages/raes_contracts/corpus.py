"""Single seam for resolving the published RAES contract corpus.

The ``contracts/`` tree at the repository root is the hand-governed normative
authority (ADR-009): published schemas, the fixture conformance corpus, backend
and semantic capability profiles, and the concept-authority catalogs. Every
loader that reads that corpus resolves through this module rather than
reconstructing a repository path, so:

* an **installed distribution** finds the corpus shipped as package data under
  ``raes_contracts/_corpus`` (see the wheel/sdist ``force-include`` in
  ``implementations/python/pyproject.toml``), resolved via
  ``importlib.resources`` so it is install-layout independent; and
* a **source / editable checkout** finds the in-repo ``contracts/`` authority.

This is the single extension seam: adding a future corpus family needs one
``force-include`` pattern and one call site through :func:`corpus_family_root`,
not a new ``Path(__file__).parents[N]`` heuristic in every loader.

Caller-controlled override roots (``--fixtures-root`` / ``--profiles-root``) are
deliberately *not* handled here; they stay explicit inputs at the loader
boundary, distinct from the packaged-resource default.
"""

from __future__ import annotations

import importlib.resources as resources
from functools import cache
from pathlib import Path

_CORPUS_PACKAGE = "raes_contracts"
_BUNDLED_DIRNAME = "_corpus"
_REPO_MARKER = ".ground-control.yaml"
_CONTRACTS_DIRNAME = "contracts"

# Normative corpus families (mirror specs/authority/authority-boundary.yaml and
# ADR-019). Loaders reference these constants so the family names live in one
# place.
PROFILES = "profiles"
FIXTURES = "fixtures"
CONCEPT_AUTHORITY = "concept-authority"
SCHEMAS = "schemas"
REALIZATION_ENVELOPES = "realization-envelopes"
PROVENANCE = "provenance"


def _bundled_corpus_root() -> Path | None:
    """Return the packaged corpus root when the distribution bundles it.

    For an installed (unpacked) wheel/sdist the ``force-include`` lands the
    corpus at ``raes_contracts/_corpus``. ``importlib.resources.files`` returns
    a concrete filesystem path for such installs, which the corpus loaders need
    for directory traversal (``glob``). Returns ``None`` when the package ships
    without bundled data (the source/editable layout), so the caller can fall
    back to the in-repo authority.
    """

    try:
        candidate = resources.files(_CORPUS_PACKAGE).joinpath(_BUNDLED_DIRNAME)
        candidate_is_dir = candidate.is_dir()
    except ModuleNotFoundError, TypeError, OSError:
        return None
    if not candidate_is_dir:
        return None
    path = Path(str(candidate))
    return path if path.is_dir() else None


def _source_checkout_corpus_root() -> Path | None:
    """Return the in-repo ``contracts/`` authority for a source/editable checkout.

    Located by walking up to the repository marker (``.ground-control.yaml``)
    rather than a fragile ``Path(__file__).resolve().parents[N]`` index, so
    relocating this package within the source tree cannot silently break
    resolution. Returns ``None`` when no marked checkout is found above this
    module (the installed-distribution layout).
    """

    for parent in Path(__file__).resolve().parents:
        contracts = parent / _CONTRACTS_DIRNAME
        if contracts.is_dir() and (parent / _REPO_MARKER).is_file():
            return contracts
    return None


@cache
def corpus_root() -> Path:
    """Resolve the published contract-corpus root directory.

    Prefers the packaged corpus (the default for an installed distribution) and
    falls back to the in-repo ``contracts/`` authority for editable/source
    checkouts. Raises :class:`RuntimeError` when neither is present rather than
    returning an empty corpus, so a wheel built without the corpus payload fails
    loudly instead of letting conformance or semantic validation pass vacuously.
    """

    bundled = _bundled_corpus_root()
    if bundled is not None:
        return bundled
    source = _source_checkout_corpus_root()
    if source is not None:
        return source
    raise RuntimeError(
        "RAES contract corpus is unavailable: the installed distribution does "
        f"not bundle '{_CORPUS_PACKAGE}/{_BUNDLED_DIRNAME}' and no source "
        f"checkout ('{_REPO_MARKER}' + '{_CONTRACTS_DIRNAME}/') was found above "
        f"{__file__}. Reinstall a wheel built with the corpus force-include, or "
        "run from a source checkout."
    )


def corpus_family_root(family: str) -> Path:
    """Return the root directory of a normative corpus family.

    ``family`` is one of :data:`PROFILES`, :data:`FIXTURES`,
    :data:`CONCEPT_AUTHORITY`, :data:`PROVENANCE`, or :data:`SCHEMAS`.
    """

    return corpus_root() / family


__all__ = [
    "CONCEPT_AUTHORITY",
    "FIXTURES",
    "PROFILES",
    "PROVENANCE",
    "REALIZATION_ENVELOPES",
    "SCHEMAS",
    "corpus_family_root",
    "corpus_root",
]
