#!/usr/bin/env python3
"""Re-record retained admitted-trial references against the reference owner.

The native trial tests keep independent inputs with their reference results.
This recorder keeps each retained input. It removes the scheduler isolation
fields that the trial-parallelism contract replaced, reseals each plan with
the reference serialization, carries every replaced plan digest into the
documents that cite it, and records the reference result again.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import sys
import types
import typing
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementations/python/packages"))

from raes_contracts._sealing import sealing  # noqa: E402
from raes_contracts.canonical import canonical_json_digest  # noqa: E402
from raes_contracts.contract_seals import seal_contract_fixture  # noqa: E402
from raes_contracts.contracts.admitted_trial_plan import AdmittedTrialPlanModel  # noqa: E402
from raes_contracts.contracts.experiment_run import ExperimentRunModel  # noqa: E402
from raes_contracts.contracts.trial_analysis import validate_admitted_trial_run  # noqa: E402
from raes_contracts.contracts.trial_cleanup import TrialCleanupReceiptModel  # noqa: E402
from raes_contracts.contracts.trial_replacement_analysis import reconcile_replacement_trials  # noqa: E402
from raes_contracts.contracts.trial_replacement_archive import build_superseded_trial_run  # noqa: E402

TESTDATA = ROOT / "implementations/go/contract/admission/testdata"
PLAN_FIXTURES = ROOT / "contracts/fixtures/plans/admitted-trial-plan-v1/valid"
PLACEHOLDER = "sha256:" + "0" * 64
REMOVED_PLAN_FIELDS = ("isolation_proof",)
REMOVED_PROFILE_FIELDS = ("isolation_profile",)
REJECTED = (ValidationError, ValueError, TypeError, KeyError)


def _field_value(annotation: object, value: object) -> object:
    """Validate one field value; build a nested model without its own model checks when it does not validate."""
    try:
        with sealing():
            return TypeAdapter(annotation).validate_python(value)
    except ValidationError:
        pass
    origin, args = typing.get_origin(annotation), typing.get_args(annotation)
    if origin is typing.Annotated:
        return _field_value(args[0], value)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel) and isinstance(value, dict):
        return _native_instance(annotation, value)
    if origin is dict and isinstance(value, dict) and len(args) == 2:
        return {key: _field_value(args[1], item) for key, item in value.items()}
    if origin in (list, tuple) and isinstance(value, list) and args:
        return [_field_value(args[0], item) for item in value]
    if origin in (typing.Union, types.UnionType):
        for member in args:
            if isinstance(member, type) and issubclass(member, BaseModel) and isinstance(value, dict):
                try:
                    return _native_instance(member, value)
                except REJECTED:
                    continue
    return value


def _native_instance(model: type[BaseModel], data: dict[str, Any]) -> BaseModel:
    try:
        with sealing():
            return model.model_validate(data)
    except ValidationError:
        pass
    values = {}
    for name, field in model.model_fields.items():
        key = field.alias or name
        if key in data:
            values[name] = _field_value(
                field.annotation if not field.metadata else typing.Annotated[field.annotation, *field.metadata],
                data[key],
            )
    return model.model_construct(**values)


def native_dump(model: type[BaseModel], data: dict[str, Any]) -> dict[str, Any]:
    """Return the reference serialization of *data*, also when its model-level joins are refused."""
    return _native_instance(model, data).model_dump(mode="json", warnings=False)


def reseal_plan(plan: dict[str, Any], exact: bool | None = None) -> dict[str, Any]:
    """Remove the replaced isolation fields and recompute the digests that were exact before.

    Entry content and its digest semantics did not change, so each entry keeps its digest. The plan
    digest covered the removed fields; it is recomputed only when it matched the reference
    serialization with those fields, so a deliberately wrong digest stays wrong. A caller that
    changed cited digests first passes whether the original plan digest was exact.
    """
    result = copy.deepcopy(plan)
    removed = {field: result.pop(field, None) for field in REMOVED_PLAN_FIELDS}
    profiles = result.get("profiles", {})
    removed_profiles = {field: profiles.pop(field) for field in REMOVED_PROFILE_FIELDS if field in profiles}
    stored = result.get("plan_digest")
    result["plan_digest"] = PLACEHOLDER
    dumped = native_dump(AdmittedTrialPlanModel, result)
    dumped.pop("plan_digest", None)
    if exact is None:
        before = {
            **dumped,
            **removed,
            "profiles": {**dumped.get("profiles", {}), **removed_profiles},
        }
        exact = canonical_json_digest(before) == stored
    result["plan_digest"] = canonical_json_digest(dumped) if exact else stored
    return result


def plan_digest_exact(plan: dict[str, Any]) -> bool:
    """Return whether a retained plan digest matches its reference serialization, with any replaced fields."""
    if _has_replaced_fields(plan):
        return reseal_plan(plan)["plan_digest"] != plan.get("plan_digest")
    content = {**plan, "plan_digest": PLACEHOLDER}
    dumped = native_dump(AdmittedTrialPlanModel, content)
    dumped.pop("plan_digest", None)
    return canonical_json_digest(dumped) == plan.get("plan_digest")


def _has_replaced_fields(plan: dict[str, Any]) -> bool:
    return any(field in plan for field in REMOVED_PLAN_FIELDS) or any(
        field in plan.get("profiles", {}) for field in REMOVED_PROFILE_FIELDS
    )


def _replace(value: object, replacements: dict[str, str]) -> object:
    if not replacements:
        return value
    text = json.dumps(value)
    for old, new in replacements.items():
        text = text.replace(json.dumps(old), json.dumps(new))
    return json.loads(text)


def _admitted(check: Callable[[], object]) -> bool:
    try:
        check()
    except REJECTED:
        return False
    return True


def _plan(value: dict[str, Any]) -> AdmittedTrialPlanModel:
    return AdmittedTrialPlanModel.model_validate(value)


def _at(reference: Any, path: tuple[Any, ...]) -> Any:
    for key in path:
        reference = reference[key]
    return reference


def _run_digest(run: dict[str, Any]) -> str:
    return canonical_json_digest(native_dump(ExperimentRunModel, run))


def _migrate_plans(
    reference: dict[str, Any],
    plans: list[tuple[Any, ...]],
    runs: list[tuple[Any, ...]] = (),
) -> dict[str, Any]:
    """Reseal plans in order and carry each replaced plan and run digest into the documents that cite it.

    A run cites its plan digest, and a replacement plan cites its parent run digest, so repeat until no
    cited digest changes.
    """
    exact = {path: plan_digest_exact(_at(reference, path)) for path in plans}
    for _ in range(16):
        progressed = False
        for path in plans:
            before_runs = {path: _run_digest(_at(reference, path)) for path in runs}
            old = _at(reference, path)
            new = reseal_plan(old, exact[path])
            cited = [(old["plan_digest"], new["plan_digest"])]
            cited += [
                (
                    old["entries"][key]["entry_digest"],
                    new["entries"][key]["entry_digest"],
                )
                for key in old["entries"]
            ]
            changed = {before: after for before, after in cited if before != after}
            _at(reference, path[:-1])[path[-1]] = new
            reference = _replace(reference, changed)  # type: ignore[assignment]
            changed_runs = {
                before_runs[run]: _run_digest(_at(reference, run))
                for run in runs
                if before_runs[run] != _run_digest(_at(reference, run))
            }
            reference = _replace(reference, changed_runs)  # type: ignore[assignment]
            progressed = progressed or bool(changed or changed_runs) or new != old
        if not progressed:
            return reference
    raise ValueError("cited digests do not reach a fixed point")


# --- reference files ----------------------------------------------------------------------------------------------


def plan_join_verdicts(reference: dict[str, Any]) -> dict[str, Any]:
    for case in reference["cases"]:
        case["value"] = reseal_plan(case["value"])
        case["admitted"] = _admitted(lambda value=case["value"]: _plan(value))
    return reference


def plan_projections(reference: dict[str, Any]) -> dict[str, Any]:
    cases = []
    for path in sorted(PLAN_FIXTURES.glob("*.json")):
        raw = path.read_bytes()
        sealed = seal_contract_fixture("admitted-trial-plan-v1", json.loads(raw), kind="valid")
        cases.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "result": _plan(sealed).model_dump(mode="json"),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    return {"cases": cases}


def run_reconciliation(reference: dict[str, Any]) -> dict[str, Any]:
    reference = _migrate_plans(reference, [("plan",)])
    plan = _plan(reference["plan"])
    for case in reference["cases"]:

        def check(case: dict[str, Any] = case) -> None:
            run = ExperimentRunModel.model_validate(case["run"])
            receipts = [TrialCleanupReceiptModel.model_validate(item) for item in case["receipts"]]
            validate_admitted_trial_run(plan, run, receipts)

        case["valid"] = _admitted(check)
    return reference


def study_reconciliation(reference: dict[str, Any]) -> dict[str, Any]:
    reference = _migrate_plans(reference, [("plan",)])
    _plan(reference["plan"])
    return reference


def replacement_archive(reference: dict[str, Any]) -> dict[str, Any]:
    reference = _migrate_plans(
        reference,
        [("cases", index, "child") for index in range(len(reference["cases"]))],
    )
    for case in reference["cases"]:
        run = ExperimentRunModel.model_validate(case["run"])
        case["superseded"] = build_superseded_trial_run(run, _plan(case["child"])).model_dump(mode="json")
    return reference


def replacement_study(reference: dict[str, Any]) -> dict[str, Any]:
    paths: list[tuple[Any, ...]] = [("root",)] + [("plans", index) for index in range(len(reference["plans"]))]
    runs: list[tuple[Any, ...]] = [("runs", index) for index in range(len(reference["runs"]))]
    reference = _migrate_plans(reference, paths, runs)
    reconcile_replacement_trials(
        _plan(reference["root"]),
        [_plan(item) for item in reference["plans"]],
        [ExperimentRunModel.model_validate(item) for item in reference["runs"]],
        [TrialCleanupReceiptModel.model_validate(item) for item in reference["receipts"]],
    )
    return reference


def large_byte_limit(reference: dict[str, Any]) -> dict[str, Any]:
    plan = json.loads((PLAN_FIXTURES / "minimal.json").read_text(encoding="utf-8"))
    plan["admission"]["limitations"] = ["a" * reference["limitation_bytes"]]
    plan.pop("plan_digest", None)
    reference["plan_digest"] = _plan(seal_contract_fixture("admitted-trial-plan-v1", plan, kind="valid")).plan_digest
    return reference


RECORDS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "large-byte-limit-reference.json": large_byte_limit,
    "trial-plan-join-verdicts-01.json": plan_join_verdicts,
    "trial-plan-join-verdicts-02.json": plan_join_verdicts,
    "trial-plan-join-verdicts-03.json": plan_join_verdicts,
    "trial-plan-projections.json": plan_projections,
    "trial-run-reconciliation.json": run_reconciliation,
    "trial-study-reconciliation.json": study_reconciliation,
    "replacement-archive-reference.json": replacement_archive,
    "replacement-study-reference.json": replacement_study,
}


def large_plan(plan: dict[str, Any]) -> dict[str, Any]:
    resealed = reseal_plan(plan)
    _plan(resealed)
    return resealed


GZIP_RECORDS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "large-source-plan.json.gz": large_plan,
    "large-trial-plan.json.gz": large_plan,
}


def _encode(value: object, original: str) -> str:
    compact = "\n" not in original.strip()
    if compact:
        return json.dumps(value, separators=(",", ":")) + ("\n" if original.endswith("\n") else "")
    return json.dumps(value, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    failed = False
    for name, record in RECORDS.items():
        path = TESTDATA / name
        original = path.read_text(encoding="utf-8")
        before = json.loads(original)
        after = record(copy.deepcopy(before))
        if args.check:
            if after != before:
                print(f"{name} differs from the reference owner", file=sys.stderr)
                failed = True
        elif after != before:
            path.write_text(_encode(after, original), encoding="utf-8")
    for name, record in GZIP_RECORDS.items():
        path = TESTDATA / name
        before = json.loads(gzip.decompress(path.read_bytes()))
        after = record(copy.deepcopy(before))
        if args.check:
            if after != before:
                print(f"{name} differs from the reference owner", file=sys.stderr)
                failed = True
        elif after != before:
            encoded = json.dumps(after, separators=(",", ":")).encode()
            path.write_bytes(gzip.compress(encoded, compresslevel=9, mtime=0))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
