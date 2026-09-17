"""Published phase and result schemas preserve the same strict exchange shapes."""

from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator
from raes_contracts.contracts import schema_bundle
from test_issue_1241_materialized_sdl import materialized_payload


def test_materialization_contracts_are_published_with_qualified_sdl_identity():
    bundle = schema_bundle()
    assert {
        "materialized-scenario-v1",
        "backend-materialization-attestation-v1",
        "materialization-archive-record-v1",
    } <= bundle.keys()
    schema = bundle["materialized-scenario-v1"]
    validator = Draft202012Validator(schema)
    payload = materialized_payload(nodes={"lab.host": {"type": "compute"}})
    assert not list(validator.iter_errors(payload))
    for name in ["Not Portable", "lab." + "a" * 36]:
        invalid = deepcopy(payload)
        invalid["nodes"] = {name: {"type": "compute"}}
        assert list(validator.iter_errors(invalid))
    assert schema["additionalProperties"] is False
    assert schema["x-raes-document-phase"] == "materialized-scenario"


@pytest.mark.parametrize(
    "field,value", [("variables", {}), ("imports", []), ("module", None), ("description", "${unbound}")]
)
def test_materialized_schema_rejects_other_phase_machinery_and_substitution(field, value):
    validator = Draft202012Validator(schema_bundle()["materialized-scenario-v1"])
    assert list(validator.iter_errors(materialized_payload(**{field: value})))


@pytest.mark.parametrize("field", ["node_name", "source_node"])
@pytest.mark.parametrize("value", ["not portable", "lab.__private", "lab..host", "host\n", "a" * 2049])
def test_published_resource_bindings_reject_invalid_qualified_identity(field, value):
    from raes.materialization_provenance import MaterializedResourceBinding

    payload = materialized_payload()
    binding = {"address": "provision.node.host", "node_name": "host", "source_node": "host", field: value}
    with pytest.raises(ValueError):
        MaterializedResourceBinding.model_validate(binding)
    payload["materialization_provenance"]["resource_bindings"] = [binding]
    validator = Draft202012Validator(schema_bundle()["materialized-scenario-v1"])
    assert list(validator.iter_errors(payload))
