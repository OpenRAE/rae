"""RUN-320 effect claims: who an effect acts for, and what became of it.

PC-09/PC-11 separate an effect from the evaluation that admitted it: the parent
commits its intent, and each effect is dispatched afterwards as its own
operation. That split must not change *whose* effect it is. The principal of
an effect is the principal of the committed operation that admitted it, so:

* the originating operation is the one whose committed transition appended the
  evaluation — the ADR-104 record already names it as its result history head;
* every effect is claimed durably, before any owner is invoked, under a context
  that retains that operation's actor, authorization scope, target and run, and
  names it as ``parent_operation_id``;
* the effect is submitted to its owner *as* that principal, restricted to its
  bindings for this participant, so the owner's own rules decide and a
  principal can never cause an effect it could not itself perform;
* the caller that drains effects is authorized separately, before anything
  committed is read, and may request execution without becoming the principal.

The claim is what makes outcomes trustworthy. It is keyed by the logical effect
key under the originating actor, so every drain resolves the same claim and
none can execute an effect twice, and the store's own replay validation binds
it to this effect's content, so an unrelated record can never answer for it.
Nothing that depends on the drain caller is ever persisted as an outcome: an
owner's refusal is a refusal of the fixed originating principal, which every
drain would meet identically, and a withhold or unsupported owner is recomputed
on each drain rather than recorded.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.participant_control_coordinates import ControlArtifactReferenceModel
from raes_contracts.contracts.participant_control_effects import ControlEffectRequestModel
from raes_contracts.contracts.participant_control_results import ControlRealizationBindingModel
from raes_contracts.operation_lifecycle import OperationAdmissionContext
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import (
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
)

from .control_plane_execution import _utc_now
from .control_plane_security import (
    ControlPlaneIdentity,
    ControlPlaneRole,
    ParticipantAudienceSubjectBinding,
    ParticipantControlSubjectBinding,
)
from .control_plane_store import (
    IDEMPOTENCY_CLAIM_CONFLICT,
    ControlPlaneOperationRecord,
    idempotency_claim_identity,
)

_APPLIED = "applied"
_FAILED = "failed"
_INDETERMINATE = "indeterminate"
_CARRIER = "participant_control_evaluation_history"
_TERMINAL_DISPOSITIONS = {OperationState.SUCCEEDED: _APPLIED, OperationState.FAILED: _FAILED}
_KNOWN_ROLES = frozenset(role.value for role in ControlPlaneRole)

# The incumbent owner of each closed effect kind records its own operation
# under its own kind: a participant-directed inject through the RUN-319
# delivery crossing, a handoff through the RUN-310 supervisory control path.
_OWNER_OPERATION_KINDS = {
    "inject": OperationKind.PARTICIPANT_CROSSING,
    "handoff": OperationKind.PARTICIPANT_CONTROL,
}


@dataclass(frozen=True)
class EffectClaim:
    """This effect's durable claim, and whether this drain just created it."""

    record: ControlPlaneOperationRecord
    fresh: bool


def require_drain_authority(control_plane: object, participant_address: str, identity: object) -> None:
    """Authorize the drain caller before any committed state is read.

    The same gate every incumbent participant mutation applies: an
    authenticated principal with a mutating role, bound to this target and to
    this participant as a controller or an audience. Draining is a request to
    execute effects that are already admitted, so it needs no authority over
    the effects themselves.
    """

    reason = _drain_refusal(control_plane, participant_address, identity)
    # The request is audited under the caller's own identity either way; the
    # effects it drains are attributed to their originating principals.
    control_plane.record_audit(
        action="dispatch_participant_control_effects",
        identity=getattr(identity, "identity", "anonymous"),
        allowed=reason is None,
        target=participant_address,
        reason=reason or "authorized",
    )
    if reason is not None:
        raise PermissionError("participant control effect dispatch is not authorized: " + reason)


