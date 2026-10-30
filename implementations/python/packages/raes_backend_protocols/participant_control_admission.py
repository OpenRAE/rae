"""API-424 adapter to the incumbent API-407 manifest support authority."""

from pydantic import ValidationError
from raes_contracts.contracts.participant_control_composition import control_digest
from raes_contracts.contracts.participant_control_results import ControlEffectiveSupportModel
from raes_contracts.errors import ConflictError
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel
from rfc8785 import CanonicalizationError

from .backend_manifest import BackendManifest
from .manifest import backend_manifest_v2_model
from .participant_feature_admission import resolve_participant_feature_support

_UNRESOLVED = "participant control manifest support is unresolved"


def resolve_participant_control_support(manifest: BackendManifest, support: ControlEffectiveSupportModel) -> str:
    """Resolve an independently obtained manifest; never install or execute.

    The caller resolves manifest identity/revision through its trusted artifact
    store. This adapter checks exact content and delegates declared strength and
    conformance evidence to API-407. Effective support remains a separate check.
    Each refusal raises ``ConflictError`` with one fixed message that does not
    identify the failed check or contain manifest values.
    """
    try:
        declaration_digest = control_digest(backend_manifest_v2_model(manifest))
    except ValidationError, CanonicalizationError:
        # A manifest without a backend-manifest-v2 form, or whose values have no RFC 8785 form,
        # cannot match the referenced declaration digest.
        raise ConflictError(_UNRESOLVED) from None
    if declaration_digest != support.declaration_ref.digest:
        raise ConflictError(_UNRESOLVED)
    if support.declared_level == "unsupported":
        entries = manifest.participant_runtime.feature_support if manifest.participant_runtime else ()
        if not any(
            entry.feature == support.feature and entry.support_level == ParticipantFeatureSupportLevel.UNSUPPORTED
            for entry in entries
        ):
            raise ConflictError(_UNRESOLVED)
        return "unsupported"
    try:
        declaration = resolve_participant_feature_support(
            manifest, support.feature, required_level=ParticipantFeatureSupportLevel(support.declared_level)
        )
    except ConflictError:
        raise ConflictError(_UNRESOLVED) from None
    if declaration is None or declaration.support_level.value != support.declared_level:
        raise ConflictError(_UNRESOLVED)
    return declaration.support_level.value
