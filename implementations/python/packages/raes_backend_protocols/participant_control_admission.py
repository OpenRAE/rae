"""API-424 adapter to the incumbent API-407 manifest support authority."""

from raes_contracts.contracts.participant_control_composition import control_digest
from raes_contracts.contracts.participant_control_results import ControlEffectiveSupportModel
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel

from .backend_manifest import BackendManifest
from .manifest import backend_manifest_v2_model
from .participant_feature_admission import resolve_participant_feature_support


def resolve_participant_control_support(manifest: BackendManifest, support: ControlEffectiveSupportModel) -> str:
    """Resolve an independently obtained manifest; never install or execute.

    The caller resolves manifest identity/revision through its trusted artifact
    store. This adapter checks exact content and delegates declared strength and
    conformance evidence to API-407. Effective support remains a separate check.
    """
    try:
        if control_digest(backend_manifest_v2_model(manifest)) != support.declaration_ref.digest:
            raise ValueError("manifest differs")
        if support.declared_level == "unsupported":
            entries = manifest.participant_runtime.feature_support if manifest.participant_runtime else ()
            if not any(
                entry.feature == support.feature and entry.support_level == ParticipantFeatureSupportLevel.UNSUPPORTED
                for entry in entries
            ):
                raise ValueError("unsupported declaration absent")
            return "unsupported"
        declaration = resolve_participant_feature_support(
            manifest, support.feature, required_level=ParticipantFeatureSupportLevel(support.declared_level)
        )
        if declaration is None or declaration.support_level.value != support.declared_level:
            raise ValueError("missing or different declaration")
        return declaration.support_level.value
    except Exception:
        raise ValueError("participant control manifest support is unresolved") from None
