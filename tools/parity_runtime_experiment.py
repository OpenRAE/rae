#!/usr/bin/env python3
"""Re-record the runtime experiment references against the reference runtime.

Each reference keeps its authored trial facts. The recorder recompiles the
retained compilation request, moves the authored facts to the identities of
the new plan, and records the expected runs with the reference assembly.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import re
import sys
from collections.abc import Callable
from io import BytesIO
from types import SimpleNamespace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from parity_trial_compiler import build_request  # noqa: E402
from raes_contracts.assigned_trial import trial_attempt_id  # noqa: E402
from raes_contracts.contracts import (  # noqa: E402
    AdmittedTrialPlanModel,
    ExperimentEvidenceRecordModel,
    ExperimentRunEvidenceInputs,
    ExperimentRunModel,
    ExperimentStudyModel,
    validate_admitted_trial_run,
    validate_admitted_trial_study,
    validate_experiment_run_against_task,
)
from raes_processor.compiler.scenario_references import authored_scenario_evidence  # noqa: E402
from raes_processor.trial_compiler import compile_admitted_trial_plan  # noqa: E402
from raes_processor.trial_compiler.replacement import (
    TrialReplacementResult,
    compile_replacement_trial,
)  # noqa: E402
from raes_processor.trial_realization import (
    TrialRealizationInputs,
    realize_admitted_trial_entry,
)  # noqa: E402
from raes_runtime.experiment_records import (
    ExperimentRecordSource,
    ExperimentRunMetadata,
)  # noqa: E402
from raes_runtime.runtime_record_assembly import assemble_run  # noqa: E402
from raes_runtime.runtime_decisions import validate_runtime_decision  # noqa: E402
from raes_runtime.runtime_experiment_records import _run_metadata  # noqa: E402
from raes_runtime.runtime_record_lineage import (
    accounting_validation_record,
    canonical_archival_runs,
)  # noqa: E402
from raes_runtime.runtime_study_records import _authored_definition, _study_snapshot  # noqa: E402
from raes_runtime.runtime_trial_decisions import (  # noqa: E402
    TrialArchiveCandidateDecision,
    TrialAttemptDecision,
    TrialObservationDecision,
    TrialReplacementDecision,
)

TESTDATA = ROOT / "implementations/go/runtime/experiment/testdata"
COMPILER = (
    ROOT / "implementations/go/processor/trial/testdata/compiler-reference.json.gz"
)
TOKEN = re.compile(r"sha256:[0-9a-f]{64}|[a-z][a-z-]*-[0-9a-f]{64}")
EMBEDDED = re.compile(
    r"sha256:[0-9a-f]{64}|[a-z][a-z-]*-[0-9a-f]{64}|attempt:[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
)


def _load(path: Path) -> Any:
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def _store(path: Path, value: Any) -> None:
    text = json.dumps(value, indent=2) + "\n"
    if path.suffix == ".gz":
        path.write_bytes(gzip.compress(text.encode(), compresslevel=9, mtime=0))
    else:
        path.write_text(text, encoding="utf-8")


class Compilation:
    """One reference compilation and the realization of each of its entries."""

    def __init__(self, request_payload: dict[str, Any]) -> None:
        self.request, self.stored = build_request(request_payload)
        result = compile_admitted_trial_plan(self.request)
        if result.plan is None:
            raise ValueError(
                f"the retained request no longer compiles: {[item.code for item in result.diagnostics]}"
            )
        self.plan: AdmittedTrialPlanModel = result.plan
        self.wire = self.plan.model_dump(mode="json")

    def realization(
        self, entry_id: str, plan: AdmittedTrialPlanModel | None = None
    ) -> Any:
        backend = next(
            key for key in self.request.apparatus_manifests if key[0] == "backend"
        )
        return realize_admitted_trial_entry(
            inputs=TrialRealizationInputs(
                plan=self.plan if plan is None else plan,
                family=self.request.family,
                experiment=self.request.experiment,
                task=self.request.task,
                capture_specs=self.request.capture_specs,
                apparatus_manifests=self.request.apparatus_manifests,
                realization_envelope=self.request.realization_envelope,
                backend_key=backend,
                participant_manifests=self.request.participant_manifests,
            ),
            plan_entry_id=entry_id,
        )


def _zip_tokens(old: Any, new: Any, tokens: dict[str, str]) -> None:
    """Pair each identity token of an old plan with the token at the same place in the new plan."""
    if isinstance(old, str) and isinstance(new, str):
        if old != new and TOKEN.fullmatch(old) and TOKEN.fullmatch(new):
            if tokens.setdefault(old, new) != new:
                raise ValueError(f"identity {old} moves to two identities")
        return
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        for left, right in zip(old, new, strict=True):
            _zip_tokens(left, right, tokens)
        return
    if isinstance(old, dict) and isinstance(new, dict):
        for key in old.keys() & new.keys():
            _zip_tokens(old[key], new[key], tokens)


def _entries_by_coordinate(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        json.dumps(entry["coordinate"], sort_keys=True): entry
        for entry in plan["entries"].values()
    }


def plan_tokens(
    old: dict[str, Any], new: dict[str, Any], experiments: tuple[str, str] | None = None
) -> dict[str, str]:
    """Return the identity moves from an old compiled plan to its recompilation.

    Attempt identities derive from the experiment, which is the root plan of a replacement chain.
    """
    old_experiment, new_experiment = experiments or (old["plan_id"], new["plan_id"])
    tokens: dict[str, str] = {}
    old_entries, new_entries = _entries_by_coordinate(old), _entries_by_coordinate(new)
    if old_entries.keys() != new_entries.keys():
        raise ValueError(
            "the recompiled plan does not keep the retained trial coordinates"
        )
    for coordinate, entry in old_entries.items():
        _zip_tokens(entry, new_entries[coordinate], tokens)
    _zip_tokens(
        {key: value for key, value in old.items() if key != "entries"}, new, tokens
    )
    for key, value in old["cleanup_plans"].items():
        moved = tokens.get(key, key)
        if moved in new["cleanup_plans"]:
            _zip_tokens(value, new["cleanup_plans"][moved], tokens)
    for coordinate, entry in old_entries.items():
        fresh = new_entries[coordinate]
        for ordinal in range(1, 1001):
            before = trial_attempt_id(old_experiment, entry["plan_entry_id"], ordinal)
            tokens[before] = trial_attempt_id(
                new_experiment, fresh["plan_entry_id"], ordinal
            )
    return tokens


def move(value: Any, tokens: dict[str, str]) -> Any:
    """Return the value with every retained identity moved to its new identity."""
    if isinstance(value, str):
        return EMBEDDED.sub(
            lambda match: tokens.get(match.group(0), match.group(0)), value
        )
    if isinstance(value, list):
        return [move(item, tokens) for item in value]
    if isinstance(value, dict):
        return {move(key, tokens): move(item, tokens) for key, item in value.items()}
    return value


def record_source(
    compilation: Compilation,
    case: dict[str, Any],
    plan: AdmittedTrialPlanModel | None = None,
) -> ExperimentRecordSource:
    """Return the protected record source of the retained trial facts."""
    plan = compilation.plan if plan is None else plan
    attempts = tuple(
        TrialAttemptDecision.model_validate(item) for item in case["attempts"]
    )
    observations = tuple(
        TrialObservationDecision.model_validate(item) for item in case["observations"]
    )
    entry = plan.entries[attempts[0].plan_entry_id]
    return ExperimentRecordSource(
        run_id=entry.run_id,
        plan=plan,
        realization=compilation.realization(entry.plan_entry_id, plan),
        attempts=attempts,
        observations=observations,
        execution_snapshots={},
        phase_states=case["phase_states"],
        operation_refs={},
        operation_states={},
        operation_receipts=(),
    )


def assembled_run(
    compilation: Compilation,
    case: dict[str, Any],
    plan: AdmittedTrialPlanModel | None = None,
) -> ExperimentRunModel:
    """Assemble the run that the reference runtime records for the retained trial facts."""
    return assemble_run(
        record_source(compilation, case, plan),
        ExperimentRunMetadata.model_validate(case["metadata"]),
    )


def run_record(compilation: Compilation, case: dict[str, Any]) -> dict[str, Any]:
    return assembled_run(compilation, case).model_dump(mode="json")


def _processor_realization() -> tuple[dict[str, Any], Compilation]:
    case = next(
        item
        for item in _load(COMPILER)["cases"]
        if item["name"] == "processor-realization"
    )
    return case, Compilation(case["request"])


def records_reference(reference: dict[str, Any]) -> dict[str, Any]:
    """Record the runs of the processor-realization entry for each retained trial history."""
    case, compilation = _processor_realization()
    tokens = plan_tokens(reference["plan"], compilation.wire)
    cases = []
    for item in reference["cases"]:
        moved = move(
            {key: value for key, value in item.items() if key != "run"}, tokens
        )
        cases.append({**moved, "run": run_record(compilation, moved)})
    return {
        "sources": reference["sources"],
        "plan": compilation.wire,
        "entry_id": move(reference["entry_id"], tokens),
        "cases": cases,
    }


def _evidence(
    compilation: Compilation, record: dict[str, Any], content: str
) -> ExperimentRunEvidenceInputs:
    evidence = ExperimentEvidenceRecordModel.model_validate(record)
    return ExperimentRunEvidenceInputs(
        capture_specs=compilation.request.capture_specs,
        evidence_records={evidence.evidence_record_id: evidence},
        artifact_readers={evidence.capture_requirement_ref: BytesIO(content.encode())},
    )


SCIENCE = "scientific-record-reference.json"
_SCIENCE: dict[str, Any] = {}


def science_chain() -> dict[str, Any]:
    """Return the re-recorded scientific trial that the science references share."""
    if not _SCIENCE:
        reference = _load(TESTDATA / SCIENCE)
        compilation = Compilation(reference["request"])
        tokens = plan_tokens(reference["plan"], compilation.wire)
        case = move(
            {key: value for key, value in reference["case"].items() if key != "run"},
            tokens,
        )
        definition = _authored_definition(
            SimpleNamespace(plan=compilation.plan),
            ExperimentStudyModel.model_validate(reference["definition"]),
        )
        _SCIENCE.update(
            reference=reference,
            compilation=compilation,
            tokens=tokens,
            case=case,
            record=move(reference["record"], tokens),
            source=record_source(compilation, case),
            definition=definition,
        )
    return _SCIENCE


def _science_run(chain: dict[str, Any], run_version: str) -> ExperimentRunModel:
    """Assemble the scientific run with the metadata that the reference runtime completes."""
    task = chain["compilation"].request.task
    metadata = ExperimentRunMetadata.model_validate(
        {**chain["case"]["metadata"], "run_version": run_version}
    )
    run = assemble_run(
        chain["source"],
        _run_metadata(SimpleNamespace(inputs=SimpleNamespace(task=task)), metadata),
    )
    validate_admitted_trial_run(chain["compilation"].plan, run, list(_receipts(run)))
    return run


def _science_study(
    chain: dict[str, Any], run: ExperimentRunModel, checked: ExperimentRunModel
) -> dict[str, Any]:
    """Validate the evaluation evidence and return the study snapshot over the validated run."""
    compilation = chain["compilation"]
    task, family = compilation.request.task, compilation.request.family
    content = chain["reference"]["content"]
    validate_experiment_run_against_task(
        task, checked, evidence=_evidence(compilation, chain["record"], content)
    )
    bundle = SimpleNamespace(
        sources=(chain["source"],),
        runs=(run,),
        validation_records=(checked,),
        eligible_run_ids=(run.run_id,),
    )
    study = _study_snapshot(bundle, chain["definition"])
    validate_admitted_trial_study(
        compilation.plan,
        study,
        [task],
        [checked],
        evidence_by_run={run.run_id: _evidence(compilation, chain["record"], content)},
        study_definition=chain["definition"],
        relation_scenarios={family.name: authored_scenario_evidence(family)},
        relation_capture_specs=compilation.request.capture_specs,
    )
    return study.model_dump(mode="json")


def science_reference(reference: dict[str, Any]) -> dict[str, Any]:
    """Record the validated run and the study snapshot of one scientific trial."""
    chain = science_chain()
    run, checked = accounting_validation_record(
        _science_run(chain, chain["case"]["metadata"]["run_version"]), None
    )
    return {
        **reference,
        "request": chain["compilation"].stored,
        "plan": chain["compilation"].wire,
        "entry_id": move(reference["entry_id"], chain["tokens"]),
        "record": chain["record"],
        "study": _science_study(chain, run, checked),
        "case": {**chain["case"], "run": run.model_dump(mode="json")},
    }


def scientific_accounting_reference(reference: dict[str, Any]) -> dict[str, Any]:
    """Record added accounting that links a later run version to the exact scientific original."""
    chain = science_chain()
    original, _ = accounting_validation_record(
        _science_run(chain, chain["case"]["metadata"]["run_version"]), None
    )
    candidate = TrialArchiveCandidateDecision(
        experiment_id=chain["compilation"].plan.plan_id, run=original
    )
    canonical = canonical_archival_runs((candidate,), candidate.experiment_id)
    linked, checked = accounting_validation_record(
        _science_run(chain, "2"), canonical.get(original.run_id)
    )
    return {
        **reference,
        "linked": linked.model_dump(mode="json"),
        "checked": checked.model_dump(mode="json"),
        "study": _science_study(chain, linked, checked),
    }


def _receipts(run: ExperimentRunModel) -> tuple[Any, ...]:
    return tuple(
        item.cleanup_receipt
        for item in run.execution_accounting.attempts
        if item.cleanup_receipt is not None
    )


def _replace(
    compilation: Compilation,
    entry_id: str,
    run: ExperimentRunModel,
    history: tuple[TrialReplacementResult, ...],
) -> TrialReplacementResult:
    """Allocate the next replacement as the reference runtime does for a committed failed run."""
    receipts = _receipts(run)
    result = compile_replacement_trial(
        compilation.request,
        original_plan=compilation.plan,
        root_entry_id=entry_id,
        previous_allocations=history,
        failed_run=run,
        cleanup_receipts=receipts,
    )
    if result.plan is None:
        raise ValueError(
            f"the replacement compiler refused: {[item.code for item in result.diagnostics]}"
        )
    return TrialReplacementResult(
        result.plan, result.superseded_run, parent_run=run, cleanup_receipts=receipts
    )


REPLACEMENT = "runtime-replacement-reference.json"
_REPLACEMENT_CHAIN: dict[str, Any] = {}


def replacement_chain() -> dict[str, Any]:
    """Return the re-recorded first replacement that the replacement references share."""
    if not _REPLACEMENT_CHAIN:
        reference = _load(TESTDATA / REPLACEMENT)
        compilation = Compilation(reference["request"])
        tokens = plan_tokens(reference["plan"], compilation.wire)
        entry_id = move(reference["entry_id"], tokens)
        case = move(
            {key: value for key, value in reference["case"].items() if key != "run"},
            tokens,
        )
        run = assembled_run(compilation, case)
        first = _replace(compilation, entry_id, run, ())
        experiments = (reference["plan"]["plan_id"], compilation.plan.plan_id)
        child_tokens = plan_tokens(
            reference["child"], first.plan.model_dump(mode="json"), experiments
        )
        _REPLACEMENT_CHAIN.update(
            reference=reference,
            compilation=compilation,
            tokens={**tokens, **child_tokens},
            entry_id=entry_id,
            case={**case, "run": run.model_dump(mode="json")},
            first=first,
        )
    return _REPLACEMENT_CHAIN


def runtime_replacement_reference(reference: dict[str, Any]) -> dict[str, Any]:
    """Record the first replacement of the retained failed parent trial."""
    chain = replacement_chain()
    first = chain["first"]
    return {
        **reference,
        "request": chain["compilation"].stored,
        "plan": chain["compilation"].wire,
        "entry_id": chain["entry_id"],
        "case": chain["case"],
        "child": first.plan.model_dump(mode="json"),
        "superseded_run": first.superseded_run.model_dump(mode="json"),
    }


def replacement_sequence_reference(reference: dict[str, Any]) -> dict[str, Any]:
    """Record the second replacement after the retained failed first child."""
    chain = replacement_chain()
    compilation, first = chain["compilation"], chain["first"]
    case = move(
        {key: value for key, value in reference["child_case"].items() if key != "run"},
        chain["tokens"],
    )
    run = assembled_run(compilation, case, first.plan)
    second = _replace(compilation, chain["entry_id"], run, (first,))
    return {
        **reference,
        "child_case": {**case, "run": run.model_dump(mode="json")},
        "second_child": second.plan.model_dump(mode="json"),
        "second_superseded_run": second.superseded_run.model_dump(mode="json"),
    }


# Batch receipt fields that trial parallelism removed with scheduler isolation.
REMOVED_RECEIPT_FIELDS = ("isolation_proof_ref", "lease_evidence_refs")
MUTATIONS: tuple[tuple[bool, Any], ...] = (
    (True, None),
    (False, None),
    (False, []),
    (False, {}),
    (False, False),
)
MUTATIONS += ((False, "invalid"),)


def _refused(document: dict[str, Any]) -> bool:
    try:
        validate_runtime_decision(document)
    except ValueError:
        return True
    return False


def _boundary_document(document: dict[str, Any]) -> dict[str, Any]:
    """Return the current form of one retained private decision."""
    if document["schema_version"] == "runtime-trial-replacement/v1":
        chain = replacement_chain()
        first = chain["first"]
        return TrialReplacementDecision(
            experiment_id=chain["compilation"].plan.plan_id,
            root_entry_id=chain["entry_id"],
            ordinal=first.plan.replacement_origin.ordinal,
            plan=first.plan,
            superseded_run=first.superseded_run,
            parent_run=first.parent_run,
            cleanup_receipts=first.cleanup_receipts,
        ).model_dump(mode="json")
    if document["schema_version"] == "runtime-trial-terminal/v1":
        receipt = {
            key: value
            for key, value in document["receipt"].items()
            if key not in REMOVED_RECEIPT_FIELDS
        }
        document = {**document, "receipt": receipt}
    return validate_runtime_decision(document).model_dump(mode="json")


def _boundary_paths(document: dict[str, Any]) -> list[tuple[str, ...]]:
    paths = [(key,) for key in document if key != "schema_version"]
    if isinstance(document.get("observation"), dict):
        paths += [
            ("observation", key) for key in document["observation"] if key != "kind"
        ]
    return [*paths, ("unexpected",)]


def _mutated(
    document: dict[str, Any], path: tuple[str, ...], delete: bool, value: Any
) -> dict[str, Any] | None:
    changed = copy.deepcopy(document)
    target = changed
    for part in path[:-1]:
        target = target[part]
    if delete and path[-1] not in target:
        return None
    if delete:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return changed


def decision_boundaries_reference(reference: dict[str, Any]) -> dict[str, Any]:
    """Record each private decision and every field mutation that the source models refuse."""
    documents, cases = [], []
    for base, item in enumerate(reference["documents"]):
        document = _boundary_document(item["document"])
        documents.append(
            {
                "document": document,
                "id": validate_runtime_decision(document).decision_id,
            }
        )
        for path in _boundary_paths(document):
            for delete, value in MUTATIONS:
                changed = _mutated(document, path, delete, value)
                if changed is not None and _refused(changed):
                    action = "delete" if delete else "set"
                    name = f"{base}/{'.'.join(path)}/{action}/{json.dumps(value)}"
                    cases.append(
                        {
                            "name": name,
                            "base": base,
                            "path": list(path),
                            "delete": delete,
                            "value": value,
                        }
                    )
    return {**reference, "documents": documents, "cases": cases}


def _decision(document: dict[str, Any]) -> dict[str, Any]:
    decision = validate_runtime_decision(document)
    return {"document": decision.model_dump(mode="json"), "id": decision.decision_id}


def decisions_reference(reference: dict[str, Any]) -> dict[str, Any]:
    """Record the projection and identity of each retained private decision."""
    return {
        **reference,
        "cases": [_decision(item["document"]) for item in reference["cases"]],
    }


def decision_defaults_reference(reference: dict[str, Any]) -> dict[str, Any]:
    """Record the defaulted projection and identity of each retained private decision input."""
    return {
        **reference,
        "cases": [{**item, **_decision(item["input"])} for item in reference["cases"]],
    }


def lineage_case(case: dict[str, Any], experiment_id: str) -> dict[str, Any]:
    records = [validate_runtime_decision(item) for item in case["records"]]
    current = ExperimentRunModel.model_validate(case["current"])
    canonical = canonical_archival_runs(records, experiment_id)
    linked, checked = accounting_validation_record(
        current, canonical.get(current.run_id)
    )
    return {
        **case,
        "linked": linked.model_dump(mode="json"),
        "checked": checked.model_dump(mode="json"),
    }


def record_lineage_reference(reference: dict[str, Any]) -> dict[str, Any]:
    """Record the accounting link of each retained run to its exact scientific original."""
    experiment_id = reference["experiment_id"]
    return {
        **reference,
        "cases": [lineage_case(case, experiment_id) for case in reference["cases"]],
    }


def compilation_case(case: dict[str, Any]) -> dict[str, Any]:
    """Recompile one retained compilation request."""
    compilation = Compilation(case["request"])
    return {**case, "request": compilation.stored, "plan": compilation.wire}


def retry_reference(reference: dict[str, Any]) -> dict[str, Any]:
    return {
        **reference,
        "cases": [compilation_case(case) for case in reference["cases"]],
    }


RECORDS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "records-reference.json": records_reference,
    "retry-reference.json": retry_reference,
    SCIENCE: science_reference,
    "scientific-accounting-reference.json": scientific_accounting_reference,
    REPLACEMENT: runtime_replacement_reference,
    "replacement-sequence-reference.json": replacement_sequence_reference,
    "decision-boundaries-reference.json": decision_boundaries_reference,
    "decisions-reference.json": decisions_reference,
    "decision-defaults-reference.json": decision_defaults_reference,
    "record-lineage-reference.json.gz": record_lineage_reference,
}


def _with_sources(reference: dict[str, Any]) -> dict[str, Any]:
    """Pin each named reference source to its current content."""
    sources = reference.get("sources")
    if isinstance(sources, dict):
        reference["sources"] = {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in sources
        }
    return reference


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    failed = False
    for name, record in RECORDS.items():
        path = TESTDATA / name
        before = _load(path)
        after = _with_sources(record(copy.deepcopy(before)))
        if args.check:
            if after != before:
                print(f"{name} differs from the reference runtime", file=sys.stderr)
                failed = True
        elif after != before:
            _store(path, after)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
