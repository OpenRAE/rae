"""Stateless reference engine for the EXP-718 ``blake3-xof-v1`` random-stream profile.

Pure functions only: no module-level mutable state, no class holding a
cursor. Every operation takes an explicit profile id, complete semantic
address, and transform parameters, and returns a value plus bounded
provenance (rejection attempt count / exhaustion flag) -- never a
process-global RNG, worker-local singleton, or cursor-style ``next()``.

Construction, verbatim from ``docs/decisions/issue-274-exp-718-controlled-randomness-preflight.md``
and the implementation plan:

* ``stream_key = blake3.derive_key(context=f"raes-random-stream-v1|profile={profile_id}",
  key_material=root_entropy_bytes)`` -- one call per (profile, root entropy)
  pair; pure function, no shared state. (This binding's Python API exposes
  the same key-derivation mode via ``blake3.blake3(derive_key_context=...)``.)
* ``address_bytes = canonical_jcs_bytes(StreamAddressModel)`` via the RFC
  8785/JCS canonical-bytes pattern (``raes/canonical.py``).
* ``block = blake3.blake3(address_bytes, key=stream_key).digest(length=BLOCK_BYTES,
  seek=local_coordinate * BLOCK_BYTES)``.
* Bounded-integer transforms consume the block via rejection sampling
  (widening via additional ``seek`` on insufficient entropy), never modulo
  bias, recording ``rejection_attempts`` and enforcing a bounded max-attempt
  budget: deterministic exhaustion failure, never fallback or clamping.

Only the published ``blake3-xof-v1`` and ``blake3-xof-participant-v1``
profile ids are dispatched. An unknown/unsupported profile id fails closed
(``ValueError``) rather than falling back to a library default or a dynamic
plugin lookup.
"""

from __future__ import annotations

from dataclasses import dataclass

import blake3
import rfc8785

from .contracts.experiment_allocation import AllocationStreamAddressModel
from .contracts.random_stream import ParticipantStreamAddressModel, PublicSeedModel, StreamAddressModel
from .diagnostics import Diagnostic, Severity
from .random_stream_profiles import SUPPORTED_RANDOM_STREAM_PROFILE_IDS

_DIAGNOSTIC_DOMAIN = "random-stream"

#: Raw-block byte length fixed by the ``blake3-xof-v1`` profile.
BLOCK_BYTES = 32

#: Root-entropy byte length fixed by the ``blake3-xof-v1`` profile (matches
#: BLAKE3's 32-byte key size).
ROOT_ENTROPY_BYTE_LENGTH = 32

#: Key-derivation domain-separation context template fixed by the
#: ``blake3-xof-v1`` profile. ``{profile_id}`` is substituted with the exact
#: requested profile id -- changing this template mints a new profile id.
DERIVATION_CONTEXT_TEMPLATE = "raes-random-stream-v1|profile={profile_id}"

BOUNDED_INTEGER_TRANSFORM_ID = "bounded-integer"
BOUNDED_INTEGER_TRANSFORM_VERSION = "1"


def _require_supported_profile(profile_id: str) -> None:
    if profile_id not in SUPPORTED_RANDOM_STREAM_PROFILE_IDS:
        supported = ", ".join(sorted(SUPPORTED_RANDOM_STREAM_PROFILE_IDS))
        raise ValueError(f"unsupported random stream profile id {profile_id!r}; supported ids: {supported}")


def decode_public_seed(seed: PublicSeedModel) -> bytes:
    """Decode an inline public seed to raw bytes, failing closed on a bad encoding/length."""

    if seed.encoding != "hex-fixed-width":
        raise ValueError(f"unsupported public seed encoding {seed.encoding!r}; expected 'hex-fixed-width'")
    raw = bytes.fromhex(seed.value)
    if len(raw) != ROOT_ENTROPY_BYTE_LENGTH:
        raise ValueError(f"public seed must decode to exactly {ROOT_ENTROPY_BYTE_LENGTH} bytes; got {len(raw)}")
    return raw


def derive_stream_key(*, profile_id: str, root_entropy: bytes) -> bytes:
    """Derive the profile-scoped stream key from root entropy (pure function, no shared state)."""

    _require_supported_profile(profile_id)
    if len(root_entropy) != ROOT_ENTROPY_BYTE_LENGTH:
        raise ValueError(f"root entropy must be exactly {ROOT_ENTROPY_BYTE_LENGTH} bytes; got {len(root_entropy)}")
    context = DERIVATION_CONTEXT_TEMPLATE.format(profile_id=profile_id)
    hasher = blake3.blake3(derive_key_context=context)
    hasher.update(root_entropy)
    return hasher.digest()


