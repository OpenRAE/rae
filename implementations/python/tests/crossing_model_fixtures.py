"""Synthetic complete profile and malformed variants for issue 971."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def profile_payload():
    return {
        "schema_version": "behavioral-relation-profile/v1",
        "profile_id": "participant-crossing-dpbb-finite-v1",
        "profile_revision": "rev2",
        "taxonomy_id": "raes-behavioral-relations",
        "taxonomy_revision": "rev8",
        "relation_id": "divergence-preserving-branching-bisimulation",
        "left_carrier_ref": "sem-230-participant-crossing-abstract",
        "observation_projection_ref": "participant-crossing-projection",
        "observation_projection_revision": "rev1",
        "finite_analysis_scope": "declared-complete-finite-carrier",
        "parameters": {
            "kind": "participant-crossing-dpbb/v1",
            "domains": {
                "participant": ["participant-0"],
                "audience": ["audience-0"],
                "controller": ["controller-0"],
                "episode": ["episode-0"],
                "request_id": ["request-0"],
                "policy_cut": ["p0", "p1"],
                "input_class": ["plain", "transform", "declassify", "unsupported", "forbidden"],
                "decision": ["none", "permit", "deny", "unsupported", "transform", "declassify"],
                "replay": ["fresh", "same-cut", "later-cut"],
                "delivery": ["none", "pending", "delivered", "withheld"],
                "history_head": ["h0", "h1", "h2", "h3"],
            },
            "left": {
                "model_id": "sem-230-participant-crossing-abstract",
                "revision": "rev2",
                "source_path": "implementations/formal/participant_crossing/abstract.py",
                "source_digest": "sha256:" + "a" * 64,
                "initial_state_ordinal": 0,
            },
            "right": {
                "model_id": "api-423-run-319-crossing-kernel",
                "revision": "rev2",
                "source_path": "implementations/formal/participant_crossing/concrete.py",
                "source_digest": "sha256:" + "b" * 64,
                "initial_state_ordinal": 0,
            },
            "visible_labels": [
                "crossing.request",
                "crossing.decision.permit",
                "crossing.decision.deny",
                "crossing.decision.unsupported",
                "crossing.transform",
                "crossing.declassify",
                "crossing.delivery",
                "crossing.observation",
                "crossing.replay.reject",
                "policy.cut.advance",
            ],
            "hidden_labels": [
                "internal.validate",
                "internal.resolve-policy-cut",
                "internal.resolve-capability",
                "internal.prepare-record",
                "internal.atomic-commit",
            ],
            "checker_tau": "internal",
            "complete_carrier": True,
            "depth_or_sample_bound": None,
            "fresh_operations": 1,
            "identity_reuse": "excluded",
            "order": "sequential-total-order",
            "time": "untimed",
            "probability": "excluded",
            "concurrency": "excluded",
            "controller_handoff": "excluded",
            "completion": "per-crossing-visible-outcome",
        },
        "source_refs": [
            {
                "source_ref": "specs/formal/participant-semantics/participant-crossing-models.md",
                "source_digest": "sha256:" + "c" * 64,
            }
        ],
        "limitations": ["One fresh operation and retries; no identity recycling."],
        "explicit_non_claims": ["No equivalence or live-runtime result is established by construction."],
    }
