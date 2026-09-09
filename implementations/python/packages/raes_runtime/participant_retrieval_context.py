"""Context-view options and runtime-owned snapshot revision paths."""

from __future__ import annotations

from dataclasses import dataclass

from .control_plane_security import ParticipantAudienceSubjectBinding
from .participant_crossing_mediation import ParticipantCrossingEvidence


@dataclass(frozen=True)
class ContextViewOptions:
    """Validated optional fields for a participant context projection."""

    episode_id: str | None = None
    derivation_basis_ref: str | None = None
    payload_ref: str | None = None
    derived_from_refs: tuple[str, ...] = ()
    identity: object | None = None
    audience_binding: ParticipantAudienceSubjectBinding | None = None
    crossing_evidence: ParticipantCrossingEvidence | None = None
    idempotency_key: str = ""

    @classmethod
    def from_fields(cls, fields: dict[str, object]) -> ContextViewOptions:
        unknown = set(fields) - {
            "episode_id",
            "derivation_basis_ref",
            "payload_ref",
            "derived_from_refs",
            "identity",
            "audience_binding",
            "crossing_evidence",
            "idempotency_key",
        }
        if unknown:
            names = ", ".join(sorted(unknown))
            raise TypeError(f"unexpected participant context options: {names}")
        episode_id = _optional_string(fields.get("episode_id"), "episode_id")
        derivation_basis_ref = _optional_string(fields.get("derivation_basis_ref"), "derivation_basis_ref")
        payload_ref = _optional_string(fields.get("payload_ref"), "payload_ref")
        derived_from_refs = fields.get("derived_from_refs", ())
        idempotency_key = fields.get("idempotency_key", "")
        crossing_evidence = fields.get("crossing_evidence")
        audience_binding = fields.get("audience_binding")
        if not isinstance(derived_from_refs, tuple) or not all(isinstance(item, str) for item in derived_from_refs):
            raise TypeError("derived_from_refs must be a tuple of strings")
        if not isinstance(idempotency_key, str):
            raise TypeError("idempotency_key must be a string")
        if crossing_evidence is not None and not isinstance(crossing_evidence, ParticipantCrossingEvidence):
            raise TypeError("crossing_evidence must be ParticipantCrossingEvidence")
        if audience_binding is not None and not isinstance(audience_binding, ParticipantAudienceSubjectBinding):
            raise TypeError("audience_binding must be ParticipantAudienceSubjectBinding")
        return cls(
            episode_id=episode_id,
            derivation_basis_ref=derivation_basis_ref,
            payload_ref=payload_ref,
            derived_from_refs=derived_from_refs,
            identity=fields.get("identity"),
            audience_binding=audience_binding,
            crossing_evidence=crossing_evidence,
            idempotency_key=idempotency_key,
        )


def context_revision_paths(options: ContextViewOptions) -> tuple[tuple[str | int, ...], ...]:
    """Return fields whose revision references are supplied by the runtime."""

    paths: list[tuple[str | int, ...]] = []
    if not options.episode_id:
        paths.extend(
            (
                ("observation_point",),
                ("source_layers", 0, "observation_point"),
            )
        )
    if not options.derived_from_refs:
        paths.extend(
            (
                ("derived_from_refs", 0),
                ("source_layers", 0, "ref"),
                ("source_layers", 0, "evidence_refs", 0),
                ("source_layers", 0, "provenance_refs", 0),
                ("evidence_refs", 0),
                ("provenance_refs", 0),
            )
        )
    return tuple(paths)


def _optional_string(value: object, name: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{name} must be a string or None")
    return value