def canonical_stream_address_bytes(
    address: StreamAddressModel | ParticipantStreamAddressModel | AllocationStreamAddressModel,
) -> bytes:
    """Return the RFC 8785/JCS canonical bytes for one closed ``StreamAddressModel``.

    Uses ``exclude_none=True`` rather than ``exclude_unset=True``: the
    canonical encoding must be a pure function of the *logical* address
    content (which optional trial-coordinate dimensions are populated),
    independent of whether a caller explicitly passed an unset field as
    ``None`` versus omitting it -- two constructions of the same logical
    address must always canonicalize to identical bytes (SVR-013).
    """

    payload = address.model_dump(mode="json", by_alias=True, exclude_none=True)
    try:
        return rfc8785.dumps(payload)
    except rfc8785.CanonicalizationError as exc:
        raise ValueError(f"stream address canonicalization failed: {exc}") from exc


def raw_block(
    *,
    profile_id: str,
    stream_key: bytes,
    address: StreamAddressModel | ParticipantStreamAddressModel | AllocationStreamAddressModel,
    byte_length: int = BLOCK_BYTES,
    byte_offset: int = 0,
) -> bytes:
    """Return ``byte_length`` raw XOF bytes at ``byte_offset`` within ``address``'s block window.

    True random access: no cursor, no recomputation of prior bytes. Calling
    this repeatedly with different ``byte_offset`` values (rejection-sampling
    widening) or in any order/parallelism yields byte-identical results for
    the same inputs (SVR-014 schedule independence).
    """

    _require_supported_profile(profile_id)
    if byte_length < 1:
        raise ValueError("raw_block byte_length must be positive")
    if byte_offset < 0:
        raise ValueError("raw_block byte_offset must be non-negative")
    address_bytes = canonical_stream_address_bytes(address)
    seek = address.local_coordinate * BLOCK_BYTES + byte_offset
    return blake3.blake3(address_bytes, key=stream_key).digest(length=byte_length, seek=seek)


@dataclass(frozen=True)
class BoundedIntegerDraw:
    """Outcome of one bounded-integer rejection-sampling draw."""

    value: int | None
    rejection_attempts: int
    rejection_exhausted: bool


def _bounded_integer_byte_width(width: int) -> int:
    byte_width = 1
    while 256**byte_width < width:
        byte_width += 1
    return byte_width


def draw_bounded_integer(
    *,
    profile_id: str,
    stream_key: bytes,
    address: StreamAddressModel | ParticipantStreamAddressModel | AllocationStreamAddressModel,
    minimum: int,
    maximum: int,
    max_rejection_attempts: int,
) -> BoundedIntegerDraw:
    """Draw an unbiased integer in ``[minimum, maximum]`` via rejection sampling.

    Never uses modulo bias directly on an unfiltered raw value: the widest
    multiple of the range ``width`` that fits the sampled byte-width is
    computed as the acceptance ceiling (``limit``), and any raw value at or
    above ``limit`` is rejected and re-sampled from the next block offset
    (widening the consumed entropy via ``seek``, never recomputing prior
    bytes). Exhaustion after ``max_rejection_attempts`` attempts is a
    deterministic failure (``rejection_exhausted=True``, ``value=None``),
    never a fallback, clamp, or unrecorded resample.
    """

    _require_supported_profile(profile_id)
    if maximum < minimum:
        raise ValueError("draw_bounded_integer requires maximum >= minimum")
    if max_rejection_attempts < 1:
        raise ValueError("draw_bounded_integer requires max_rejection_attempts >= 1")
    width = maximum - minimum + 1
    byte_width = _bounded_integer_byte_width(width)
    ceiling = 256**byte_width
    limit = ceiling - (ceiling % width)
    for attempt_index in range(max_rejection_attempts):
        chunk = raw_block(
            profile_id=profile_id,
            stream_key=stream_key,
            address=address,
            byte_length=byte_width,
            byte_offset=attempt_index * byte_width,
        )
        raw_int = int.from_bytes(chunk, "big")
        if raw_int < limit:
            return BoundedIntegerDraw(
                value=minimum + raw_int % width,
                rejection_attempts=attempt_index,
                rejection_exhausted=False,
            )
    return BoundedIntegerDraw(value=None, rejection_attempts=max_rejection_attempts, rejection_exhausted=True)


