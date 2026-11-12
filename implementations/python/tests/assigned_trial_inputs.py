"""Write the assigned-trial consumer inputs from the current compiler (issue #1944).

The inputs hold a compiled plan and digests of the other inputs. They are never
committed: every caller writes them from the same test builders, so a change to
compilation or to the builders cannot leave a stale copy behind.

Run as a script with the interpreter under test to write both documents into a
directory; ``installed_assigned_trial_consumer.py`` then reads them under ``-I``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from paths import REPO_ROOT

ORIGINAL_INPUTS = "assigned-trial-inputs.json"
REPLACEMENT_INPUTS = "assigned-trial-replacement-inputs.json"


def _contract_fixture(relative: str) -> dict:
    return json.loads((REPO_ROOT / "contracts" / "fixtures" / relative).read_text(encoding="utf-8"))


def _document(inputs) -> dict:
    return {
        "plan": inputs.plan.model_dump(mode="json"),
        # The family is the authored form: field presence without processor provenance.
        "family": inputs.family.model_dump(
            mode="json", by_alias=True, exclude_unset=True, exclude={"expansion_provenance"}
        ),
        "experiment": inputs.experiment.model_dump(mode="json"),
        "task": inputs.task.model_dump(mode="json"),
        "capture_specs": {key: value.model_dump(mode="json") for key, value in inputs.capture_specs.items()},
        "apparatus_manifests": [
            {"key": list(key), "value": value.model_dump(mode="json")}
            for key, value in inputs.apparatus_manifests.items()
        ],
        "realization_envelope": inputs.realization_envelope.model_dump(mode="json"),
        "backend_key": list(inputs.backend_key),
        "evidence_template": _contract_fixture("experiment-core/experiment-evidence-record-v1/valid/reference.json"),
    }


def _compilation_request(request) -> dict:
    return {
        "input_refs": request.input_refs.model_dump(mode="json"),
        "apparatus": request.apparatus.model_dump(mode="json"),
        "execution_authority": request.execution_authority.model_dump(mode="json"),
        "participant_manifests": [
            {"key": list(key), "value": value.model_dump(mode="json")}
            for key, value in request.participant_manifests.items()
        ],
        "participant_validator_keys": [list(key) for key in request.participant_configuration_validators],
    }


def original_inputs() -> dict:
    """Return the original parallel allocation inputs."""
    from issue_1870_trial_fixture import parallel_inputs

    _request, inputs, _target = parallel_inputs()
    return _document(inputs)


def replacement_inputs() -> dict:
    """Return the inputs of one original condition with one permitted replacement."""
    from issue_1870_trial_fixture import replacement_inputs as build

    request, inputs, _target = build()
    return {
        **_document(inputs),
        "compilation_request": _compilation_request(request),
        "run_template": _contract_fixture("experiment-core/experiment-run-v1/valid/reference.json"),
    }


def write_inputs(directory: Path) -> Path:
    """Write both documents into *directory*; return the original inputs path."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / REPLACEMENT_INPUTS).write_text(json.dumps(replacement_inputs()), encoding="utf-8")
    original = directory / ORIGINAL_INPUTS
    original.write_text(json.dumps(original_inputs()), encoding="utf-8")
    return original


if __name__ == "__main__":
    import raes_processor

    # The interpreter under test compiles the plan; its installed packages, not the source tree, must run.
    assert Path(raes_processor.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), raes_processor.__file__
    print(write_inputs(Path(sys.argv[1])))
