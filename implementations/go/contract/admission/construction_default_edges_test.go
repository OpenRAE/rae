package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestConstructionModelDefaultsStayBoundToSchemaAndInstancePath(t *testing.T) {
	owner := boundTestOwner(t)
	check := constructionModels{owner: owner, id: "participant-control-selection-v1", defaults: map[string]any{}}
	instance := validation.SchemaInstance{SchemaPointer: "#/$defs/ControlApplicabilityModel", Path: "/applicability", Value: map[string]any{"participant_address": "participant", "episode_id": "episode", "direction": "ingress", "sink_ref": "sink", "phase_ref": "phase", "subject_kind": "participant-action-contract"}}
	first, err := check.defaultInstance(instance)
	if err != nil || first.Value == nil || len(check.defaults) != 1 {
		t.Fatalf("owned construction defaults failed: %+v %v", first, err)
	}
	second, err := check.defaultInstance(instance)
	if err != nil || second.Value == nil || len(check.defaults) != 1 {
		t.Fatal("same instance did not reuse its bounded defaults")
	}
	instance.Path = "/different"
	instance.Value = func() {}
	if _, err := check.defaultInstance(instance); err == nil || len(check.defaults) != 1 {
		t.Fatal("invalid construction value entered the default cache")
	}
	instance.SchemaPointer = "#/$defs/ControlUnknown"
	instance.Value = map[string]any{}
	if _, err := check.defaultInstance(instance); err == nil || len(check.defaults) != 1 {
		t.Fatal("unknown control model borrowed another schema's defaults")
	}
}