@dataclass(frozen=True)
class BoundedIntegerDrawRequest:
    """One member of a bounded-integer batch-draw operation."""

    address: StreamAddressModel
    minimum: int
    maximum: int
    max_rejection_attempts: int


@dataclass(frozen=True)
class BoundedIntegerBatchResult:
    """Result of one bounded batch-draw operation: exactly one of the two fields is set.

    A collision anywhere in the batch yields no partial result -- ``draws``
    stays ``None`` even for the requests that did not collide (EXP-718
    preflight: "detect ... report a deterministic collision diagnostic and
    emit no partial result").
    """

    draws: tuple[BoundedIntegerDraw, ...] | None
    diagnostic: Diagnostic | None


def _semantic_coordinate_key(address: StreamAddressModel) -> tuple[object, ...]:
    coordinate = address.trial_coordinate
    return (
        address.namespace,
        coordinate.condition_id,
        coordinate.block_id,
        coordinate.replicate_id,
        address.selection_policy_id,
        address.variation_point_id,
        address.draw_purpose,
        address.local_coordinate,
    )


def _batch_collision_diagnostic(*, duplicate_semantic_count: int, duplicate_address_bytes_count: int) -> Diagnostic:
    return Diagnostic(
        code="random-stream.batch-draw-address-collision",
        domain=_DIAGNOSTIC_DOMAIN,
        address="",
        message=(
            f"batch draw detected {duplicate_semantic_count} duplicate semantic coordinate(s) and "
            f"{duplicate_address_bytes_count} duplicate canonical address byte string(s); "
            "no draws were produced for this batch"
        ),
        severity=Severity.ERROR,
    )


def draw_bounded_integer_batch(
    *,
    profile_id: str,
    stream_key: bytes,
    requests: list[BoundedIntegerDrawRequest],
) -> BoundedIntegerBatchResult:
    """Draw a batch of bounded integers as one bounded collision-checked operation.

    Detects duplicate semantic coordinates and duplicate canonical address
    bytes among the requested addresses before drawing anything. On
    collision, returns a deterministic ``Diagnostic`` and no draws (not the
    non-colliding subset). The check is independent of request order, so
    repeated or reordered calls over the same request set are byte-identical
    (SVR-014 schedule independence extended to collision reporting).
    """

    _require_supported_profile(profile_id)
    seen_semantic: set[tuple[object, ...]] = set()
    duplicate_semantic_count = 0
    seen_address_bytes: set[bytes] = set()
    duplicate_address_bytes_count = 0
    for request in requests:
        semantic_key = _semantic_coordinate_key(request.address)
        if semantic_key in seen_semantic:
            duplicate_semantic_count += 1
        seen_semantic.add(semantic_key)
        address_bytes = canonical_stream_address_bytes(request.address)
        if address_bytes in seen_address_bytes:
            duplicate_address_bytes_count += 1
        seen_address_bytes.add(address_bytes)
    if duplicate_semantic_count or duplicate_address_bytes_count:
        return BoundedIntegerBatchResult(
            draws=None,
            diagnostic=_batch_collision_diagnostic(
                duplicate_semantic_count=duplicate_semantic_count,
                duplicate_address_bytes_count=duplicate_address_bytes_count,
            ),
        )
    draws = tuple(
        draw_bounded_integer(
            profile_id=profile_id,
            stream_key=stream_key,
            address=request.address,
            minimum=request.minimum,
            maximum=request.maximum,
            max_rejection_attempts=request.max_rejection_attempts,
        )
        for request in requests
    )
    return BoundedIntegerBatchResult(draws=draws, diagnostic=None)


__all__ = [
    "BLOCK_BYTES",
    "BOUNDED_INTEGER_TRANSFORM_ID",
    "BOUNDED_INTEGER_TRANSFORM_VERSION",
    "DERIVATION_CONTEXT_TEMPLATE",
    "ROOT_ENTROPY_BYTE_LENGTH",
    "BoundedIntegerBatchResult",
    "BoundedIntegerDraw",
    "BoundedIntegerDrawRequest",
    "canonical_stream_address_bytes",
    "decode_public_seed",
    "derive_stream_key",
    "draw_bounded_integer",
    "draw_bounded_integer_batch",
    "raw_block",
]