def _drain_refusal(control_plane: object, participant_address: str, identity: object) -> str | None:
    if not isinstance(identity, ControlPlaneIdentity):
        return "unauthenticated"
    if identity.target_name is not None and identity.target_name != control_plane.target_name:
        return "target-forbidden"
    if identity.roles.isdisjoint({ControlPlaneRole.BACKEND, ControlPlaneRole.OPERATOR}):
        return "caller-forbidden"
    bound = any(
        binding.participant_address == participant_address for binding in identity.participant_control_subjects
    ) or any(binding.participant_address == participant_address for binding in identity.participant_audience_subjects)
    return None if bound else "participant-forbidden"


def originating_operations(control_plane: object, participant_address: str) -> dict[str, ControlPlaneOperationRecord]:
    """Map each committed evaluation to the operation whose transition appended it.

    A record names the history head it produced; only the record whose
    transition *moved* the head to an evaluation appended it. A later record
    that left the head unchanged names the same value on both sides.
    """

    key = f"{_CARRIER}:{participant_address}"
    origins: dict[str, ControlPlaneOperationRecord] = {}
    for record in control_plane._store.load_records().values():
        produced = record.result_history_heads.get(key)
        if produced is not None and record.decision_history_heads.get(key) != produced:
            origins[produced] = record
    return origins


def origin_principal(
    control_plane: object,
    origin: ControlPlaneOperationRecord,
    participant_address: str,
) -> ControlPlaneIdentity:
    """The originating principal, restricted to its authority over this participant.

    The parent's admission context durably records the actor and the exact
    role, control and audience scopes it was admitted with. Only this
    participant's bindings are carried: the scope prefix names the participant
    address, which cannot contain ``:``, so the remainder is exactly the bound
    controller or audience. Every governed crossing requires an authenticated
    identity, so an origin always reconstructs as one; an origin that somehow
    carries no binding simply holds no authority, and its owner refuses it.
    """

    context = origin.status.context
    control_prefix = f"participant-control:{participant_address}:"
    audience_prefix = f"participant-audience:{participant_address}:"
    roles = frozenset(
        ControlPlaneRole(scope.removeprefix("role:"))
        for scope in context.authorization_scope
        if scope.startswith("role:") and scope.removeprefix("role:") in _KNOWN_ROLES
    )
    return ControlPlaneIdentity(
        identity=context.actor_id,
        roles=roles,
        target_name=control_plane.target_name,
        participant_control_subjects=tuple(
            ParticipantControlSubjectBinding(participant_address, scope.removeprefix(control_prefix))
            for scope in context.authorization_scope
            if scope.startswith(control_prefix)
        ),
        participant_audience_subjects=tuple(
            ParticipantAudienceSubjectBinding(participant_address, scope.removeprefix(audience_prefix))
            for scope in context.authorization_scope
            if scope.startswith(audience_prefix)
        ),
    )


def effect_idempotency_key(request: ControlEffectRequestModel) -> str:
    """Scope the claim to the logical effect key, never to an attempt."""

    return f"control-effect:{canonical_json_digest(request.key.model_dump(mode='json'))}"


def owner_idempotency_key(claim: ControlPlaneOperationRecord) -> str:
    """The owner submission key, derived from this effect's own claim.

    The claim's operation identity is minted inside the drain's held mutation,
    so nothing can hold this key before the owner is invoked. The key is not a
    secret, though: a record only answers for the effect when it also lies in
    the owner's claim scope, which ``owner_record`` requires.
    """

    return f"control-effect-owner:{claim.receipt.operation_id}"


def claim_effect(
    control_plane: object,
    origin: ControlPlaneOperationRecord,
    request: ControlEffectRequestModel,
) -> EffectClaim | None:
    """Claim this effect for its originating principal, or ``None`` on conflict.

    The claim retains the origin's actor and scopes and names it as parent, so
    its claim identity — ``(actor, operation kind, key)`` — is the same for
    every drain. The request commitment binds it to this effect's content, so
    the store's own replay validation refuses a different request under the
    same key rather than returning it.
    """

    context = OperationAdmissionContext.model_validate(
        {
            **origin.status.context.model_dump(mode="python"),
            "operation_kind": OperationKind.PARTICIPANT_CONTROL,
            "request_commitment": canonical_json_digest(
                {"domain": "participant-control-effect/v1", "effect": request.model_dump(mode="json")}
            ),
            "parent_operation_id": origin.receipt.operation_id,
        }
    )
    operation_id = str(uuid4())
    timestamp = _utc_now()
    record = ControlPlaneOperationRecord(
        receipt=OperationReceipt(
            operation_id=operation_id,
            domain=RuntimeDomain.PARTICIPANT,
            submitted_at=timestamp,
            accepted=True,
            context=context,
        ),
        status=OperationStatus(
            operation_id=operation_id,
            domain=RuntimeDomain.PARTICIPANT,
            state=OperationState.RUNNING,
            submitted_at=timestamp,
            updated_at=timestamp,
            context=context,
        ),
        request_fingerprint=context.request_commitment,
        idempotency_key=effect_idempotency_key(request),
    )
    try:
        claimed = control_plane._claim_record(record)
    except ValueError as error:
        if str(error) == IDEMPOTENCY_CLAIM_CONFLICT:
            return None
        raise
    return EffectClaim(record=claimed, fresh=claimed.receipt.operation_id == operation_id)


