"""Compose the published participant-crossing facts from two admitted records only."""

from pathlib import Path

from raes_contracts.canonical import canonical_json_digest

from . import machine_check as machine
from . import reproduction_record
from .counterexample_corpus import decoded
from .export import digest


def _models(result: dict) -> dict:
    keys = (
        "model_id",
        "model_revision",
        "initial",
        "states",
        "semantic_transitions",
        "aut_transitions",
        "input_digest",
        "sidecar_digest",
    )
    return {name: {key: model[key] for key in keys} for name, model in result["models"].items()}


def _tool(manifest: dict) -> dict:
    tool = manifest["tool"]
    return {
        "artifact_id": tool["artifact_id"],
        "version": tool["version"],
        "archive_sha256": tool["raw"]["sha256"],
        "executable_sha256": tool["executable"]["sha256"],
        "installed_tree_sha256": tool["installed_tree"]["manifest_sha256"],
    }


def publication_facts(root: Path) -> dict:
    """Admit the pinned machine check and reproduction, then project their public facts."""
    bundle, subject = machine.load_retained(root)
    machine.admit_bundle(root, bundle, subject)
    record = reproduction_record.admit_record(root)
    manifest = decoded(bundle["manifest.json"])
    result = decoded(bundle["result.json"])
    mutations = decoded(bundle["mutation-results.json"])
    review = record["review"]
    verification = manifest["verification"]
    return {
        "schema": "participant-crossing-publication/v1",
        "relation": result["relation"],
        "taxonomy": result["claim"]["taxonomy_id"] + "@" + result["claim"]["taxonomy_revision"],
        "profile": result["profile"],
        "profile_digest": result["profile_digest"],
        "projection": result["projection"],
        "complete_reachable_fixed_point": result["complete_reachable_fixed_point"],
        "equivalent": result["equivalent"],
        "domain_counts": result["domain_counts"],
        "models": _models(result),
        "tool": _tool(manifest),
        "verification": {key: verification[key] for key in ("mode", "tau", "ordered_inputs")},
        "mutation_cases": {
            name: case["observed"]["dpbranching-bisim"] for name, case in sorted(mutations["cases"].items())
        },
        "machine_check": {
            "manifest_digest": subject,
            "result_digest": digest(bundle["result.json"]),
            "claim_digest": canonical_json_digest(result["claim"]),
            "corpus_manifest_digest": manifest["corpus_manifest_digest"],
            "mutation_review_subject_digest": manifest["mutation_review_subject_digest"],
            "authenticity": manifest["authenticity"],
            "claim_non_claims": result["non_claims"],
            "limitations": result["claim"]["limitations"],
        },
        "reproduction": {
            "manifest_digest": record["manifest_digest"],
            "measurement_digest": record["artifact_digests"]["measurement.json"],
            "execution_digest": record["artifact_digests"]["execution.json"],
            "review_digest": record["artifact_digests"]["review.json"],
            "decision": review["decision"],
            "reviewer_role": review["reviewer_role"],
            "producer_ref": review["producer_ref"],
            "reviewer_ref": review["reviewer_ref"],
            "acceptance_record_ref": review["acceptance_record_ref"],
            "qualified_run": review["qualified_run"]["url"],
            "qualified_artifact_digest": review["qualified_run"]["artifact_digest"],
            "source_revision": review["source_revision"],
            "authenticity": review["authenticity"],
            "nonclaims": review["nonclaims"],
        },
    }
