#!/usr/bin/env python3
"""Validate the REV1 scientific-scenario completeness claim contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from pydantic import ValidationError  # noqa: E402
from raes_conformance.conformance import validate_contract_payload  # noqa: E402
from raes_contracts.errors import InvalidInputError  # noqa: E402
from raes_contracts.operational_logging import run_application  # noqa: E402
from raes_contracts.scientific_completeness import (  # noqa: E402
    DeliveryStatus,
    ProfileCompletenessResult,
    ScientificCompletenessAssessmentModel,
    ScientificCompletenessTaxonomyModel,
    evaluate_profile_completeness,
    load_scientific_completeness_assessment,
    load_scientific_completeness_taxonomy,
)

from tools.check_schema_publication import load_schema_publication_catalog  # noqa: E402
from tools.policy.common import PolicyFailure, safe_repo_path  # noqa: E402

_EXPECTED_PROFILE_IDS = {
    "valid-sdl-fragment",
    "deployable-scenario-intent",
    "participant-evaluation-scenario",
    "controlled-experiment-scenario",
    "reproducible-benchmark-study-input",
}
_REQUIRED_NON_CLAIM_TERMS = {
    "backend conformance",
    "behavioral equivalence",
    "deployability",
    "reproducibility",
}
_SUMMARY_START = "<!-- scientific-completeness-summary:start -->"
_SUMMARY_END = "<!-- scientific-completeness-summary:end -->"


def _render_summary(outcomes: tuple[ProfileCompletenessResult, ...]) -> str:
    lines = [
        _SUMMARY_START,
        "| Profile | Complete | Blocking required concerns |",
        "| --- | --- | --- |",
    ]
    for outcome in outcomes:
        blockers = (
            ", ".join(f"`{concern_id}`" for concern_id in outcome.blocking_concerns)
            if outcome.blocking_concerns
            else "none"
        )
        lines.append(f"| `{outcome.profile_id}` | {'yes' if outcome.complete else 'no'} | {blockers} |")
    lines.append(_SUMMARY_END)
    return "\n".join(lines)


def _validate_profile_set(
    taxonomy: ScientificCompletenessTaxonomyModel,
) -> list[PolicyFailure]:
    profile_ids = {profile.profile_id for profile in taxonomy.profiles}
    if profile_ids == _EXPECTED_PROFILE_IDS:
        return []
    return [
        PolicyFailure(
            "scientific-completeness-profile-set",
            f"REV1 profiles must exactly match {sorted(_EXPECTED_PROFILE_IDS)}; got {sorted(profile_ids)}",
        )
    ]


def _validate_evidence_paths(
    repo_root: Path,
    assessment: ScientificCompletenessAssessmentModel,
) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for item in assessment.concerns:
        for evidence in item.evidence:
            resolved = safe_repo_path(repo_root, evidence.path)
            if resolved is None or not resolved.is_file():
                failures.append(
                    PolicyFailure(
                        "scientific-completeness-evidence-missing",
                        f"concern {item.concern_id!r} evidence path is missing or escapes the repository",
                        evidence.path,
                    )
                )
        for contract_id, witness_ref in item.satisfiability_witness_refs.items():
            resolved = safe_repo_path(repo_root, witness_ref)
            if resolved is None or not resolved.is_file():
                failures.append(
                    PolicyFailure(
                        "scientific-completeness-witness-missing",
                        f"concern {item.concern_id!r} satisfiability witness is missing or escapes the repository",
                        witness_ref,
                    )
                )
                continue
            try:
                payload = json.loads(resolved.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                failures.append(
                    PolicyFailure(
                        "scientific-completeness-witness-invalid",
                        f"concern {item.concern_id!r} witness for {contract_id!r} is not valid JSON: {exc}",
                        witness_ref,
                    )
                )
                continue
            except ValueError, RecursionError:
                # The witness is not UTF-8, has an integer beyond the interpreter digit limit or nests beyond the decoder.
                failures.append(
                    PolicyFailure(
                        "scientific-completeness-witness-invalid",
                        f"concern {item.concern_id!r} witness for {contract_id!r} is not UTF-8 JSON within the "
                        "decoder limits",
                        witness_ref,
                    )
                )
                continue
            diagnostics = validate_contract_payload(contract_id, payload)
            if diagnostics:
                failures.append(
                    PolicyFailure(
                        "scientific-completeness-witness-nonconforming",
                        f"concern {item.concern_id!r} witness does not conform to "
                        f"{contract_id!r}: {diagnostics[0].message}",
                        witness_ref,
                    )
                )
    return failures


def _published_schema_paths(repo_root: Path) -> dict[str, str]:
    manifest = load_schema_publication_catalog(repo_root)
    schemas = manifest.get("schemas", [])
    if not isinstance(schemas, list):
        raise InvalidInputError("schema publication catalog schemas must be a list")
    return {
        entry["contract_id"]: entry["schema_path"]
        for entry in schemas
        if isinstance(entry, dict) and isinstance(entry.get("contract_id"), str)
    }


def _validate_contract_evidence(
    repo_root: Path,
    assessment: ScientificCompletenessAssessmentModel,
) -> list[PolicyFailure]:
    published_schemas = _published_schema_paths(repo_root)
    failures: list[PolicyFailure] = []
    for item in assessment.concerns:
        for evidence in item.evidence:
            if evidence.contract_id is None:
                continue
            expected_path = published_schemas.get(evidence.contract_id)
            if expected_path != evidence.path:
                failures.append(
                    PolicyFailure(
                        "scientific-completeness-contract-evidence-mismatch",
                        f"concern {item.concern_id!r} contract "
                        f"{evidence.contract_id!r} must cite its published schema "
                        f"path {expected_path!r}",
                        evidence.path,
                    )
                )
    return failures


def _validate_profile_examples(
    repo_root: Path,
    taxonomy: ScientificCompletenessTaxonomyModel,
    outcomes: tuple[ProfileCompletenessResult, ...],
) -> list[PolicyFailure]:
    outcome_by_id = {outcome.profile_id: outcome for outcome in outcomes}
    failures: list[PolicyFailure] = []
    for profile in taxonomy.profiles:
        outcome = outcome_by_id[profile.profile_id]
        if outcome.complete and not profile.example_refs:
            failures.append(
                PolicyFailure(
                    "scientific-completeness-example-required",
                    f"complete profile {profile.profile_id!r} requires a minimal example",
                )
            )
        if not outcome.complete and profile.example_refs:
            failures.append(
                PolicyFailure(
                    "scientific-completeness-example-overclaim",
                    f"incomplete profile {profile.profile_id!r} must not present an example as completeness evidence",
                )
            )
        for example_ref in profile.example_refs:
            resolved = safe_repo_path(repo_root, example_ref)
            if resolved is None or not resolved.is_file():
                failures.append(
                    PolicyFailure(
                        "scientific-completeness-example-missing",
                        f"profile {profile.profile_id!r} example is missing or escapes the repository",
                        example_ref,
                    )
                )
    return failures


def _validate_nonclaims(
    taxonomy: ScientificCompletenessTaxonomyModel,
) -> list[PolicyFailure]:
    non_claim_text = " ".join(
        statement.lower() for profile in taxonomy.profiles for statement in profile.explicit_non_claims
    )
    missing_terms = sorted(term for term in _REQUIRED_NON_CLAIM_TERMS if term not in non_claim_text)
    if not missing_terms:
        return []
    return [
        PolicyFailure(
            "scientific-completeness-nonclaim-coverage",
            f"REV1 explicit non-claims must cover: {missing_terms}",
        )
    ]


def _validate_summary(
    repo_root: Path,
    outcomes: tuple[ProfileCompletenessResult, ...],
) -> list[PolicyFailure]:
    spec_path = repo_root / "specs/sdl/scientific-scenario-completeness.md"
    spec_text = spec_path.read_text(encoding="utf-8") if spec_path.is_file() else ""
    if _render_summary(outcomes) in spec_text:
        return []
    return [
        PolicyFailure(
            "scientific-completeness-summary-drift",
            "normative reader-facing outcome table does not match the computed profile outcomes",
            "specs/sdl/scientific-scenario-completeness.md",
        )
    ]


def _validate_required_exclusions(
    taxonomy: ScientificCompletenessTaxonomyModel,
    assessment: ScientificCompletenessAssessmentModel,
) -> list[PolicyFailure]:
    assessment_by_id = {item.concern_id: item for item in assessment.concerns}
    required_deliberate_exclusions = {
        concern_id
        for profile in taxonomy.profiles
        for concern_id, disposition in profile.dispositions.items()
        if disposition.value == "required"
        and assessment_by_id[concern_id].status is DeliveryStatus.DELIBERATELY_EXCLUDED
    }
    if not required_deliberate_exclusions:
        return []
    return [
        PolicyFailure(
            "scientific-completeness-required-exclusion",
            "deliberately excluded concerns cannot satisfy required profile rows: "
            + ", ".join(sorted(required_deliberate_exclusions)),
        )
    ]


def evaluate(repo_root: Path) -> list[PolicyFailure]:
    try:
        taxonomy = load_scientific_completeness_taxonomy()
        assessment = load_scientific_completeness_assessment()
    except (OSError, UnicodeDecodeError, ValidationError, InvalidInputError) as exc:
        return [PolicyFailure("scientific-completeness-invalid", str(exc))]
    try:
        outcomes = evaluate_profile_completeness(taxonomy, assessment)
    except ValueError as exc:  # the model cross-check reports a mismatch with ValueError (E3)
        return [PolicyFailure("scientific-completeness-invalid", str(exc))]

    failures: list[PolicyFailure] = []
    failures.extend(_validate_profile_set(taxonomy))
    failures.extend(_validate_evidence_paths(repo_root, assessment))
    try:
        failures.extend(_validate_contract_evidence(repo_root, assessment))
    except (OSError, UnicodeDecodeError, InvalidInputError) as exc:
        failures.append(
            PolicyFailure(
                "scientific-completeness-manifest-invalid",
                f"cannot validate contract evidence against publication manifest: {exc}",
            )
        )
    failures.extend(_validate_profile_examples(repo_root, taxonomy, outcomes))
    failures.extend(_validate_nonclaims(taxonomy))
    failures.extend(_validate_summary(repo_root, outcomes))
    failures.extend(_validate_required_exclusions(taxonomy, assessment))
    return failures


def main() -> int:
    failures = evaluate(REPO_ROOT)
    for failure in failures:
        print(failure.render())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run_application(main))