def owner_record(
    control_plane: object,
    claim: ControlPlaneOperationRecord,
    request: ControlEffectRequestModel,
) -> ControlPlaneOperationRecord | None:
    """The owner operation this claim's dispatch submitted, if it exists.

    Resolved inside the owner's own claim scope — ``(actor, operation kind,
    key)`` — exactly as the store would replay it. The owner is always
    submitted as the originating principal, so its actor is the claim's actor:
    a record another actor files under this key, however it learned the key,
    is outside that scope and can never answer for the effect.
    """

    kind = _OWNER_OPERATION_KINDS.get(request.target.kind)
    if kind is None:
        return None
    key = owner_idempotency_key(claim)
    scope = (claim.status.context.actor_id, kind, key)
    return next(
        (
            record
            for record in control_plane._store.load_records().values()
            if record.idempotency_key == key and idempotency_claim_identity(record.receipt.context, key) == scope
        ),
        None,
    )


def claim_outcome(
    control_plane: object,
    claim: ControlPlaneOperationRecord,
    request: ControlEffectRequestModel,
) -> str:
    """Classify an effect from its own claim, falling back to its owner's record.

    A terminal claim is the answer. A claim left open — dispatch may have begun
    before an interruption — is resolved by the owner operation it submitted,
    which only this claim's dispatch could have created; with no terminal owner
    record either, the outcome stays uncertain and repeats nothing.
    """

    state = claim.status.state
    if state in _TERMINAL_DISPOSITIONS:
        return _TERMINAL_DISPOSITIONS[state]
    owner = owner_record(control_plane, claim, request)
    if owner is not None and owner.status.state in _TERMINAL_DISPOSITIONS:
        return _TERMINAL_DISPOSITIONS[owner.status.state]
    return _INDETERMINATE


def never_dispatched(
    control_plane: object,
    claim: ControlPlaneOperationRecord,
    request: ControlEffectRequestModel,
) -> bool:
    """Is there durable proof that this claimed effect's dispatch never began?

    PC-11 lets a committed-but-undispatched key resume only on such proof. Both
    owners claim their operation write-ahead, under a key only this claim
    derives, before they act — so an unsettled claim with no owner record,
    observed under the drain's held mutation, proves no submission ever
    started. Anything else may have begun and is never repeated.
    """

    unsettled = claim.status.state in {OperationState.RUNNING, OperationState.INDETERMINATE}
    return unsettled and owner_record(control_plane, claim, request) is None


def realization(
    request: ControlEffectRequestModel,
    disposition: str,
    receipt_ref: str,
) -> ControlRealizationBindingModel:
    return ControlRealizationBindingModel(
        effect_id=request.effect_id,
        disposition=disposition,
        receipt=ControlArtifactReferenceModel(
            kind="receipt",
            ref=receipt_ref,
            revision="rev1",
            digest=canonical_json_digest({"effect_id": request.effect_id, "disposition": disposition}),
        ),
        evidence=(request.evidence[0],),
    )


__all__ = (
    "EffectClaim",
    "claim_effect",
    "claim_outcome",
    "effect_idempotency_key",
    "never_dispatched",
    "origin_principal",
    "originating_operations",
    "owner_idempotency_key",
    "owner_record",
    "realization",
    "require_drain_authority",
)
