"""Closed evidence construction for the single-operation finite decision."""

from pathlib import Path

from raes_contracts.behavioral_relation_profiles import BehavioralRelationProfileModel
from raes_contracts.behavioral_relations import validate_behavioral_claim_binding
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.base import BehavioralClaimBindingModel
from raes_contracts.errors import EvidenceIntegrityError

from . import counterexample_corpus as corpus
from . import export
from .aut import parse_aut
from .ingress import read_bytes

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = "specs/formal/participant-semantics/machine-check"
NONCLAIMS = [
    "unbounded-proof",
    "proof-certificate",
    "independent-reproduction",
    "runtime-realization",
    "backend-conformance",
    "noninterference",
    "opacity",
    "other-profiles-carriers-orders-times-probabilities-concurrency-controllers-policy-cuts-backends",
]
SOURCE_PATHS = tuple(
    sorted(
        {
            *corpus.SOURCE_PATHS,
            "implementations/formal/participant_crossing/machine_check.py",
            "implementations/formal/participant_crossing/machine_check_evidence.py",
            "implementations/formal/participant_crossing/machine_check_publication.py",
            "tools/bootstrap_profile.py",
            "tools/python_closure_profiles.py",
            "tools/nox_support/machine_check_lane.py",
            "implementations/python/pyproject.toml",
            "noxfile.py",
            export.PROFILE_PATH,
            corpus.OUTPUT_ROOT + "/pin.json",
            "specs/formal/participant-semantics/participant-crossing-machine-check.md",
            *(
                path.relative_to(ROOT).as_posix()
                for path in (ROOT / "implementations/python/packages/raes_contracts").rglob("*.py")
            ),
        }
    )
)


def source_pins(root: Path) -> dict[str, str]:
    return {path: export.digest(read_bytes(root, path)) for path in SOURCE_PATHS}


def inputs(root: Path):
    """Reproduce consumed model bytes, and admit the separately selected corpus."""
    current = export.build_bundle(root)
    retained, pin = corpus.load_retained(root)
    corpus.admit_bundle(root, retained, pin)
    for name in ("abstract.aut", "concrete.aut", "abstract.json", "concrete.json"):
        if retained[name] != current[name]:
            raise EvidenceIntegrityError("machine-check input drift")
    return current, retained, pin


def result(root: Path, equivalent: bool, model: dict[str, bytes], witness_digest: str | None) -> dict:
    if type(equivalent) is not bool:
        raise EvidenceIntegrityError("invalid machine-check decision type")
    profile = BehavioralRelationProfileModel.model_validate(corpus.decoded(read_bytes(root, export.PROFILE_PATH)))
    claim = None
    if equivalent:
        if witness_digest is not None:
            raise EvidenceIntegrityError("positive decision cannot carry a counterexample")
        claim = BehavioralClaimBindingModel(
            taxonomy_id=profile.taxonomy_id,
            taxonomy_revision=profile.taxonomy_revision,
            relation_id=profile.relation_id,
            subject="Declared initial states of the complete single-operation rev2 finite carrier",
            left_carrier_ref=profile.parameters.left.model_id,
            right_carrier_ref=profile.parameters.right.model_id,
            observation_projection_ref=profile.observation_projection_ref,
            observation_projection_revision=profile.observation_projection_revision,
            relation_parameter_profile_ref=profile.profile_id,
            relation_parameter_profile_revision=profile.profile_revision,
            quantifier_scope="all-admitted-inputs",
            evidence_scope="model-check",
            assurance_axis="model-check",
            assurance_status="model-checked",
            evidence_boundary="Only the complete reachable carrier of participant-crossing-dpbb-finite-v1@rev2.",
            evidence_refs=[export.digest(model[name]) for name in ("abstract.aut", "concrete.aut", "manifest.json")],
            limitations=[
                "One fresh operation with retries, sequential total order, untimed and nonprobabilistic.",
                "Singleton participant, audience, controller, episode and request; exact policy cuts p0 and p1.",
                "Native finite decision with no positive certificate or checked relation witness.",
            ],
            explicit_non_claims=NONCLAIMS,
        )
        validate_behavioral_claim_binding(claim, profile=profile)
    elif witness_digest is None:
        raise EvidenceIntegrityError("negative decision requires a checked counterexample")
    counts = {}
    identity = corpus.decoded(model["manifest.json"])
    for name in ("abstract", "concrete"):
        initial, states, edges = parse_aut(model[name + ".aut"])
        counts[name] = {
            "initial": initial,
            "states": states,
            "aut_transitions": len(edges),
            "semantic_transitions": identity["models"][name]["transitions"],
            "model_id": getattr(profile.parameters, "left" if name == "abstract" else "right").model_id,
            "model_revision": "rev2",
            "input_digest": export.digest(model[name + ".aut"]),
            "sidecar_digest": export.digest(model[name + ".json"]),
        }
    return {
        "schema": "participant-crossing-finite-decision/v1",
        "equivalent": equivalent,
        "relation": profile.relation_id,
        "profile": profile.profile_id + "@" + profile.profile_revision,
        "profile_digest": profile.canonical_digest,
        "projection": "participant-crossing-projection@rev1",
        "complete_reachable_fixed_point": True,
        "domain_counts": identity["domain_counts"],
        "models": counts,
        "claim": claim.model_dump(mode="json") if claim else None,
        "counterexample": {
            "kind": "checked-auxiliary-branching-bisim-formula",
            "digest": witness_digest,
        }
        if witness_digest
        else None,
        "non_claims": NONCLAIMS,
    }


def manifest(
    root: Path,
    bundle: dict[str, bytes],
    model: dict[str, bytes],
    retained: dict[str, bytes],
    pin: str,
) -> dict:
    identities = source_pins(root)
    corpus_manifest = corpus.decoded(retained["manifest.json"])
    return {
        "schema": "participant-crossing-machine-check/v1",
        "source_digests": identities,
        "source_identity": canonical_json_digest(identities),
        "model_manifest_digest": export.digest(model["manifest.json"]),
        "retained_model_manifest_digest": corpus_manifest["baseline_manifest_digest"],
        "historical_baseline_source_drift": corpus_manifest["historical_baseline_source_drift"],
        "corpus_manifest_digest": pin,
        "mutation_review_subject_digest": corpus_manifest["review_subject_digest"],
        "mapping": corpus_manifest["mapping"],
        "tool": corpus_manifest["tool"],
        "verification": {
            "mode": "dpbranching-bisim",
            "tau": ["internal"],
            "arguments": [
                "--equivalence=dpbranching-bisim",
                "--tau=internal",
                "--in1=aut",
                "--in2=aut",
            ],
            "ordered_inputs": ["abstract.aut", "concrete.aut"],
            "native_argv": [
                "/opt/mcrl2/usr/bin/ltscompare",
                "--equivalence=dpbranching-bisim",
                "--tau=internal",
                "--in1=aut",
                "--in2=aut",
                "/input/left.aut",
                "/input/right.aut",
            ],
            "offline": True,
            "shell": False,
            "max_comparisons": 47,
            "producer_wall_seconds": 2160,
        },
        "artifact_digests": {name: export.digest(value) for name, value in bundle.items() if name != "manifest.json"},
        "authenticity": "unsigned",
        "trust_role": "evidence_artifact",
    }
