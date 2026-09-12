"""Safe legacy mount observations retain the existing typed presence contract."""

import pytest
from pydantic import TypeAdapter
from raes.runtime_mounts import RuntimeMount
from raes_processor.semantics.realization_concern_observations import typed_runtime_observation_shape
from raes_processor.semantics.realization_concern_projections import project_mounts, sanitize_mount_observation


@pytest.mark.parametrize("protected", [False, True])
def test_typed_presence_view_accepts_owned_safe_mount_projection(protected):
    mount = RuntimeMount(
        target="/work",
        source="" if protected else "/fixtures/work",
        source_kind="bind",
        source_sensitivity="operator_secret" if protected else "plain",
        options=[] if protected else ["nodev"],
        options_sensitivity="operator_secret" if protected else "plain",
    )
    safe = sanitize_mount_observation([mount.model_dump(mode="json")], observed=True)
    restored = typed_runtime_observation_shape(safe, adapter=TypeAdapter(list[RuntimeMount]))
    assert restored[0].source == mount.source
    assert restored[0].options == mount.options


@pytest.mark.parametrize("field", ["source_present", "options_present"])
def test_safe_mount_presence_cannot_contradict_its_owned_projection(field):
    mount = RuntimeMount(
        target="/work",
        source="/fixtures/work",
        source_kind="bind",
        source_sensitivity="plain",
        options=["nodev"],
        options_sensitivity="plain",
    )
    safe = sanitize_mount_observation([mount.model_dump(mode="json")], observed=True)
    safe[0][field] = False
    with pytest.raises(ValueError):
        typed_runtime_observation_shape(safe, adapter=TypeAdapter(list[RuntimeMount]))


@pytest.mark.parametrize("projector", [project_mounts, sanitize_mount_observation])
@pytest.mark.parametrize("field,value", [("source", "/fixtures/raw-source"), ("options", ["nodev"])])
@pytest.mark.parametrize("sensitivity", ["operator_secret", "redacted"])
def test_raw_protected_mount_material_is_rejected_by_owning_projection(projector, field, value, sensitivity):
    observation = {
        "target": "/work",
        "source_kind": "bind",
        "source": "",
        "source_sensitivity": sensitivity,
        "options": [],
        "options_sensitivity": sensitivity,
    }
    safe = projector([observation], observed=True)
    assert safe[0][field] == observation[field]
    observation[field] = value
    with pytest.raises(ValueError, match=f"^protected runtime mount {field} must not carry raw material$"):
        projector([observation], observed=True)
